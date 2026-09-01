"""
Kaldi-compatible 80-band log-mel filterbank, in numpy.

Only needed by the optional neural speaker backend. A pretrained
speaker-embedding network is very particular about its input: it was
trained on Kaldi `fbank` features, and features that are merely
*similar* produce embeddings that are merely similar too, which is
exactly the failure a verification system must not have. So this is a
faithful reimplementation of

    torchaudio.compliance.kaldi.fbank(
        waveform * 32768,      # normalize=False, i.e. int16 scale
        num_mel_bins=80,
        frame_length=25,
        frame_shift=10,
        sample_frequency=16000,
        window_type="hamming",
    )

with every other argument left at its torchaudio default, followed by
WeSpeaker's cepstral mean normalisation. Written out in numpy so the
project needs neither torch nor torchaudio; `_ort_lab.py` checks the
result against the reference values quoted in the tests.
"""

import numpy as np

RATE = 16000

FRAME = 400                 # 25 ms
HOP = 160                   # 10 ms
PADDED = 512                # round_to_power_of_two

BANDS = 80
LOW_HZ = 20.0
HIGH_HZ = 8000.0            # high_freq=0.0 means Nyquist

PREEMPH = 0.97

# torch.finfo(torch.float).eps - the floor Kaldi's log() uses.
FLOOR = 1.1920928955078125e-07

# torch.hamming_window(400, periodic=False, alpha=0.54, beta=0.46)
_WINDOW = np.hamming(FRAME).astype(np.float64)

_BANK = None


def _mel(hz):
    return 1127.0 * np.log(1.0 + np.asarray(hz, dtype=np.float64) / 700.0)


def _bank():
    """Kaldi's triangular mel bank: 80 x 257, the Nyquist column zeroed."""
    global _BANK

    if _BANK is not None:
        return _BANK

    usable = PADDED // 2                       # Kaldi drops the last bin
    width = RATE / float(PADDED)

    low, high = _mel(LOW_HZ), _mel(HIGH_HZ)
    step = (high - low) / (BANDS + 1)

    index = np.arange(BANDS, dtype=np.float64)[:, None]

    left = low + index * step
    centre = low + (index + 1.0) * step
    right = low + (index + 2.0) * step

    points = _mel(width * np.arange(usable, dtype=np.float64))[None, :]

    rising = (points - left) / (centre - left)
    falling = (right - points) / (right - centre)

    bank = np.maximum(0.0, np.minimum(rising, falling))

    _BANK = np.concatenate(
        [bank, np.zeros((BANDS, 1), dtype=np.float64)], axis=1
    )

    return _BANK


def features(samples, normalise=True) -> np.ndarray:
    """16 kHz mono float32 in [-1, 1] -> (frames, 80) float32."""
    data = np.asarray(samples, dtype=np.float64) * 32768.0

    if data.size < FRAME:
        return np.zeros((0, BANDS), dtype=np.float32)

    count = 1 + (data.size - FRAME) // HOP        # snip_edges=True

    windows = np.lib.stride_tricks.as_strided(
        data,
        shape=(count, FRAME),
        strides=(data.strides[0] * HOP, data.strides[0]),
    ).copy()

    windows -= windows.mean(axis=1, keepdims=True)          # remove_dc_offset

    shifted = np.concatenate(
        [windows[:, :1], windows[:, :-1]], axis=1           # replicate pad
    )
    windows -= PREEMPH * shifted

    windows *= _WINDOW

    spectrum = np.fft.rfft(windows, n=PADDED, axis=1)
    power = np.abs(spectrum) ** 2                           # use_power=True

    banded = np.log(np.maximum(power @ _bank().T, FLOOR))

    if normalise:
        banded -= banded.mean(axis=0, keepdims=True)        # WeSpeaker's CMN

    return banded.astype(np.float32)
