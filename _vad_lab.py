"""
Temporary lab: choose the voice-activity thresholds by measuring them.

The detector was rejecting real speech - four clean Malayalam clips came
back as "noise-like, not a voice", and once any room noise was added it
passed nothing at all while the speaker embedder could still tell the
voices apart. That is the worst possible failure for this feature: the
Boss speaks and the assistant hears nothing.

So the thresholds get measured rather than guessed. Positives are real
speech (clean, short, and buried in white or pink noise at 20/10/5 dB);
negatives are the sounds a room actually makes. The grid is searched for
the point that passes the most speech while letting through none of the
noise, and a candidate only wins if its neighbours in the grid are safe
too - a threshold that only works at one grid corner is fitted to this
corpus, not to a room.

Music, television speech and a conversation three rooms away are listed
as `watch` rather than `noise`: they are real vocal sound, the detector
is not a security check, and rejecting them is the speaker model's job.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _spk_lab as lab

from voice import dsp, vad

RNG = np.random.default_rng(7)

# (FLOOR_MARGIN_DB, share of the clip's own dynamic range)
FLOOR_GRID = ((4.0, 0.25), (4.0, 0.35), (6.0, 0.25), (6.0, 0.35),
              (8.0, 0.35), (8.0, 0.45))
SNR_GRID = (2.0, 3.0, 4.0, 5.0, 6.0)
ACTIVE_GRID = (0.05, 0.08, 0.10, 0.15)
PITCH_GRID = (0.15, 0.20, 0.25, 0.30, 0.35, 0.40)
FLAT_GRID = (0.35, 0.45, 0.55, 0.65, 0.75)
BAND_GRID = (0.10, 0.20, 0.30, 0.40, 0.50)
RATIO_GRID = (0.03, 0.05, 0.08, 0.10, 0.15, 0.20)

CURRENT = ((6.0, 0.35), 6.0, 0.10, 0.35, 0.45, 0.30, 0.20)

# Fixed: a quarter second is the least voice anyone could be identified
# from, and the absolute silence guard is not a tuning knob.
MIN_VOICED_SECONDS = 0.25

SPEECH_VOICES = lab.EVAL[:6] + lab.BACKGROUND[:8]
SPEECH_TAGS = ("en_a", "native")


# ------------------------------------------------------------- the corpus


def speech_clips():
    """(name, samples) for a slice of the TTS corpus."""
    out = []

    for voice in SPEECH_VOICES:
        for tag, _ in lab.clips_for(voice):
            if tag not in SPEECH_TAGS:
                continue

            path = os.path.join(lab.OUT, f"{voice}__{tag}.mp3")

            if os.path.exists(path):
                out.append((f"{voice[:18]}:{tag}", dsp.load_file(path)))

    return out


def spoken_level(samples):
    """RMS of the part of the clip that is actually speech, in dBFS."""
    windows = dsp.frames(np.asarray(samples, dtype=np.float32))

    if windows.shape[0] == 0:
        return -90.0

    energy = dsp.energy_db(windows)

    return float(np.percentile(energy, 80))


def trimmed(samples, seconds=None):
    """Drop the leading silence Edge TTS adds, then optionally truncate."""
    report = vad.inspect(samples, pitch_on=0.0, max_flatness=1.0,
                         min_band=0.0, min_voiced_ratio=0.0,
                         min_voiced_seconds=0.0)

    marks = np.flatnonzero(report.active)
    start = int(marks[0]) * dsp.HOP if marks.size else 0

    cut = samples[start:]

    if seconds is not None:
        cut = cut[:int(seconds * dsp.RATE)]

    return cut


# ------------------------------------------------------------ the room


def _at_db(samples, dbfs):
    """Scale so the RMS sits at `dbfs`."""
    rms = float(np.sqrt(np.mean(np.asarray(samples, dtype=np.float64) ** 2)))

    if rms <= 0.0:
        return np.asarray(samples, dtype=np.float32)

    return (samples * (10.0 ** (dbfs / 20.0) / rms)).astype(np.float32)


def _coloured(count, power, seed=None):
    """1/f**power noise, built by shaping a white spectrum."""
    rng = RNG if seed is None else np.random.default_rng(seed)

    spectrum = np.fft.rfft(rng.standard_normal(count))
    bins = np.arange(spectrum.size, dtype=np.float64)
    bins[0] = 1.0

    shaped = np.fft.irfft(spectrum / bins ** power, n=count)

    return shaped.astype(np.float32)


def _band(samples, low_hz, high_hz):
    """Crude brick-wall band-pass; good enough to shape a noise bed."""
    spectrum = np.fft.rfft(samples)
    freqs = np.fft.rfftfreq(len(samples), 1.0 / dsp.RATE)

    spectrum[(freqs < low_hz) | (freqs > high_hz)] = 0.0

    return np.fft.irfft(spectrum, n=len(samples)).astype(np.float32)


def _clicks(count, rate=4.0, seed=3):
    """Keyboard: sparse broadband taps with a fast decay."""
    rng = np.random.default_rng(seed)
    out = np.zeros(count, dtype=np.float32)

    for start in rng.integers(0, count - 800, int(count / dsp.RATE * rate)):
        length = int(rng.integers(120, 400))
        decay = np.exp(-np.arange(length) / (length / 4.0))

        out[start:start + length] += (
            rng.standard_normal(length) * decay
        ).astype(np.float32)

    return out


def _hum(count, base=50.0, seed=4):
    """Mains hum: a low fundamental, its harmonics and a little hiss."""
    rng = np.random.default_rng(seed)
    time = np.arange(count) / float(dsp.RATE)

    out = np.zeros(count, dtype=np.float64)

    for index in range(1, 7):
        out += (1.0 / index) * np.sin(
            2.0 * np.pi * base * index * time + rng.uniform(0, 6.28)
        )

    out += 0.02 * rng.standard_normal(count)

    return out.astype(np.float32)


def _fan(count, seed=5):
    """Fan or air handler: low noise with a slow throb."""
    bed = _band(_coloured(count, 1.0, seed), 40.0, 600.0)
    time = np.arange(count) / float(dsp.RATE)

    return (bed * (1.0 + 0.3 * np.sin(2.0 * np.pi * 0.4 * time))).astype(
        np.float32
    )


def _thump(count, seed=6):
    """A door closing: one low transient, then the room."""
    rng = np.random.default_rng(seed)
    out = _at_db(_coloured(count, 1.0, seed), -60.0).astype(np.float64)

    start = count // 3
    length = min(int(0.25 * dsp.RATE), count - start)
    decay = np.exp(-np.arange(length) / (0.05 * dsp.RATE))

    burst = _band(rng.standard_normal(length).astype(np.float32), 30.0, 250.0)
    out[start:start + length] += burst * decay

    return out.astype(np.float32)


def noise_clips(seconds=3.0):
    """The sounds that must never reach the speaker model."""
    count = int(seconds * dsp.RATE)

    out = []

    for step, seed in enumerate((11, 51, 91)):
        level = -25.0 - 4.0 * step

        out += [
            (f"white {level:.0f}dB", _at_db(_coloured(count, 0.0, seed),
                                            level)),
            (f"pink {level:.0f}dB", _at_db(_coloured(count, 1.0, seed + 1),
                                           level)),
            (f"brown {level:.0f}dB", _at_db(_coloured(count, 2.0, seed + 2),
                                             level)),
            (f"fan {level + 3:.0f}dB", _at_db(_fan(count, seed + 3),
                                              level + 3.0)),
            (f"air-con {level:.0f}dB",
             _at_db(_band(_coloured(count, 0.5, seed + 4), 200.0, 2000.0),
                    level)),
            (f"hum{50 + step * 5}Hz {level:.0f}dB",
             _at_db(_hum(count, 50.0 + step * 5.0, seed + 5), level)),
            (f"keyboard {level:.0f}dB",
             _at_db(_clicks(count, 3.0 + step, seed + 6), level)),
            (f"rumble {level:.0f}dB",
             _at_db(_band(_coloured(count, 2.0, seed + 7), 20.0, 200.0),
                    level)),
        ]

    out += [
        ("door thump", _thump(count, 22)),
        ("near silence", _at_db(_coloured(count, 1.0, 23), -68.0)),
        ("hiss -42dB", _at_db(_coloured(count, 0.0, 24), -42.0)),
        ("fan + hum", _at_db(_fan(count, 25) + 0.3 * _hum(count, 50.0, 26),
                             -24.0)),
    ]

    return out


def _music(count, seed=24):
    """Instrument-like: harmonic, sustained, with vibrato. Not a voice, but
    periodic enough that a detector cannot be expected to reject it."""
    rng = np.random.default_rng(seed)
    time = np.arange(count) / float(dsp.RATE)

    out = np.zeros(count, dtype=np.float64)

    for root in (196.0, 246.9, 293.7):
        vibrato = 1.0 + 0.004 * np.sin(2.0 * np.pi * 5.5 * time)

        for harmonic in range(1, 8):
            out += (0.6 ** harmonic) * np.sin(
                2.0 * np.pi * root * harmonic * time * vibrato
                + rng.uniform(0, 6.28)
            )

    envelope = 0.6 + 0.4 * np.sin(2.0 * np.pi * 0.8 * time) ** 2

    return (out * envelope).astype(np.float32)


def watch_clips(speech, seconds=3.0):
    """Vocal sound that is not the Boss. The speaker model rejects these;
    the detector is not expected to, and it is measured either way."""
    count = int(seconds * dsp.RATE)
    voice = trimmed(speech[0][1], seconds)
    other = trimmed(speech[2][1], seconds)

    room = _at_db(_coloured(voice.size, 1.0, 31), -52.0)
    distant = _at_db(_band(voice, 150.0, 1400.0), -46.0) + room

    return [
        ("music -25dB", _at_db(_music(count), -25.0)),
        ("music -18dB", _at_db(_music(count, 25), -18.0)),
        ("television", _at_db(_band(other, 300.0, 3400.0), -24.0)),
        ("distant talk", distant.astype(np.float32)),
    ]


def mix(samples, bed, snr_db):
    """Speech plus a noise bed at a stated speech-to-noise ratio."""
    level = spoken_level(samples)

    if bed.size < samples.size:
        bed = np.tile(bed, int(np.ceil(samples.size / bed.size)))

    return (samples + _at_db(bed[:samples.size], level - snr_db)).astype(
        np.float32
    )


def groups():
    """[(label, kind, [(name, samples)])] - kind in speech / noise / watch."""
    speech = speech_clips()

    if not speech:
        raise SystemExit("no corpus: run _spk_lab.py first")

    whole = [(name, trimmed(one)) for name, one in speech]
    short = [(name, trimmed(one, 1.5)) for name, one in speech]
    brief = [(name, trimmed(one, 1.0)) for name, one in speech]

    count = int(4.0 * dsp.RATE)
    white = _coloured(count, 0.0, 41)
    pink = _coloured(count, 1.0, 42)
    fan = _fan(count, 43)

    out = [
        ("clean", "speech", whole),
        ("clean 1.5s", "speech", short),
        ("clean 1.0s", "speech", brief),
    ]

    for label, bed in (("white", white), ("pink", pink), ("fan", fan)):
        for snr in (20.0, 10.0, 5.0):
            out.append((
                f"{label} {snr:.0f}dB", "speech",
                [(name, mix(one, bed, snr)) for name, one in whole],
            ))

    out.append((
        "pink 10dB 1.5s", "speech",
        [(name, mix(one, pink, 10.0)) for name, one in short],
    ))

    out.append(("room noise", "noise", noise_clips()))
    out.append(("not the Boss", "watch", watch_clips(speech)))

    return out


# ------------------------------------------------------------ measurement


def measure(samples):
    """Everything the decision could possibly depend on, once per clip."""
    windows = dsp.frames(np.asarray(samples, dtype=np.float32))

    if windows.shape[0] < 8:
        return None

    energy = dsp.energy_db(windows)
    floor = float(np.percentile(energy, 10))
    peak = float(np.percentile(energy, 95))
    snr = peak - floor

    pitch = dsp.pitch_strength(windows)

    power = dsp.power_spectrum(windows)
    flat = dsp.spectral_flatness(power)
    band = dsp.band_ratio(power)

    total = float(windows.shape[0])

    shape = (len(PITCH_GRID), len(FLAT_GRID), len(BAND_GRID))

    looks_voiced = (
        (pitch[:, None, None, None] >= np.array(PITCH_GRID)[:, None, None])
        & (flat[:, None, None, None] <= np.array(FLAT_GRID)[None, :, None])
        & (band[:, None, None, None] >= np.array(BAND_GRID)[None, None, :])
    )

    active_ratio = np.zeros(len(FLOOR_GRID))
    voiced_ratio = np.zeros((len(FLOOR_GRID),) + shape)

    for index, (margin, share) in enumerate(FLOOR_GRID):
        active = energy > floor + max(margin, share * snr)

        active_ratio[index] = active.sum() / total
        voiced_ratio[index] = (
            active[:, None, None, None] & looks_voiced
        ).sum(axis=0) / total

    middle = np.flatnonzero(energy > floor + 6.0)
    loud = middle if middle.size else np.arange(len(energy))

    return {
        "peak": peak, "snr": snr,
        "active": active_ratio, "ratio": voiced_ratio,
        "sec": voiced_ratio * total * vad.SECONDS_PER_FRAME,
        "pitch": float(np.median(pitch[loud])),
        "flat": float(np.median(flat[loud])),
        "band": float(np.median(band[loud])),
    }


# ------------------------------------------------------------- the search


def rates(table):
    """Pass rate over one group for every point in the grid."""
    peak = np.array([one["peak"] for one in table])
    snr = np.array([one["snr"] for one in table])
    active = np.stack([one["active"] for one in table])
    ratio = np.stack([one["ratio"] for one in table])
    second = np.stack([one["sec"] for one in table])

    count = len(table)
    shape = (count, len(FLOOR_GRID), len(SNR_GRID), len(ACTIVE_GRID),
             len(PITCH_GRID), len(FLAT_GRID), len(RATIO_GRID))

    good = np.ones(shape, dtype=bool)

    good &= (peak >= vad.MIN_PEAK_DBFS).reshape(count, 1, 1, 1, 1, 1, 1)
    good &= (snr[:, None] >= np.array(SNR_GRID)).reshape(
        count, 1, -1, 1, 1, 1, 1)
    good &= (active[:, :, None] >= np.array(ACTIVE_GRID)).reshape(
        count, len(FLOOR_GRID), 1, -1, 1, 1, 1)
    good &= (second >= MIN_VOICED_SECONDS).reshape(
        count, len(FLOOR_GRID), 1, 1, len(PITCH_GRID), len(FLAT_GRID), 1)
    good &= (ratio[..., None] >= np.array(RATIO_GRID)).reshape(
        count, len(FLOOR_GRID), 1, 1, len(PITCH_GRID), len(FLAT_GRID), -1)

    return good.mean(axis=0), good.sum(axis=0)


def erode(flags):
    """True only where every one-step neighbour in the grid is also True."""
    out = flags.copy()

    for axis in range(flags.ndim):
        for shift in (-1, 1):
            moved = np.roll(flags, shift, axis=axis)

            edge = [slice(None)] * flags.ndim
            edge[axis] = 0 if shift == 1 else -1
            moved[tuple(edge)] = flags[tuple(edge)]

            out &= moved

    return out


def point(index):
    """Grid index -> the six threshold values."""
    floor, snr, active, pitch, flat, ratio = index

    return (FLOOR_GRID[floor], SNR_GRID[snr], ACTIVE_GRID[active],
            PITCH_GRID[pitch], FLAT_GRID[flat], RATIO_GRID[ratio])


def index_of(values):
    """The six threshold values -> grid index."""
    grids = (FLOOR_GRID, SNR_GRID, ACTIVE_GRID, PITCH_GRID, FLAT_GRID,
             RATIO_GRID)

    return tuple(grid.index(value) for grid, value in zip(grids, values))


def show(name, values, worst, mean, leaks, watched):
    floor, snr, active, pitch, flat, ratio = values

    print(f"  {name:<12} floor {floor[0]:.0f}dB/{floor[1]:.2f}  "
          f"SNR {snr:.0f}  act {active:.2f}  pitch {pitch:.2f}  "
          f"flat {flat:.2f}  voiced {ratio:.2f}   "
          f"speech worst {worst * 100:5.1f}%  mean {mean * 100:5.1f}%  "
          f"noise {leaks}  watch {watched}")


def passes_at(row, values):
    """Would this one clip pass, at this one grid point?"""
    floor, snr, active, pitch, flat, ratio = values

    place = (FLOOR_GRID.index(floor), PITCH_GRID.index(pitch),
             FLAT_GRID.index(flat))

    return bool(
        row["peak"] >= vad.MIN_PEAK_DBFS
        and row["snr"] >= snr
        and row["active"][place[0]] >= active
        and row["sec"][place] >= MIN_VOICED_SECONDS
        and row["ratio"][place] >= ratio
    )


def sweep():
    print("Measuring...")

    table = []

    for label, kind, clips in groups():
        rows = []
        names = []

        for name, one in clips:
            row = measure(one)

            if row is not None:
                rows.append(row)
                names.append(name)

        table.append((label, kind, rows, names))

    print("\nwhat the frames look like, median over the loud frames")
    print(f"  {'group':<16}{'clips':>6}{'SNR dB':>9}{'pitch':>7}{'flat':>7}")

    for label, kind, rows, _ in table:
        print(f"  {label:<16}{len(rows):>6}"
              f"{np.median([one['snr'] for one in rows]):9.1f}"
              f"{np.median([one['pitch'] for one in rows]):7.2f}"
              f"{np.median([one['flat'] for one in rows]):7.2f}")

    scored = {label: rates(rows) for label, kind, rows, _ in table}
    kinds = {label: kind for label, kind, _, _ in table}

    speech = np.stack([scored[label][0] for label in scored
                       if kinds[label] == "speech"])
    leaks = sum(scored[label][1] for label in scored
                if kinds[label] == "noise")
    watched = sum(scored[label][1] for label in scored
                  if kinds[label] == "watch")

    worst = speech.min(axis=0)
    mean = speech.mean(axis=0)

    firm = erode(leaks == 0)

    if not firm.any():
        raise SystemExit("no grid point rejects every noise bed")

    # Robust in both directions: the neighbours must also let every speech
    # group through, so the choice is not sitting on a cliff edge.
    best = float(worst[firm].max())
    firm &= erode(worst >= best)

    # Among equals, the strictest point - less noise reaching the speaker
    # model is free security, and here it costs no speech at all.
    order = sorted(
        (tuple(one) for one in np.argwhere(firm)),
        key=lambda index: (-SNR_GRID[index[1]], -ACTIVE_GRID[index[2]],
                           -FLOOR_GRID[index[0]][0], -FLOOR_GRID[index[0]][1],
                           -PITCH_GRID[index[3]], FLAT_GRID[index[4]],
                           -RATIO_GRID[index[5]]),
    )

    print(f"\n{firm.sum()} of {leaks.size} grid points pass every speech "
          f"group at {best * 100:.0f}% and reject every noise bed, with a "
          f"safe neighbourhood in both directions; strictest twelve:")

    for index in order[:12]:
        show("", point(index), worst[index], mean[index],
             int(leaks[index]), int(watched[index]))

    now = index_of(CURRENT)
    chosen = order[0]

    print()
    show("shipping now", CURRENT, worst[now], mean[now], int(leaks[now]),
         int(watched[now]))
    show("chosen", point(chosen), worst[chosen], mean[chosen],
         int(leaks[chosen]), int(watched[chosen]))

    print("\nper group, at those two points")
    print(f"  {'group':<16}{'kind':>7}{'now':>8}{'chosen':>8}")

    for label, kind, _, _ in table:
        rate = scored[label][0]

        print(f"  {label:<16}{kind:>7}{rate[now] * 100:7.0f}%"
              f"{rate[chosen] * 100:7.0f}%")

    print("\nevery non-speech clip, at the chosen point")

    for label, kind, rows, names in table:
        if kind == "speech":
            continue

        for row, name in zip(rows, names):
            verdict = "PASSES" if passes_at(row, point(chosen)) else "rejected"

            print(f"  {name:<18}{kind:>7}  SNR {row['snr']:5.1f}  "
                  f"pitch {row['pitch']:.2f}  flat {row['flat']:.2f}  "
                  f"-> {verdict}")

    return point(chosen)


# --------------------------------------------------- does it hold up now?


def recheck():
    """
    With the thresholds locked, does real speech in a noisy room still
    reach the speaker model, and does the speaker model still separate
    the voices once it gets there?
    """
    import _ort_lab as ort_lab

    voices = lab.EVAL

    clean = {
        voice: {
            tag: trimmed(dsp.load_file(
                os.path.join(lab.OUT, f"{voice}__{tag}.mp3")))
            for tag, _ in lab.clips_for(voice)
        }
        for voice in voices
    }

    profile = {}

    for voice in voices:
        pooled = sum(
            ort_lab.embed(clean[voice][tag]) for tag in lab.ENROL
        )
        profile[voice] = pooled / np.linalg.norm(pooled)

    count = int(4.0 * dsp.RATE)
    beds = (
        ("clean", None, 0.0),
        ("white 20dB", _coloured(count, 0.0, 41), 20.0),
        ("white 10dB", _coloured(count, 0.0, 41), 10.0),
        ("white 5dB", _coloured(count, 0.0, 41), 5.0),
        ("pink 20dB", _coloured(count, 1.0, 42), 20.0),
        ("pink 10dB", _coloured(count, 1.0, 42), 10.0),
        ("pink 5dB", _coloured(count, 1.0, 42), 5.0),
        ("fan 10dB", _fan(count, 43), 10.0),
    )

    print(f"\n  {'condition':<12}{'VAD ok':>8}{'gen min':>9}{'gen mean':>10}"
          f"{'imp max':>9}{'gap':>8}")

    for label, bed, snr in beds:
        embeddings = {}
        passed = 0
        total = 0

        for voice in voices:
            for tag in lab.TEST:
                total += 1

                one = clean[voice][tag]
                one = one if bed is None else mix(one, bed, snr)

                report = vad.inspect(one)

                if not report.ok:
                    continue

                passed += 1
                embeddings[(voice, tag)] = ort_lab.embed(
                    ort_lab.audible((one, report), "trim")
                )

        genuine = [lab._cosine(profile[voice], one)
                   for (voice, _), one in embeddings.items()]
        imposter = [
            lab._cosine(profile[other], one)
            for (voice, _), one in embeddings.items()
            for other in voices
            if lab.identity(other) != lab.identity(voice)
        ]

        if not genuine:
            print(f"  {label:<12}{passed:>4}/{total:<3}"
                  f"{'-':>9}{'-':>10}{'-':>9}{'-':>8}")
            continue

        print(f"  {label:<12}{passed:>4}/{total:<3}"
              f"{min(genuine):+9.3f}{np.mean(genuine):+10.3f}"
              f"{max(imposter):+9.3f}{min(genuine) - max(imposter):+8.3f}")


def main():
    if "--recheck" in sys.argv:
        recheck()
        return

    sweep()


if __name__ == "__main__":
    main()
