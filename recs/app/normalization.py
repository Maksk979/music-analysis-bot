# normalization.py
import numpy as np
from sklearn.preprocessing import MinMaxScaler
from typing import List, Optional
import pickle

class FeatureNormalizer:
    def __init__(self):
        self.scaler = MinMaxScaler()
        self.fitted = False
    
    def fit(self, features_matrix: np.ndarray):
        """Обучает нормализатор на матрице признаков"""
        self.scaler.fit(features_matrix)
        self.fitted = True
    
    def transform(self, features_matrix: np.ndarray) -> np.ndarray:
        """Нормализует признаки"""
        if not self.fitted:
            raise ValueError("Normalizer not fitted. Call fit() first.")
        # Обработка выбросов: ограничиваем значения в пределах [0,1] после масштабирования
        normalized = self.scaler.transform(features_matrix)
        # Клиппинг выбросов (если вдруг вышли за пределы из-за новых данных)
        normalized = np.clip(normalized, 0.0, 1.0)
        return normalized
    
    def fit_transform(self, features_matrix: np.ndarray) -> np.ndarray:
        self.fit(features_matrix)
        return self.transform(features_matrix)
    
    def handle_missing(self, features_matrix: np.ndarray, strategy: str = "median") -> np.ndarray:
        """Заполнение пропущенных значений"""
        if strategy == "median":
            col_medians = np.nanmedian(features_matrix, axis=0)
            inds = np.where(np.isnan(features_matrix))
            features_matrix[inds] = np.take(col_medians, inds[1])
        elif strategy == "mean":
            col_means = np.nanmean(features_matrix, axis=0)
            inds = np.where(np.isnan(features_matrix))
            features_matrix[inds] = np.take(col_means, inds[1])
        elif strategy == "zero":
            features_matrix = np.nan_to_num(features_matrix, nan=0.0)
        return features_matrix
    
    def save(self, path: str):
        with open(path, 'wb') as f:
            pickle.dump(self.scaler, f)
    
    def load(self, path: str):
        with open(path, 'rb') as f:
            self.scaler = pickle.load(f)
        self.fitted = True

# Глобальный экземпляр
normalizer = FeatureNormalizer()