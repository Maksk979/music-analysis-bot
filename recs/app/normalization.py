import numpy as np
from sklearn.preprocessing import MinMaxScaler
import pickle


class FeatureNormalizer:
    def __init__(self):
        self.scaler = MinMaxScaler()
        self.fitted = False

    def fit(self, matrix: np.ndarray):
        self.scaler.fit(matrix)
        self.fitted = True

    def transform(self, matrix: np.ndarray) -> np.ndarray:
        if not self.fitted:
            raise ValueError("Normalizer not fitted.")
        return np.clip(self.scaler.transform(matrix), 0.0, 1.0)

    def fit_transform(self, matrix: np.ndarray) -> np.ndarray:
        self.fit(matrix)
        return self.transform(matrix)

    def handle_missing(self, matrix: np.ndarray, strategy: str = "median") -> np.ndarray:
        if strategy == "median":
            medians = np.nanmedian(matrix, axis=0)
            inds = np.where(np.isnan(matrix))
            matrix[inds] = np.take(medians, inds[1])
        elif strategy == "zero":
            matrix = np.nan_to_num(matrix, nan=0.0)
        return matrix

    def save(self, path: str):
        with open(path, 'wb') as f:
            pickle.dump(self.scaler, f)

    def load(self, path: str):
        with open(path, 'rb') as f:
            self.scaler = pickle.load(f)
        self.fitted = True


normalizer = FeatureNormalizer()
