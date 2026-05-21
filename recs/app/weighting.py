import numpy as np
from typing import Dict

DEFAULT_WEIGHTS = {
    "tempo": 1.0, "energy": 1.0, "danceability": 1.0, "valence": 1.0,
    "acousticness": 1.0, "instrumentalness": 1.0, "speechiness": 1.0,
    "loudness": 1.0, "key": 0.5, "mode": 0.5,
}


class FeatureWeighting:
    def __init__(self, weights: Dict[str, float] = None):
        self.weights = weights or DEFAULT_WEIGHTS.copy()
        self.feature_order = list(DEFAULT_WEIGHTS.keys())

    def apply(self, vec: np.ndarray) -> np.ndarray:
        w = np.array([self.weights[f] for f in self.feature_order])
        return vec * w if vec.ndim == 1 else vec * w.reshape(1, -1)

    def update_weight(self, name: str, value: float):
        if name not in self.weights:
            raise ValueError(f"Unknown feature: {name}")
        self.weights[name] = value

    def set_weights(self, weights: Dict[str, float]):
        for k, v in weights.items():
            self.update_weight(k, v)


weighting = FeatureWeighting()
