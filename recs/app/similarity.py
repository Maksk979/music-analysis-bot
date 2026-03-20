import numpy as np
from sklearn.metrics.pairwise import cosine_similarity
from scipy.stats import pearsonr
from typing import List, Tuple

def extract_feature_vector(features) -> np.ndarray:
    """Преобразует объект фичей в numpy массив"""
    return np.array([[
        features.tempo,
        features.energy,
        features.danceability,
        features.valence,
        features.acousticness,
        features.instrumentalness,
        features.speechiness,
        features.loudness,
        features.key,
        features.mode
    ]]).reshape(1, -1)

def cosine_similarity_score(vec1: np.ndarray, vec2: np.ndarray) -> float:
    return float(cosine_similarity(vec1, vec2)[0][0])

def euclidean_distance_score(vec1: np.ndarray, vec2: np.ndarray) -> float:
    # Преобразуем расстояние в схожесть (чем меньше расстояние, тем выше схожесть)
    dist = np.linalg.norm(vec1 - vec2)
    return 1.0 / (1.0 + dist)

def pearson_correlation_score(vec1: np.ndarray, vec2: np.ndarray) -> float:
    # Убираем предупреждения о константных данных
    with np.errstate(divide='ignore', invalid='ignore'):
        corr, _ = pearsonr(vec1.flatten(), vec2.flatten())
        if np.isnan(corr):
            return 0.0
        return float(corr)

def compute_similarity(vec1: np.ndarray, vec2: np.ndarray, method: str = "cosine") -> float:
    if method == "cosine":
        return cosine_similarity_score(vec1, vec2)
    elif method == "euclidean":
        return euclidean_distance_score(vec1, vec2)
    elif method == "pearson":
        return pearson_correlation_score(vec1, vec2)
    else:
        raise ValueError(f"Unknown method: {method}")

def get_top_similar(
    target_vec: np.ndarray,
    target_id: int,
    all_features: List,
    method: str = "cosine",
    limit: int = 10
) -> List[Tuple[int, float]]:
    scores = []
    for feats in all_features:
        if feats.audio_file_id == target_id:
            continue
        vec = extract_feature_vector(feats)
        score = compute_similarity(target_vec, vec, method)
        scores.append((feats.audio_file_id, score))
    
    # Сортируем по убыванию схожести
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores[:limit]