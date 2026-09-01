"""
Temporary lab: does the optional neural backend actually earn its 26 MB?

Same corpus, same held-out background voices and the same operating-point
report as `_spk_lab.py`, so the two backends are directly comparable.
Also times a single embedding, because a speaker check that costs a
second per command is not worth having.
"""

import os
import sys
import time

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import onnxruntime as ort

import _spk_lab as lab

from voice import dsp, fbank

MODEL = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "models", "voxceleb_resnet34_LM.onnx",
)

_SESSION = None


def session():
    global _SESSION

    if _SESSION is None:
        options = ort.SessionOptions()
        options.intra_op_num_threads = 4

        _SESSION = ort.InferenceSession(
            MODEL, options, providers=["CPUExecutionProvider"]
        )

    return _SESSION


def embed(samples):
    feats = fbank.features(samples)[None, :, :]

    embedding = session().run(["embs"], {"feats": feats})[0][0]

    return embedding / (np.linalg.norm(embedding) + 1e-12)


def audible(entry, mode):
    """Which part of the clip the network is shown."""
    samples, report = entry

    if mode == "full" or not report.active.any():
        return samples

    marks = np.flatnonzero(report.active)

    if mode == "trim":
        start = marks[0] * dsp.HOP
        stop = min(marks[-1] * dsp.HOP + dsp.FRAME, samples.size)

        return samples[start:stop]

    pieces = [
        samples[index * dsp.HOP:index * dsp.HOP + dsp.HOP] for index in marks
    ]

    return np.concatenate(pieces) if pieces else samples


def run(mode="trim"):
    print(f"\nneural backend, audio: {mode}")

    eval_corpus = lab.load(lab.EVAL)
    bg_corpus = lab.load(lab.BACKGROUND)

    table = {
        voice: {tag: embed(audible(entry, mode))
                for tag, entry in clips.items()}
        for voice, clips in eval_corpus.items()
    }

    background = np.array([
        embed(audible(entry, mode))
        for clips in bg_corpus.values() for entry in clips.values()
    ])

    def enrol(voice):
        pooled = sum(table[voice][tag] for tag in lab.ENROL)

        return pooled / (np.linalg.norm(pooled) + 1e-12)

    profiles = {voice: enrol(voice) for voice in lab.EVAL}

    centre, whitener = lab.fit_whitener(background, reg=0.05)

    clean = {
        voice: {tag: lab.project(one, centre, whitener)
                for tag, one in clips.items()}
        for voice, clips in table.items()
    }
    clean_profile = {
        voice: lab.project(profiles[voice], centre, whitener)
        for voice in lab.EVAL
    }
    cohort = np.array([lab.project(one, centre, whitener)
                       for one in background])

    import itertools

    pairs, others = lab.trials()

    def show(name, score):
        lab.report(name, [score(*one) for one in pairs],
                   [score(*one) for one in others])

    show("cosine", lambda a, b, t: lab._cosine(profiles[a], table[b][t]))
    show("whitened cosine",
         lambda a, b, t: lab._cosine(clean_profile[a], clean[b][t]))
    show("whitened + s-norm", lambda a, b, t: lab.snorm(
        lab._cosine(clean_profile[a], clean[b][t]),
        clean_profile[a], clean[b][t], cohort,
    ))

    return eval_corpus


def timing(eval_corpus):
    samples = eval_corpus[lab.EVAL[0]]["en_b"][0]

    embed(samples[:16000])

    for seconds in (1.0, 2.0, 4.0, 6.0):
        clip = samples[:int(seconds * dsp.RATE)]

        marks = []

        for _ in range(5):
            start = time.perf_counter()
            embed(clip)
            marks.append(time.perf_counter() - start)

        print(f"  {seconds:.0f}s of audio -> {np.median(marks) * 1000:6.1f} ms")


def main():
    corpus = run("trim")
    run("full")
    run("gate")

    print("\nembedding cost (median of 5)")
    timing(corpus)


if __name__ == "__main__":
    main()
