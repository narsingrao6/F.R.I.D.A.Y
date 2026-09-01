"""
A small numpy DSP kit, shared by the voice-activity detector and the
speaker model.

No scipy and no torch: everything here is a handful of FFTs over 25 ms
frames, which is all that is needed to turn microphone audio into the
two things the rest of the feature wants - a description of *how* the
sound was produced (is it voiced speech at all?) and a description of
*who* produced it (the cepstral shape of their vocal tract).

Deliberately absent: anything to do with loudness. Frame energy is used
to find speech, never to identify a speaker, and MFCC coefficient 0 -
the one that carries overall gain - is dropped before any comparison.
"""

import wave

import numpy as np

# Everything downstream assumes 16 kHz mono float32 in [-1, 1].
RATE = 16000

FRAME = 400                 # 25 ms analysis window
HOP = 160                   # 10 ms step
FFT = 512

MELS = 26
COEFFS = 20                 # MFCC c0..c19; c0 is dropped by the caller
FMIN = 80.0
FMAX = 7600.0

PREEMPH = 0.97
EPS = 1e-10

# Human pitch range, used to tell voiced speech from fans and clicks.
PITCH_MIN_HZ = 70.0
PITCH_MAX_HZ = 400.0

_WINDOW = np.hamming(FRAME).astype(np.float32)

_BANK = None
_DCT = None


# ------------------------------------------------------------- loading


def from_bytes(raw, width=2) -> np.ndarray:
    """16-bit little-endian PCM bytes -> float32 samples in [-1, 1]."""
    if width != 2:
        raise ValueError("only 16-bit PCM is supported")

    if not raw:
        return np.zeros(0, dtype=np.float32)

    return np.frombuffer(raw, dtype="<i2").astype(np.float32) / 32768.0


def from_audiodata(audio) -> np.ndarray:
    """A `speech_recognition.AudioData` -> 16 kHz mono float32."""
    return from_bytes(
        audio.get_raw_data(convert_rate=RATE, convert_width=2)
    )


def _resample(samples, rate) -> np.ndarray:
    """Linear resampling: good enough, and keeps the dependency list short."""
    if rate == RATE or samples.size == 0:
        return samples

    count = int(round(samples.size * RATE / float(rate)))

    if count <= 0:
        return np.zeros(0, dtype=np.float32)

    source = np.linspace(0.0, samples.size - 1, samples.size)
    target = np.linspace(0.0, samples.size - 1, count)

    return np.interp(target, source, samples).astype(np.float32)


def load_wav(path) -> np.ndarray:
    """Read a PCM WAV file as 16 kHz mono float32."""
    with wave.open(path, "rb") as handle:
        channels = handle.getnchannels()
        width = handle.getsampwidth()
        rate = handle.getframerate()
        raw = handle.readframes(handle.getnframes())

    samples = from_bytes(raw, width)

    if channels > 1:
        usable = samples.size - (samples.size % channels)
        samples = samples[:usable].reshape(-1, channels).mean(axis=1)

    return _resample(samples.astype(np.float32), rate)


def load_mp3(path) -> np.ndarray:
    """
    Decode an mp3 through pygame's mixer, which is already a dependency.

    Only the offline tools need this (Edge TTS writes mp3); the live
    assistant never decodes a file.
    """
    import pygame

    if not pygame.mixer.get_init():
        pygame.mixer.init(frequency=RATE, size=-16, channels=1)

    rate, _, channels = pygame.mixer.get_init()

    sound = pygame.mixer.Sound(path)
    samples = pygame.sndarray.array(sound).astype(np.float32) / 32768.0

    if samples.ndim > 1:
        samples = samples.mean(axis=1)

    return _resample(samples, rate)


def load_file(path) -> np.ndarray:
    """Load a wav or mp3 as 16 kHz mono float32."""
    return load_wav(path) if path.lower().endswith(".wav") else load_mp3(path)


# ------------------------------------------------------------- framing


def frames(samples) -> np.ndarray:
    """Pre-emphasised, windowed 25 ms frames every 10 ms."""
    if samples.size < FRAME:
        return np.zeros((0, FRAME), dtype=np.float32)

    lifted = np.empty_like(samples)
    lifted[0] = samples[0]
    np.subtract(samples[1:], PREEMPH * samples[:-1], out=lifted[1:])

    count = 1 + (lifted.size - FRAME) // HOP

    # A strided view costs nothing; the copy happens in the multiply.
    windows = np.lib.stride_tricks.as_strided(
        lifted,
        shape=(count, FRAME),
        strides=(lifted.strides[0] * HOP, lifted.strides[0]),
    )

    return windows * _WINDOW


def power_spectrum(windows) -> np.ndarray:
    if windows.shape[0] == 0:
        return np.zeros((0, FFT // 2 + 1), dtype=np.float32)

    spectrum = np.fft.rfft(windows, n=FFT, axis=1)

    return (np.abs(spectrum) ** 2) / FFT


# ---------------------------------------------------------------- mel


def _hz_to_mel(hz):
    return 2595.0 * np.log10(1.0 + np.asarray(hz, dtype=np.float64) / 700.0)


def _mel_to_hz(mel):
    return 700.0 * (10.0 ** (np.asarray(mel, dtype=np.float64) / 2595.0) - 1.0)


def _filterbank() -> np.ndarray:
    """Triangular mel filters, built once."""
    global _BANK

    if _BANK is not None:
        return _BANK

    edges = _mel_to_hz(
        np.linspace(_hz_to_mel(FMIN), _hz_to_mel(FMAX), MELS + 2)
    )

    bins = np.floor((FFT + 1) * edges / RATE).astype(int)
    bins = np.clip(bins, 0, FFT // 2)

    bank = np.zeros((MELS, FFT // 2 + 1), dtype=np.float32)

    for index in range(MELS):
        left, centre, right = bins[index], bins[index + 1], bins[index + 2]

        if centre == left:
            centre = min(left + 1, FFT // 2)

        if right <= centre:
            right = min(centre + 1, FFT // 2)

        bank[index, left:centre] = (
            (np.arange(left, centre) - left) / float(centre - left)
        )
        bank[index, centre:right] = (
            (right - np.arange(centre, right)) / float(right - centre)
        )

    _BANK = bank

    return _BANK


def _dct_matrix() -> np.ndarray:
    """Orthonormal-ish DCT-II, built once."""
    global _DCT

    if _DCT is None:
        grid = np.outer(
            np.arange(COEFFS),
            (np.arange(MELS) + 0.5) * np.pi / MELS,
        )

        _DCT = (np.cos(grid) * np.sqrt(2.0 / MELS)).astype(np.float32)

    return _DCT


# ----------------------------------------------------------- features


def log_mel(power) -> np.ndarray:
    if power.shape[0] == 0:
        return np.zeros((0, MELS), dtype=np.float32)

    return np.log(power @ _filterbank().T + EPS)


def mfcc(mels) -> np.ndarray:
    """Cepstral coefficients c0..c19 (the caller drops c0)."""
    if mels.shape[0] == 0:
        return np.zeros((0, COEFFS), dtype=np.float32)

    return mels @ _dct_matrix().T


def deltas(features, width=2) -> np.ndarray:
    """
    First-order regression deltas - how the vocal tract is *moving*.

    Speaker identity survives in the dynamics as well as in the average
    shape, and unlike the static coefficients the deltas are immune to
    any constant channel colouring.
    """
    if features.shape[0] == 0:
        return np.zeros_like(features)

    padded = np.pad(features, ((width, width), (0, 0)), mode="edge")
    steps = np.arange(-width, width + 1, dtype=np.float32)
    scale = float((steps ** 2).sum())

    stacked = np.stack(
        [padded[offset:offset + features.shape[0]] for offset in
         range(2 * width + 1)]
    )

    return np.tensordot(steps, stacked, axes=(0, 0)) / scale


def energy_db(windows) -> np.ndarray:
    """Per-frame RMS in dB. Used to find speech, never to identify it."""
    if windows.shape[0] == 0:
        return np.zeros(0, dtype=np.float32)

    rms = np.sqrt(np.mean(windows.astype(np.float64) ** 2, axis=1) + EPS)

    return (20.0 * np.log10(rms + EPS)).astype(np.float32)


def spectral_flatness(power, low_hz=200.0, high_hz=4000.0) -> np.ndarray:
    """
    Geometric over arithmetic mean, per frame, across the speech band.

    Near 1 for a flat spectrum (fan, hiss, white noise), well below 1 for
    the peaky harmonic spectrum of a voice.

    Only 200-4000 Hz is measured. Below that sits rumble that belongs to
    the room rather than to the speaker, and above it sits the hiss that
    every cheap microphone adds; including either makes a real voice in a
    noisy room look flat, which is how a voice-activity detector ends up
    calling the Boss noise.
    """
    if power.shape[0] == 0:
        return np.zeros(0, dtype=np.float32)

    width = RATE / float(FFT)

    low = max(1, int(low_hz / width))
    high = min(power.shape[1], int(high_hz / width) + 1)

    usable = power[:, low:high] + EPS
    geometric = np.exp(np.mean(np.log(usable), axis=1))
    arithmetic = np.mean(usable, axis=1)

    return (geometric / (arithmetic + EPS)).astype(np.float32)


def band_ratio(power, low_hz=200.0, high_hz=3800.0) -> np.ndarray:
    """
    Share of each frame's power that lies in the speech band.

    A voice puts its formants between roughly 200 and 4000 Hz. A fan, a
    lorry outside, a desk being knocked and the low end of a room's noise
    floor put almost everything below that, and because such a spectrum
    is steeply sloped rather than flat it can look peaky to
    `spectral_flatness` and self-similar to `pitch_strength` - a slowly
    varying signal correlates well with itself at every short lag. Both
    of those measures were fooled by 1/f^2 rumble until this was added.

    A ratio, not a level: scaling the microphone gain does not change it.
    """
    if power.shape[0] == 0:
        return np.zeros(0, dtype=np.float32)

    width = RATE / float(FFT)

    low = max(1, int(low_hz / width))
    high = min(power.shape[1], int(high_hz / width) + 1)

    inside = power[:, low:high].sum(axis=1)
    everything = power.sum(axis=1) + EPS

    return (inside / everything).astype(np.float32)


def pitch_strength(windows, cutoff=1000.0) -> np.ndarray:
    """
    Normalised autocorrelation peak inside the human pitch range.

    High for a voiced vowel, low for keyboard clicks, doors, hiss and
    steady hum - none of which repeat at 70-400 Hz.

    The frame is low-passed first. A vowel's periodicity lives in its
    first few harmonics; everything above `cutoff` is mostly noise, and
    leaving it in is what makes autocorrelation fail on exactly the
    recordings where speech has to be found - a real voice a few feet
    from the microphone with a fan running.
    """
    if windows.shape[0] == 0:
        return np.zeros(0, dtype=np.float32)

    low = int(RATE / PITCH_MAX_HZ)
    high = min(int(RATE / PITCH_MIN_HZ), FRAME - 1)

    if high <= low:
        return np.zeros(windows.shape[0], dtype=np.float32)

    data = windows.astype(np.float32)
    data = data - data.mean(axis=1, keepdims=True)

    size = 1 << (2 * FRAME - 1).bit_length()
    spectrum = np.fft.rfft(data, n=size, axis=1)

    edge = int(cutoff * size / RATE) + 1

    if edge < spectrum.shape[1]:
        spectrum[:, edge:] = 0.0

    correlation = np.fft.irfft(np.abs(spectrum) ** 2, n=size, axis=1)

    zero = correlation[:, :1] + EPS
    window = correlation[:, low:high + 1] / zero

    return np.clip(window.max(axis=1), 0.0, 1.0).astype(np.float32)
