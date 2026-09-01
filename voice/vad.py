"""
Voice activity detection: is there meaningful human speech in this clip?

This is the first gate in the pipeline, and its only job is to throw away
sound that no one produced with their voice - fans, hiss, keyboard, a
door, a distant murmur three rooms away. It is deliberately *not* a
security check: a television saying "hey Friday" is real human speech and
will pass here. Deciding *who* spoke is the speaker model's job, and that
runs next.

Four independent pieces of evidence are used, none of them loudness on
its own:

  * dynamic range - speech rises clearly above the room's noise floor,
    a fan or a hum does not
  * harmonicity - a voice repeats at 70-400 Hz, a click or a door or
    broadband hiss does not
  * spectral shape - a voice is peaky, hiss and rumble are flat
  * band placement - a voice lives between 200 and 4000 Hz, while a
    fan, a lorry and a desk knock live underneath it
"""

from dataclasses import dataclass, field

import numpy as np

from voice import dsp

# Below this there is not enough voice to identify anyone anyway.
MIN_VOICED_SECONDS = 0.35

# Speech has to stand clear of the room, and to be a decent part of the
# clip - one syllable in four seconds of hum is not a command.
MIN_SNR_DB = 6.0
MIN_ACTIVE_RATIO = 0.10
MIN_VOICED_RATIO = 0.20

# How far above the noise floor a frame has to be to count as sound.
FLOOR_MARGIN_DB = 6.0

# Autocorrelation peak that says "this frame is a vowel".
# Increased to 0.45 to reject dog barks and semi-tonal noises.
PITCH_ON = 0.45

# Flatness above this is noise-like rather than voice-like.
MAX_FLATNESS = 0.45

# Share of a frame's power that has to sit in the 200-4000 Hz speech band.
BAND_ON = 0.30

# Absolute silence guard, in dBFS: nothing this quiet is a command.
MIN_PEAK_DBFS = -55.0

SECONDS_PER_FRAME = dsp.HOP / float(dsp.RATE)


@dataclass
class SpeechReport:
    """What the detector found, and the frames the speaker model may use."""

    ok: bool = False
    reason: str = "no audio"
    seconds: float = 0.0
    voiced_seconds: float = 0.0
    snr_db: float = 0.0
    pitch: float = 0.0
    flatness: float = 1.0
    band: float = 0.0
    windows: np.ndarray = field(
        default_factory=lambda: np.zeros((0, dsp.FRAME), dtype=np.float32)
    )
    active: np.ndarray = field(
        default_factory=lambda: np.zeros(0, dtype=bool)
    )

    def summary(self) -> str:
        return (
            f"{self.voiced_seconds:.2f}s voiced, "
            f"SNR {self.snr_db:.0f}dB, pitch {self.pitch:.2f}, "
            f"flatness {self.flatness:.2f}, band {self.band:.2f}"
        )


def inspect(samples, pitch_on=PITCH_ON, max_flatness=MAX_FLATNESS,
            min_band=BAND_ON, min_voiced_ratio=MIN_VOICED_RATIO,
            min_voiced_seconds=MIN_VOICED_SECONDS) -> SpeechReport:
    """
    Look at one clip of 16 kHz mono float32 audio.

    The thresholds are arguments rather than constants only so that
    `_vad_lab.py` can sweep them; the defaults above are the swept result
    and nothing in the assistant passes anything else.
    """
    windows = dsp.frames(np.asarray(samples, dtype=np.float32))

    if windows.shape[0] < 8:
        return SpeechReport(reason="too short")

    energy = dsp.energy_db(windows)
    floor = float(np.percentile(energy, 10))
    peak = float(np.percentile(energy, 95))
    snr = peak - floor

    if peak < MIN_PEAK_DBFS:
        return SpeechReport(reason="silence", snr_db=snr, windows=windows)

    # A quiet room has a low floor and a loud one a high floor; the margin
    # scales with the range so both behave the same way.
    cut = floor + max(FLOOR_MARGIN_DB, 0.35 * snr)
    active = energy > cut

    pitch = dsp.pitch_strength(windows)

    power = dsp.power_spectrum(windows)
    flatness = dsp.spectral_flatness(power)
    band = dsp.band_ratio(power)

    voiced = (
        active
        & (pitch >= pitch_on)
        & (flatness <= max_flatness)
        & (band >= min_band)
    )


    total = float(windows.shape[0])
    active_ratio = float(active.sum()) / total
    voiced_ratio = float(voiced.sum()) / total
    voiced_seconds = float(voiced.sum()) * SECONDS_PER_FRAME

    report = SpeechReport(
        seconds=float(active.sum()) * SECONDS_PER_FRAME,
        voiced_seconds=voiced_seconds,
        snr_db=snr,
        pitch=float(pitch[active].mean()) if active.any() else 0.0,
        flatness=float(flatness[active].mean()) if active.any() else 1.0,
        band=float(band[active].mean()) if active.any() else 0.0,
        windows=windows,
        active=active,
    )

    if snr < MIN_SNR_DB:
        report.reason = "no speech above the room"

    elif active_ratio < MIN_ACTIVE_RATIO:
        report.reason = "a blip, not a sentence"

    elif voiced_seconds < min_voiced_seconds:
        report.reason = "no voiced speech"

    elif voiced_ratio < min_voiced_ratio:
        report.reason = "noise-like, not a voice"

    else:
        report.ok = True
        report.reason = "human speech"

    return report


def inspect_audio(audio) -> SpeechReport:
    """Same, straight from a `speech_recognition.AudioData`."""
    return inspect(dsp.from_audiodata(audio))
