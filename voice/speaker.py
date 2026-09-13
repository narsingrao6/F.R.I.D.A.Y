"""
Edge TTS output for F.R.I.D.A.Y.

The voice is chosen from the ACTUAL RESPONSE TEXT, not from whatever
language the speech recogniser thought the user spoke. The language of
the user's request is passed in only as a weak fallback for very short
replies.

Also handles:
  * transient `NoAudioReceived` failures (retry, then a backup voice)
  * long replies (synthesised and played in sentence chunks, so
    interruption reacts quickly)
  * immediate stop for barge-in and for Ctrl+C
"""

import asyncio
import sys

if sys.platform == 'win32':
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
import os
import re
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import pygame
import edge_tts

from voice.audio import is_shutting_down
from voice.language import detect_response_language

# --------------------------------------------------------------- settings

VOICES = {
    "en": "en-US-AriaNeural",
    "te": "te-IN-ShrutiNeural",
    "hi": "hi-IN-SwaraNeural",
}

# Used only if the primary voice keeps failing.
BACKUP_VOICES = {
    "en": "en-US-JennyNeural",
    "te": "te-IN-MohanNeural",
    "hi": "hi-IN-MadhurNeural",
}

RATE = "+5%"

MAX_ATTEMPTS = 3
RETRY_DELAY = 0.5

# Edge TTS latency is round trip, not text length: measured over 7 runs
# each, te-IN-ShrutiNeural took a median 0.81s for 39 characters and
# 0.92s for 233. So splitting a reply to "start sooner" buys nothing and
# costs an extra request, and the limit stays where it was - high enough
# that a normal reply is one request. What splitting is still for is a
# genuinely long reply, and there the fix is to download the next piece
# while the current one plays (see `_speak_chunks`) so the ~0.9s gap at
# every boundary disappears.
CHUNK_LIMIT = 600

# ------------------------------------------------------------------ state

_playback_lock = threading.Lock()
_state_lock = threading.Lock()

_speaking = threading.Event()
_stop_playback = threading.Event()

_current_text = ""
_temp_files = set()


def is_speaking() -> bool:
    """True while audio is being generated or played."""
    return _speaking.is_set()


def current_speech() -> str:
    """What F.R.I.D.A.Y. is saying right now (used for echo rejection)."""
    with _state_lock:
        return _current_text


def _begin(text):
    global _current_text

    with _state_lock:
        _current_text = text

    _speaking.set()


def _end():
    global _current_text

    _speaking.clear()

    with _state_lock:
        _current_text = ""


# ------------------------------------------------------------- text hygiene

_MARKDOWN = re.compile(
    r"(\*\*|__|\*|`{1,3}|~~|^#{1,6}\s*|^\s*[-*+]\s+|^\s*>\s?)",
    re.MULTILINE,
)

_EMOJI = re.compile(
    "[\U0001F000-\U0001FAFF←-⇿☀-➿️⬀-⯿]+"
)

def sanitize(text: str) -> str:
    """
    Edge TTS answers `NoAudioReceived` for text it cannot voice
    (markdown symbols, emoji-only strings, empty text), so clean it up
    before sending.
    """
    if not text:
        return ""

    clean = _MARKDOWN.sub(" ", str(text))
    clean = _EMOJI.sub(" ", clean)
    clean = re.sub(r"\s+", " ", clean).strip()

    # Anything with no letters or digits left cannot be spoken.
    if not re.search(r"[^\W_]", clean, re.UNICODE):
        return ""

    return clean


def _chunks(text: str, limit: int = CHUNK_LIMIT):
    """
    Split a long reply on sentence boundaries.

    A normal reply comes back as a single chunk. Only a genuinely long
    one is split, and then only between sentences unless one sentence is
    on its own longer than the limit.
    """
    pieces = [
        piece
        for piece in re.split(r"(?<=[.!?。।॥\n])\s+", text)
        if piece.strip()
    ]

    if not pieces:
        return [text] if text else []

    chunks = []
    buffer = ""

    for piece in pieces:

        if buffer and len(buffer) + len(piece) + 1 > limit:
            chunks.append(buffer)
            buffer = ""

        # A single monster sentence still has to be cut somewhere.
        while len(piece) > limit:
            if buffer:
                chunks.append(buffer)
                buffer = ""

            chunks.append(piece[:limit])
            piece = piece[limit:]

        buffer = f"{buffer} {piece}".strip() if buffer else piece

    if buffer:
        chunks.append(buffer)

    return chunks


# ------------------------------------------------------------- synthesis


def _new_temp_path() -> str:
    handle, path = tempfile.mkstemp(
        prefix="friday_tts_",
        suffix=".mp3",
    )

    os.close(handle)

    with _state_lock:
        _temp_files.add(path)

    return path


def _drop_temp(path):
    if not path:
        return

    with _state_lock:
        _temp_files.discard(path)

    try:
        if os.path.exists(path):
            os.remove(path)

    except OSError:
        pass


class _Aborted(Exception):
    """Synthesis was abandoned because we were told to stop."""


async def _save(text, voice, path):
    """
    Stream one chunk to disk, giving up straight away if a barge-in or
    Ctrl+C arrives while the request is still in flight.
    """
    communicate = edge_tts.Communicate(
        text=text,
        voice=voice,
        rate=RATE,
    )

    task = asyncio.create_task(communicate.save(path))
    
    start_time = time.time()
    timeout = 15.0

    while not task.done():

        if _stop_playback.is_set() or is_shutting_down():
            task.cancel()

            try:
                await task

            except BaseException:
                pass

            raise _Aborted()
            
        if time.time() - start_time > timeout:
            task.cancel()
            try:
                await task
            except BaseException:
                pass
            raise TimeoutError("Edge TTS request timed out.")

        await asyncio.sleep(0.05)

    # Re-raise anything the download failed with.
    await task


def _synthesize(text, voice, backup_voice):
    """Generate one chunk, tolerating transient Edge TTS failures."""
    for attempt in range(1, MAX_ATTEMPTS + 1):

        if _stop_playback.is_set() or is_shutting_down():
            return None

        # Last attempt switches to the backup voice of the same language.
        chosen = voice if attempt < MAX_ATTEMPTS else backup_voice
        path = None

        try:
            path = _new_temp_path()

            asyncio.run(_save(text, chosen, path))

            if os.path.getsize(path) > 0:
                return path

            raise edge_tts.exceptions.NoAudioReceived(
                "Edge TTS returned an empty file."
            )

        except _Aborted:
            _drop_temp(path)

            return None

        except Exception as error:
            _drop_temp(path)

            print(
                f"F.R.I.D.A.Y.: TTS attempt {attempt}/{MAX_ATTEMPTS} "
                f"failed on {chosen}: {type(error).__name__}"
            )

            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_DELAY * attempt)

    print(
        "F.R.I.D.A.Y.: Skipping this part of the reply "
        "(voice service unavailable)."
    )

    return None


# -------------------------------------------------------------- playback


def _ensure_mixer() -> bool:
    try:
        if not pygame.mixer.get_init():
            pygame.mixer.init()

        return True

    except pygame.error as error:
        print(
            f"F.R.I.D.A.Y.: Audio device error: {error}"
        )

        return False


def _play(path) -> bool:
    """Play one chunk. Returns False if it was cut short."""
    if not _ensure_mixer():
        return False

    completed = True

    try:
        pygame.mixer.music.load(path)
        pygame.mixer.music.play()

        # get_busy() can lag a few milliseconds behind play().
        time.sleep(0.05)

        while pygame.mixer.music.get_busy():

            if _stop_playback.is_set() or is_shutting_down():
                pygame.mixer.music.stop()
                completed = False
                break

            time.sleep(0.05)

        # Another thread may have stopped the music between two checks.
        if _stop_playback.is_set() or is_shutting_down():
            completed = False

    except pygame.error as error:
        print(
            f"F.R.I.D.A.Y.: Playback error: {error}"
        )

        completed = False

    finally:
        try:
            if pygame.mixer.get_init():
                pygame.mixer.music.stop()

                try:
                    pygame.mixer.music.unload()
                except pygame.error:
                    pass

        except pygame.error:
            pass

        _drop_temp(path)

    return completed


# ------------------------------------------------------------ public API


def _discard_later(pending):
    """
    Throw away a prefetch nobody is going to play.

    The conversation must not wait for an abandoned download, so the file
    is removed on a side thread; `shutdown_audio` sweeps anything left.
    """
    if pending is None:
        return

    threading.Thread(
        target=lambda: _drop_temp(pending.result()),
        daemon=True,
    ).start()


def _speak_chunks(chunks, voice, backup_voice) -> bool:
    """
    Play each chunk while the next one is already downloading.

    Only the first chunk is on the clock; every later download hides
    behind the playback of the one before it.
    """
    pool = ThreadPoolExecutor(max_workers=1)
    completed = True

    try:
        pending = pool.submit(_synthesize, chunks[0], voice, backup_voice)

        for index in range(len(chunks)):
            path = pending.result()
            following = index + 1

            pending = (
                pool.submit(_synthesize, chunks[following], voice, backup_voice)
                if following < len(chunks)
                else None
            )

            if path is None:
                # One chunk failed; the rest of the reply still gets said.
                completed = False
                continue

            if not _play(path):
                completed = False
                break

        _discard_later(pending)

    finally:
        pool.shutdown(wait=False)

    return completed


def resolve_voice(text, hint=None):
    """
    Pick the voice for `text`.

    Returns `(language_code, voice_name, LanguageResult)`.
    The response text decides; `hint` is only a weak rescue.
    """
    result = detect_response_language(text, fallback=hint)

    code = result.code if result.code in VOICES else "en"

    return code, VOICES[code], result


def speak(text, language=None, hint=None) -> bool:
    """
    Say `text`.

    `language` is kept for backwards compatibility - it is treated as a
    hint about the user's language, never as the truth about the reply.
    Returns True if the whole reply was spoken.
    """
    clean = sanitize(text)

    if not clean or is_shutting_down():
        return False

    code, voice, result = resolve_voice(clean, hint or language)
    backup_voice = BACKUP_VOICES.get(code, BACKUP_VOICES["en"])

    with _playback_lock:

        _stop_playback.clear()
        _begin(clean)

        print(
            f"F.R.I.D.A.Y.: Speaking ({code} / {result.style} "
            f"via {voice})..."
        )

        completed = True

        try:
            pieces = _chunks(clean)

            if not pieces:
                completed = False

            elif _stop_playback.is_set() or is_shutting_down():
                completed = False

            else:
                completed = _speak_chunks(pieces, voice, backup_voice)

        except Exception as error:
            # A voice problem must never take the assistant down.
            print(
                f"F.R.I.D.A.Y.: Voice error: "
                f"{type(error).__name__}: {error}"
            )

            completed = False

        finally:
            _end()

    return completed


def stop_speaking():
    """Barge-in: cut the current reply immediately."""
    _stop_playback.set()

    try:
        if pygame.mixer.get_init():
            pygame.mixer.music.stop()

            try:
                pygame.mixer.music.unload()
            except pygame.error:
                pass

    except pygame.error:
        pass

    if _speaking.is_set():
        print("F.R.I.D.A.Y.: Speech stopped.")


def shutdown_audio():
    """Release every audio resource (called on exit)."""
    stop_speaking()
    _speaking.clear()

    try:
        if pygame.mixer.get_init():
            pygame.mixer.quit()

    except pygame.error:
        pass

    with _state_lock:
        leftovers = list(_temp_files)

    for path in leftovers:
        _drop_temp(path)

