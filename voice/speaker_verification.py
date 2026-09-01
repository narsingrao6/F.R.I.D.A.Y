"""
Speaker verification using VoxCeleb ResNet34 ONNX model.
Extracts Kaldi-compatible fbank features and computes cosine similarity.
"""

import os
import numpy as np
import onnxruntime as ort

from voice import dsp, fbank

# Paths
_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MODEL_PATH = os.path.join(_BASE_DIR, "models", "voxceleb_resnet34_LM.onnx")
PROFILE_PATH = os.path.join(_BASE_DIR, "speaker_profile.npy")

# Tunable threshold for the cosine similarity.
# For raw cosine similarity on VoxCeleb ResNet34, genuine trials often sit
# between 0.40 and 0.80. A threshold of 0.45 is a balanced starting point.
SPEAKER_THRESHOLD = 0.45

_SESSION = None

def _session():
    global _SESSION
    if _SESSION is None:
        options = ort.SessionOptions()
        # Keep threads low to prevent background tasks from hogging resources
        options.intra_op_num_threads = 2
        _SESSION = ort.InferenceSession(MODEL_PATH, options, providers=["CPUExecutionProvider"])
    return _SESSION


def embed(samples):
    """
    Generate a normalized embedding from a raw audio clip.
    """
    feats = fbank.features(samples)[None, :, :]
    embedding = _session().run(["embs"], {"feats": feats})[0][0]
    return embedding / (np.linalg.norm(embedding) + 1e-12)


def verify_samples(samples, report):
    """
    Verify an utterance against the enrolled speaker profile.
    
    Uses the VAD report to trim silence before embedding.
    
    Returns:
        (is_authorized, confidence_score)
    """
    if not os.path.exists(PROFILE_PATH):
        print("F.R.I.D.A.Y. SECURITY: No speaker profile found. Please run enroll_voice.py.")
        return False, 0.0

    marks = np.flatnonzero(report.active)
    if marks.size == 0:
        return False, 0.0

    start = marks[0] * dsp.HOP
    stop = min(marks[-1] * dsp.HOP + dsp.FRAME, samples.size)
    audible = samples[start:stop]
    
    # Needs to be at least a quarter of a second for a reliable embedding
    if len(audible) < dsp.RATE * 0.25:
        return False, 0.0

    query_emb = embed(audible)
    profile_emb = np.load(PROFILE_PATH)
    
    score = float(np.dot(query_emb, profile_emb))
    print(f"[DEBUG] Speaker Verification Score: {score:.3f} (Threshold: {SPEAKER_THRESHOLD})")
    
    return score >= SPEAKER_THRESHOLD, score


def enroll(samples_list):
    """
    Takes a list of audio sample arrays (16kHz mono float32), embeds them, 
    and averages them to create a robust authorized speaker profile.
    """
    embeddings = [embed(s) for s in samples_list]
    
    # Average the embeddings
    pooled = np.sum(embeddings, axis=0)
    profile = pooled / (np.linalg.norm(pooled) + 1e-12)
    
    np.save(PROFILE_PATH, profile)
    return profile
