# weighting.py
import numpy as np
from typing import Dict, List

# Порядок признаков: tempo, energy, danceability, valence, acousticness,
# instrumentalness, speechiness, loudness, key, mode
DEFAULT_WEIGHTS = {
    "tempo": 1.0,
    "energy": 1.0,
    "danceability": 1.0,
    "valence": 1.0,
    "acousticness": 1.0,
    "instrumentalness": 1.0,
    "speechiness": 1.0,
    "loudness": 1.0,
    "key": 0.5,      # ключ и лад менее важны
    "mode": 0.5,
}

class FeatureWeighting:
    def __init__(self, weights: Dict[str, float] = None):
        self.weights = weights or DEFAULT_WEIGHTS.copy()
        self.feature_order = list(DEFAULT_WEIGHTS.keys())
    
    def apply(self, feature_vector: np.ndarray) -> np.ndarray:
        """Применяет веса к вектору признаков (1D или 2D)"""
        weight_array = np.array([self.weights[f] for f in self.feature_order])
        if feature_vector.ndim == 1:
            return feature_vector * weight_array
        else:
            return feature_vector * weight_array.reshape(1, -1)
    
    def update_weight(self, feature_name: str, weight: float):
        if feature_name in self.weights:
            self.weights[feature_name] = weight
        else:
            raise ValueError(f"Unknown feature: {feature_name}")
    
    def set_weights(self, weights: Dict[str, float]):
        for k, v in weights.items():
            self.update_weight(k, v)

weighting = FeatureWeighting()