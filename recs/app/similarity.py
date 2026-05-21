import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from scipy.stats import pearsonr
from typing import List, Tuple
from .normalization import normalizer
from .weighting import weighting


def extract_feature_vector(features, normalize: bool = True, apply_weights: bool = True) -> np.ndarray:
    vec = np.array([[
        features.tempo or 0.0,
        features.energy or 0.0,
        features.danceability or 0.0,
        features.valence or 0.0,
        features.acousticness or 0.0,
        features.instrumentalness or 0.0,
        features.speechiness or 0.0,
        features.loudness or 0.0,
        float(features.key or 0),
        float(features.mode or 0),
    ]])
    if np.any(np.isnan(vec)):
        vec = normalizer.handle_missing(vec, strategy="median")
    if normalize and normalizer.fitted:
        vec = normalizer.transform(vec)
    if apply_weights:
        vec = weighting.apply(vec)
    return vec


def cosine_similarity_score(v1: np.ndarray, v2: np.ndarray) -> float:
    return float(cosine_similarity(v1, v2)[0][0])


def euclidean_distance_score(v1: np.ndarray, v2: np.ndarray) -> float:
    return 1.0 / (1.0 + np.linalg.norm(v1 - v2))


def pearson_correlation_score(v1: np.ndarray, v2: np.ndarray) -> float:
    with np.errstate(divide='ignore', invalid='ignore'):
        corr, _ = pearsonr(v1.flatten(), v2.flatten())
        return 0.0 if np.isnan(corr) else float(corr)


def compute_similarity(v1: np.ndarray, v2: np.ndarray, method: str = "cosine") -> float:
    if method == "cosine":
        return cosine_similarity_score(v1, v2)
    elif method == "euclidean":
        return euclidean_distance_score(v1, v2)
    elif method == "pearson":
        return pearson_correlation_score(v1, v2)
    raise ValueError(f"Unknown method: {method}")


def get_top_similar(
    target_vec: np.ndarray,
    target_id: str,
    all_features: List,
    method: str = "cosine",
    limit: int = 10,
) -> List[Tuple[str, float]]:
    scores = []
    for feats in all_features:
        if feats.audio_file_id == target_id:
            continue
        vec = extract_feature_vector(feats)
        scores.append((feats.audio_file_id, compute_similarity(target_vec, vec, method)))
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:limit]
