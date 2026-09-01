"""
One controlled audio-input pipeline for F.R.I.D.A.Y.

`VoiceListener` (transcription) and `InterruptionController` (barge-in)
used to each create their own `sr.Microphone`, so they could fight over
the same device. Both now borrow the single microphone owned here, and
the lock guarantees only one of them holds the stream at a time.

This module also owns the global shutdown flag, because every audio
consumer (microphone, Whisper upload, TTS playback) has to react to it.
"""

import threading
from contextlib import contextmanager

import speech_recognition as sr


class MicrophoneBusy(RuntimeError):
    """Raised when the microphone could not be borrowed in time."""


# --------------------------------------------------------------- shutdown

_shutdown = threading.Event()


def request_shutdown():
    """Ctrl+C / exit command: tell every audio consumer to stop now."""
    _shutdown.set()


def is_shutting_down() -> bool:
    return _shutdown.is_set()


def clear_shutdown():
    _shutdown.clear()


# ------------------------------------------------------------- microphone


class MicrophoneHub:
    """Serialised access to a single shared `sr.Microphone`."""

    def __init__(self):
        self._lock = threading.Lock()
        self._create_lock = threading.Lock()
        self._microphone = None

    def _get_microphone(self):
        with self._create_lock:
            if self._microphone is None:
                self._microphone = sr.Microphone()

            return self._microphone

    @contextmanager
    def session(self, recognizer=None, calibrate=0.0, timeout=15.0):
        """
        Borrow the microphone.

        Yields a `speech_recognition` source. `sr.Microphone` opens
        PyAudio on enter and terminates it on exit, so the device is
        always released when the block finishes.
        """
        if not self._lock.acquire(timeout=timeout):
            raise MicrophoneBusy(
                "Microphone is still held by another listener."
            )

        try:
            with self._get_microphone() as source:

                if calibrate and recognizer is not None:
                    recognizer.adjust_for_ambient_noise(
                        source,
                        duration=calibrate
                    )

                yield source

        finally:
            self._lock.release()

    def is_busy(self) -> bool:
        return self._lock.locked()

    def release(self):
        """Drop the cached device handle (used on shutdown)."""
        with self._create_lock:
            self._microphone = None


# Single shared instance.
mic_hub = MicrophoneHub()
