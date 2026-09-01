"""
Temporary lab: how short can the test utterance get?

The real failure mode is not a paragraph, it is "Friday, time enti?" -
about a second and a half of speech. This truncates every test clip and
re-measures, for the neural backend and for both candidate fallbacks, so
the choice is made on the length the Boss will actually speak.
"""

import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import _ort_lab as ort_lab
import _spk_lab as lab

from voice import dsp, vad

LENGTHS = (1.0, 1.5, 2.5, 4.0, None)


def cut(entry, seconds):
    """The first `seconds` of *voiced* audio, re-inspected."""
    samples, report = entry

    if seconds is None:
        return entry

    marks = np.flatnonzero(report.active)

    if not marks.size:
        return entry

    start = marks[0] * dsp.HOP
    clipped = samples[start:start + int(seconds * dsp.RATE)]

    return clipped, vad.inspect(clipped)


def main():
    eval_corpus = lab.load(lab.EVAL)
    bg_corpus = lab.load(lab.BACKGROUND)

    pairs, others = lab.trials()

    stats = {
        voice: {tag: lab.stats(entry) for tag, entry in clips.items()}
        for voice, clips in eval_corpus.items()
    }
    frames = {
        voice: {tag: lab.gmm_frames(entry) for tag, entry in clips.items()}
        for voice, clips in eval_corpus.items()
    }

    ubm = lab.train_ubm(
        np.concatenate(
            [lab.gmm_frames(entry) for clips in bg_corpus.values()
             for entry in clips.values()],
            axis=0,
        ),
        comps=16,
    )

    kl_profile = {
        voice: (
            np.mean([stats[voice][tag][0] for tag in lab.ENROL], axis=0),
            np.mean([stats[voice][tag][1] for tag in lab.ENROL], axis=0),
        )
        for voice in lab.EVAL
    }

    gsv_profile = {
        voice: lab.supervector(ubm, lab.adapt(
            ubm,
            np.concatenate([frames[voice][tag] for tag in lab.ENROL], axis=0),
        ))
        for voice in lab.EVAL
    }

    neural_profile = {}

    for voice in lab.EVAL:
        pooled = sum(
            ort_lab.embed(ort_lab.audible(eval_corpus[voice][tag], "trim"))
            for tag in lab.ENROL
        )

        neural_profile[voice] = pooled / np.linalg.norm(pooled)

    for seconds in LENGTHS:
        pieces = {
            voice: {tag: cut(eval_corpus[voice][tag], seconds)
                    for tag in lab.TEST}
            for voice in lab.EVAL
        }

        label = "whole clip" if seconds is None else f"{seconds:.1f}s"
        voiced = np.mean([
            pieces[v][t][1].voiced_seconds
            for v in lab.EVAL for t in lab.TEST
        ])

        print(f"\ntest audio: {label}  ({voiced:.2f}s voiced on average)")

        test_stats = {v: {t: lab.stats(pieces[v][t]) for t in lab.TEST}
                      for v in lab.EVAL}
        test_frames = {v: {t: lab.gmm_frames(pieces[v][t]) for t in lab.TEST}
                       for v in lab.EVAL}
        test_neural = {
            v: {t: ort_lab.embed(ort_lab.audible(pieces[v][t], "trim"))
                for t in lab.TEST}
            for v in lab.EVAL
        }

        def show(name, score):
            lab.report(name,
                       [score(*one) for one in pairs],
                       [score(*one) for one in others])

        show("mfcc sym-KL",
             lambda a, b, t: lab.rule_kl(kl_profile[a], test_stats[b][t]))
        show("mfcc scaled-cosine",
             lambda a, b, t: lab.rule_scaled_cosine(
                 kl_profile[a], test_stats[b][t]))
        show("GMM-UBM supervector", lambda a, b, t: lab._cosine(
            gsv_profile[a],
            lab.supervector(ubm, lab.adapt(ubm, test_frames[b][t])),
        ))
        show("neural cosine", lambda a, b, t: lab._cosine(
            neural_profile[a], test_neural[b][t]))


if __name__ == "__main__":
    main()
