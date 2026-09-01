"""
Temporary lab: pick the speaker-scoring rule by measuring it.

Builds a small corpus with Edge TTS - several distinct voices, each
reading English, Romanized Indic and native-script text - then scores
every enrol/test pair with a few candidate rules and reports the equal
error rate. A TTS voice is not a human, so the absolute numbers are
optimistic; what this decides is which rule and which feature set to
ship, and it is the same experiment `calibrate_speaker.py` runs on the
Boss's real microphone.

The background voices are held out: nothing in BACKGROUND appears in
EVAL, so the whitening and the score-normalisation cohort are never
fitted on a voice they are later tested on.
"""

import asyncio
import itertools
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import edge_tts

from voice import dsp, vad

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_spk_out")
os.makedirs(OUT, exist_ok=True)

EVAL = [
    "en-US-AriaNeural",
    "en-US-JennyNeural",
    "en-US-GuyNeural",
    "en-GB-SoniaNeural",
    "en-GB-RyanNeural",
    "en-IN-NeerjaNeural",
    "en-IN-PrabhatNeural",
    "te-IN-ShrutiNeural",
    "te-IN-MohanNeural",
    "hi-IN-SwaraNeural",
    "hi-IN-MadhurNeural",
]

BACKGROUND = [
    "en-AU-NatashaNeural",
    "en-CA-ClaraNeural",
    "en-CA-LiamNeural",
    "en-GB-LibbyNeural",
    "en-GB-ThomasNeural",
    "en-HK-SamNeural",
    "en-HK-YanNeural",
    "en-IE-ConnorNeural",
    "en-IE-EmilyNeural",
    "en-KE-AsiliaNeural",
    "en-KE-ChilembaNeural",
    "en-NG-AbeoNeural",
    "en-NG-EzinneNeural",
    "en-NZ-MitchellNeural",
    "en-NZ-MollyNeural",
    "en-PH-JamesNeural",
    "en-PH-RosaNeural",
    "en-SG-LunaNeural",
    "en-SG-WayneNeural",
    "en-ZA-LeahNeural",
    "en-ZA-LukeNeural",
    "en-US-EricNeural",
    "en-US-MichelleNeural",
    "en-US-RogerNeural",
    "ta-IN-PallaviNeural",
    "ta-IN-ValluvarNeural",
    "kn-IN-SapnaNeural",
    "ml-IN-MidhunNeural",
    "mr-IN-AarohiNeural",
    "bn-IN-TanishaaNeural",
    "gu-IN-DhwaniNeural",
    "ur-IN-GulNeural",
]

ENGLISH_A = (
    "Hey Friday, what time is it in London right now, and is it raining "
    "there this evening?"
)
ENGLISH_B = (
    "Friday, tell me one interesting fact about space, and remind me to "
    "call the office tomorrow morning."
)
ENGLISH_C = (
    "The meeting was moved to four o'clock, so I will finish the project "
    "notes before I leave the office."
)
ROMAN = (
    "Friday naaku oka help kavali, ivala weather enti, mujhe kal subah "
    "jaldi uthna hai, alarm laga do."
)
TELUGU = (
    "ఫ్రైడే నాకు ఒక సహాయం కావాలి, ఇవాళ వాతావరణం ఎలా ఉంది, "
    "రేపు కాలేజీకి వెళ్ళాలి."
)
HINDI = (
    "फ्राइडे मुझे एक मदद चाहिए, आज मौसम कैसा है, "
    "कल सुबह जल्दी उठना है।"
)

ENROL = ("en_a", "roman")
TEST = ("en_b", "native")

# Measured, not assumed: the neural backend scores these two groups as the
# same person across locales (0.79-0.92 cosine, as high as its genuine
# pairs), and Microsoft plainly recorded one voice talent per group for
# en-IN, hi-IN and te-IN. Counting those pairs as impostors would be
# scoring the system wrong for being right, so they are dropped from the
# trial list rather than treated as either genuine or imposter.
FAMILIES = (
    ("en-IN-NeerjaNeural", "hi-IN-SwaraNeural", "te-IN-ShrutiNeural"),
    ("en-IN-PrabhatNeural", "hi-IN-MadhurNeural", "te-IN-MohanNeural"),
)


def identity(voice):
    for family in FAMILIES:
        if voice in family:
            return family[0]

    return voice


def trials():
    """(same-speaker pairs, different-speaker pairs) as (profile, test, tag)."""
    genuine = [(voice, voice, tag) for voice in EVAL for tag in TEST]

    imposter = [
        (left, right, tag)
        for left, right in itertools.permutations(EVAL, 2)
        for tag in TEST
        if identity(left) != identity(right)
    ]

    return genuine, imposter


def clips_for(voice):
    """Four clips per voice, so a same-speaker pair spans two languages."""
    native = TELUGU if voice.startswith("te-") else (
        HINDI if voice.startswith("hi-") else ENGLISH_C
    )

    return [("en_a", ENGLISH_A), ("en_b", ENGLISH_B),
            ("roman", ROMAN), ("native", native)]


def build(voices):
    for voice in voices:
        for tag, text in clips_for(voice):
            path = os.path.join(OUT, f"{voice}__{tag}.mp3")

            if os.path.exists(path) and os.path.getsize(path) > 0:
                continue

            asyncio.run(
                edge_tts.Communicate(text=text, voice=voice).save(path)
            )

            print(f"  built {os.path.basename(path)}")


def load(voices):
    """{voice: {tag: (samples, report)}}."""
    corpus = {}

    for voice in voices:
        corpus[voice] = {}

        for tag, _ in clips_for(voice):
            samples = dsp.load_file(os.path.join(OUT, f"{voice}__{tag}.mp3"))
            report = vad.inspect(samples)

            corpus[voice][tag] = (samples, report)

            if not report.ok:
                print(f"  !! VAD rejected {voice} {tag}: {report.reason}")

    return corpus


# --------------------------------------------------------------- features


def _frames(report, masked=True):
    """VAD-masked cepstra and their deltas."""
    cepstra = dsp.mfcc(dsp.log_mel(dsp.power_spectrum(report.windows)))[:, 1:]
    moving = dsp.deltas(cepstra)

    mask = report.active if masked else np.ones(len(cepstra), dtype=bool)

    if mask.sum() < 20:
        mask = np.ones(len(cepstra), dtype=bool)

    return cepstra[mask], moving[mask]


def vector(entry, kind="mean+delta", masked=True):
    """One fixed-length description of a whole utterance."""
    cepstra, moving = _frames(entry[1], masked)

    parts = [cepstra.mean(axis=0)]

    if "delta" in kind:
        parts.append(moving.mean(axis=0))

    if "std" in kind:
        parts.append(np.log(cepstra.std(axis=0) + 1e-6))

    if "dstd" in kind:
        parts.append(np.log(moving.std(axis=0) + 1e-6))

    return np.concatenate(parts)


def stats(entry, masked=True):
    """Per-dimension mean and variance - what the old rules compare."""
    cepstra, moving = _frames(entry[1], masked)
    features = np.concatenate([cepstra, moving], axis=1)

    return features.mean(axis=0), features.var(axis=0) + 1e-6


# ------------------------------------------------------------ the backend


def _cosine(left, right):
    return float(
        left @ right / (np.linalg.norm(left) * np.linalg.norm(right) + 1e-12)
    )


def fit_whitener(background, reg=0.1):
    """
    Mean and inverse square root covariance of the background voices.

    This is the classical within-class-covariance step: it takes the
    directions along which *any* two utterances differ and shrinks them,
    so what is left is mostly speaker.
    """
    mean = background.mean(axis=0)
    centred = background - mean

    cov = centred.T @ centred / float(len(centred))
    cov += reg * np.trace(cov) / len(cov) * np.eye(len(cov))

    values, vectors = np.linalg.eigh(cov)
    values = np.maximum(values, 1e-9)

    return mean, (vectors * values ** -0.5) @ vectors.T


def project(raw, mean, whitener):
    """Whiten, then put on the unit sphere so only direction is compared."""
    moved = whitener @ (raw - mean)

    return moved / (np.linalg.norm(moved) + 1e-12)


def snorm(score, left, right, cohort, top=20):
    """
    Adaptive symmetric score normalisation.

    The same raw cosine means different things for a voice that sits close
    to everybody and a voice that sits far from everybody; dividing by how
    each side scores against a cohort of strangers removes that.
    """
    near_left = np.sort(cohort @ left)[-top:]
    near_right = np.sort(cohort @ right)[-top:]

    return 0.5 * (
        (score - near_left.mean()) / (near_left.std() + 1e-9)
        + (score - near_right.mean()) / (near_right.std() + 1e-9)
    )


# ------------------------------------------------------------- references


def rule_scaled_cosine(profile, test):
    """Best of the first round: each dimension scaled by the enrolled std."""
    scale = np.sqrt(profile[1])

    return _cosine(profile[0] / scale, test[0] / scale)


def rule_kl(profile, test):
    """Symmetric KL between two diagonal Gaussians, squashed."""
    gap = (profile[0] - test[0]) ** 2

    divergence = 0.5 * float(
        np.sum(profile[1] / test[1] + test[1] / profile[1] - 2.0)
        + np.sum(gap * (1.0 / profile[1] + 1.0 / test[1]))
    )

    return float(np.exp(-divergence / 40.0))


# ------------------------------------------------------------- evaluation


def eer(genuine, imposter):
    """Equal error rate, plus the threshold that produces it."""
    marks = sorted(genuine + imposter)

    best = (1.0, 0.0, 1.0, 0.0)

    for index in range(len(marks) + 1):
        cut = marks[index] if index < len(marks) else marks[-1] + 1e-9

        frr = sum(1 for score in genuine if score < cut) / float(len(genuine))
        far = sum(1 for score in imposter if score >= cut) / float(
            len(imposter)
        )

        if abs(far - frr) < abs(best[2] - best[3]):
            best = (max(far, frr), cut, far, frr)

    return best


def report(name, genuine, imposter):
    """
    Operating points, not a single number.

    With only 22 genuine trials the equal error rate can only land on
    multiples of 4.5%, so it cannot tell two good rules apart. What
    matters for this feature is how many strangers get in at a threshold
    that still lets the Boss in, so that is what is printed.
    """
    good = np.sort(np.asarray(genuine, dtype=float))
    bad = np.asarray(imposter, dtype=float)

    strict = float((bad >= good[0]).mean())
    relaxed = float((bad >= good[int(len(good) * 0.05)]).mean())
    blocked = float((good < bad.max() + 1e-12).mean())

    spread = np.sqrt(0.5 * (good.var() + bad.var())) + 1e-12
    margin = float((good.mean() - bad.mean()) / spread)

    rate, cut, far, frr = eer(list(genuine), list(imposter))

    print(
        f"  {name:<24} d' {margin:4.2f}  "
        f"FAR@FRR0 {strict * 100:5.1f}%  FAR@FRR5 {relaxed * 100:5.1f}%  "
        f"FRR@FAR0 {blocked * 100:5.1f}%  EER {rate * 100:4.1f}% at {cut:+7.3f}"
    )

    return margin


def sweep(eval_corpus, bg_corpus, kind, masked=True):
    """Raw cosine, whitened cosine and whitened cosine + s-norm."""
    print(f"\n{kind}{'' if masked else '  (no VAD mask)'}"
          f"  dim {len(vector(eval_corpus[EVAL[0]]['en_a'], kind, masked))}")

    raw = {
        voice: {
            tag: vector(entry, kind, masked)
            for tag, entry in clips.items()
        }
        for voice, clips in eval_corpus.items()
    }

    background = np.array([
        vector(entry, kind, masked)
        for clips in bg_corpus.values() for entry in clips.values()
    ])

    centre, whitener = fit_whitener(background)
    cohort = np.array([project(one, centre, whitener) for one in background])

    def enrol(table, voice):
        pooled = sum(table[voice][tag] for tag in ENROL) / float(len(ENROL))

        return pooled / (np.linalg.norm(pooled) + 1e-12)

    plain = {voice: enrol(raw, voice) for voice in EVAL}

    clean = {
        voice: {tag: project(one, centre, whitener)
                for tag, one in clips.items()}
        for voice, clips in raw.items()
    }
    clean_profile = {voice: enrol(clean, voice) for voice in EVAL}

    pairs, others = trials()

    def run(name, score):
        report(
            name,
            [score(a, b, t) for a, b, t in pairs],
            [score(a, b, t) for a, b, t in others],
        )

    run("cosine", lambda a, b, t: _cosine(plain[a], raw[b][t]))
    run("whitened cosine",
        lambda a, b, t: _cosine(clean_profile[a], clean[b][t]))
    run("whitened + s-norm", lambda a, b, t: snorm(
        _cosine(clean_profile[a], clean[b][t]),
        clean_profile[a], clean[b][t], cohort,
    ))


def references(eval_corpus):
    """The two survivors of the first round, for comparison."""
    print("\nreference rules on per-dimension statistics")

    table = {
        voice: {tag: stats(entry) for tag, entry in clips.items()}
        for voice, clips in eval_corpus.items()
    }

    def profile(voice):
        means = [table[voice][tag][0] for tag in ENROL]
        variances = [table[voice][tag][1] for tag in ENROL]

        return np.mean(means, axis=0), np.mean(variances, axis=0)

    profiles = {voice: profile(voice) for voice in EVAL}

    pairs, others = trials()

    for name, rule in (("scaled-cosine", rule_scaled_cosine),
                       ("sym-KL", rule_kl)):
        report(
            name,
            [rule(profiles[a], table[b][t]) for a, b, t in pairs],
            [rule(profiles[a], table[b][t]) for a, b, t in others],
        )


# --------------------------------------------------------------- GMM-UBM


def _log_probs(ubm, data):
    """log w_k + log N(x | mu_k, var_k) for every frame and component."""
    weights, means, variances = ubm

    constant = -0.5 * (
        means.shape[1] * np.log(2.0 * np.pi) + np.log(variances).sum(axis=1)
    )

    scaled = data / variances[:, None, :]

    quadratic = (
        (data ** 2) @ (1.0 / variances).T
        - 2.0 * data @ (means / variances).T
        + ((means ** 2) / variances).sum(axis=1)
    )

    del scaled

    return np.log(weights) + constant - 0.5 * quadratic


def _logsumexp(values):
    top = values.max(axis=1, keepdims=True)

    return top[:, 0] + np.log(np.exp(values - top).sum(axis=1))


def train_ubm(data, comps=32, rounds=30, seed=0):
    """Plain diagonal-covariance EM. The UBM is a map of speech, not of
    any one speaker."""
    rng = np.random.default_rng(seed)

    means = data[rng.choice(len(data), comps, replace=False)].copy()
    variances = np.tile(data.var(axis=0) + 1e-3, (comps, 1))
    weights = np.full(comps, 1.0 / comps)

    floor = 0.01 * (data.var(axis=0) + 1e-6)

    for _ in range(rounds):
        logs = _log_probs((weights, means, variances), data)
        posterior = np.exp(logs - _logsumexp(logs)[:, None])

        mass = posterior.sum(axis=0) + 1e-9

        means = (posterior.T @ data) / mass[:, None]
        variances = np.maximum(
            (posterior.T @ (data ** 2)) / mass[:, None] - means ** 2, floor
        )
        weights = mass / mass.sum()

    return weights, means, variances


def adapt(ubm, data, relevance=10.0):
    """
    MAP adaptation of the component means towards this utterance.

    Where the utterance has evidence for a sound the mean moves; where it
    has none it stays on the universal model. That is what makes two
    utterances comparable even when they say completely different words.
    """
    weights, means, variances = ubm

    logs = _log_probs(ubm, data)
    posterior = np.exp(logs - _logsumexp(logs)[:, None])

    mass = posterior.sum(axis=0)
    centre = (posterior.T @ data) / np.maximum(mass, 1e-9)[:, None]

    share = (mass / (mass + relevance))[:, None]

    return share * centre + (1.0 - share) * means


def supervector(ubm, moved):
    """The adapted means, weighted and normalised - one vector per clip."""
    weights, means, variances = ubm

    stacked = (
        np.sqrt(weights)[:, None] * (moved - means) / np.sqrt(variances)
    )

    flat = stacked.ravel()

    return flat / (np.linalg.norm(flat) + 1e-12)


def llr(ubm, moved, data):
    """Classic frame-level log likelihood ratio, speaker against the UBM."""
    weights, _, variances = ubm

    speaker = _logsumexp(_log_probs((weights, moved, variances), data))
    universal = _logsumexp(_log_probs(ubm, data))

    return float(np.mean(speaker - universal))


def gmm_frames(entry, masked=True):
    cepstra, moving = _frames(entry[1], masked)

    return np.concatenate([cepstra, moving], axis=1)


def fit_subspace(background, keep=48, reg=0.1):
    """PCA whitening of the background supervectors - i-vector lite."""
    mean = background.mean(axis=0)
    centred = background - mean

    _, values, basis = np.linalg.svd(centred, full_matrices=False)
    scale = values / np.sqrt(len(centred))

    keep = min(keep, len(scale))
    floor = reg * float(scale[:keep].mean())

    return mean, basis[:keep], 1.0 / (scale[:keep] + floor)


def project_sub(raw, model):
    mean, basis, inverse = model

    moved = ((raw - mean) @ basis.T) * inverse

    return moved / (np.linalg.norm(moved) + 1e-12)


def gmm_sweep(eval_corpus, bg_corpus, comps=32, relevance=10.0):
    print(f"\nGMM-UBM  {comps} components, relevance {relevance:g}")

    bg_frames = [gmm_frames(entry) for clips in bg_corpus.values()
                 for entry in clips.values()]

    ubm = train_ubm(np.concatenate(bg_frames, axis=0), comps=comps)

    background = np.array([
        supervector(ubm, adapt(ubm, one, relevance)) for one in bg_frames
    ])

    subspace = fit_subspace(background)
    cohort = np.array([project_sub(one, subspace) for one in background])

    frames = {
        voice: {tag: gmm_frames(entry) for tag, entry in clips.items()}
        for voice, clips in eval_corpus.items()
    }

    tests = {
        voice: {
            tag: adapt(ubm, frames[voice][tag], relevance) for tag in TEST
        }
        for voice in EVAL
    }

    enrolled = {
        voice: adapt(
            ubm,
            np.concatenate([frames[voice][tag] for tag in ENROL], axis=0),
            relevance,
        )
        for voice in EVAL
    }

    plain = {v: supervector(ubm, m) for v, m in enrolled.items()}
    clean = {v: project_sub(plain[v], subspace) for v in EVAL}

    test_plain = {
        v: {t: supervector(ubm, m) for t, m in row.items()}
        for v, row in tests.items()
    }
    test_clean = {
        v: {t: project_sub(one, subspace) for t, one in row.items()}
        for v, row in test_plain.items()
    }

    pairs, others = trials()

    def run(name, score):
        report(name,
               [score(*one) for one in pairs],
               [score(*one) for one in others])

    run("supervector cosine",
        lambda a, b, t: _cosine(plain[a], test_plain[b][t]))
    run("whitened supervector",
        lambda a, b, t: _cosine(clean[a], test_clean[b][t]))
    run("whitened + s-norm", lambda a, b, t: snorm(
        _cosine(clean[a], test_clean[b][t]),
        clean[a], test_clean[b][t], cohort,
    ))
    run("frame LLR",
        lambda a, b, t: llr(ubm, enrolled[a], frames[b][t]))


def main():
    print("Building the corpus...")
    build(EVAL)
    build(BACKGROUND)

    print("Loading...")
    eval_corpus = load(EVAL)
    bg_corpus = load(BACKGROUND)

    references(eval_corpus)

    for kind in ("mean", "mean+delta", "mean+std", "mean+delta+std",
                 "mean+delta+std+dstd"):
        sweep(eval_corpus, bg_corpus, kind)

    sweep(eval_corpus, bg_corpus, "mean+delta+std", masked=False)

    for comps in (16, 32, 64):
        gmm_sweep(eval_corpus, bg_corpus, comps)


if __name__ == "__main__":
    main()
