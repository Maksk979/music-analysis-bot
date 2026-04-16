# model_manager.py
import numpy as np
import faiss
from sklearn.cluster import KMeans
from typing import List, Tuple
import os
from .database import AudioFeatures
from .normalization import normalizer
from .weighting import weighting

class RecommendationModel:
    def __init__(self, index_type: str = "cosine"):
        self.index_type = index_type  # "cosine", "euclidean", "pearson"
        self.index = None
        self.file_ids = []  # соответствует порядку в индексе
        self.feature_dim = 10
        self.kmeans = None
        self.cluster_labels = None
        
    def build_index(self, features_list: List[AudioFeatures]):
        """Строит FAISS индекс и кластеризует"""
        # Извлекаем матрицу признаков (n_samples x n_features)
        matrix = []
        file_ids = []
        for f in features_list:
            vec = np.array([
                f.tempo, f.energy, f.danceability, f.valence,
                f.acousticness, f.instrumentalness, f.speechiness,
                f.loudness, f.key, f.mode
            ])
            matrix.append(vec)
            file_ids.append(f.audio_file_id)
        
        matrix = np.array(matrix, dtype=np.float32)
        
        # Заполнение пропусков (если есть)
        if np.any(np.isnan(matrix)):
            matrix = normalizer.handle_missing(matrix, strategy="median")
        
        # Нормализация
        if not normalizer.fitted:
            matrix_norm = normalizer.fit_transform(matrix)
        else:
            matrix_norm = normalizer.transform(matrix)
        
        # Применение весов
        matrix_norm = weighting.apply(matrix_norm)
        
        # Построение индекса в зависимости от метода схожести
        if self.index_type == "cosine":
            # Для косинусной схожести используем inner product после L2 нормализации
            index = faiss.IndexFlatIP(self.feature_dim)
            # L2 нормализуем векторы
            faiss.normalize_L2(matrix_norm)
            index.add(matrix_norm)
        elif self.index_type == "euclidean":
            index = faiss.IndexFlatL2(self.feature_dim)
            index.add(matrix_norm)
        else:  # pearson – не поддерживается FAISS, оставляем None
            index = None
        
        self.index = index
        self.file_ids = file_ids
        self.matrix_norm = matrix_norm  # сохраняем для pearson или пересчета
        
        # Кластеризация (например, для предварительной фильтрации)
        if len(matrix_norm) > 10:
            n_clusters = min(20, len(matrix_norm) // 5)
            self.kmeans = KMeans(n_clusters=n_clusters, random_state=42)
            self.cluster_labels = self.kmeans.fit_predict(matrix_norm)
        else:
            self.cluster_labels = np.zeros(len(matrix_norm), dtype=int)
    
    def get_similar(self, target_vec: np.ndarray, target_id: int, method: str, limit: int = 10) -> List[Tuple[int, float]]:
        """Поиск похожих треков с использованием индекса или кластеризации"""
        # Нормализуем и взвешиваем целевой вектор
        target_vec = target_vec.reshape(1, -1).astype(np.float32)
        if normalizer.fitted:
            target_vec = normalizer.transform(target_vec)
        target_vec = weighting.apply(target_vec)
        
        # Для методов, поддерживаемых FAISS
        if method in ["cosine", "euclidean"] and self.index is not None:
            if method == "cosine":
                faiss.normalize_L2(target_vec)
                distances, indices = self.index.search(target_vec, limit + 1)
                # Для косинусной: similarity = distance (inner product), уже нормирован
                similarities = distances[0]
            else:  # euclidean
                distances, indices = self.index.search(target_vec, limit + 1)
                # Преобразуем L2 расстояние в схожесть: similarity = 1/(1+dist)
                similarities = 1.0 / (1.0 + distances[0])
            
            # Формируем результат, исключая целевой
            result = []
            for idx, sim in zip(indices[0], similarities):
                file_id = self.file_ids[idx]
                if file_id != target_id:
                    result.append((file_id, float(sim)))
                if len(result) == limit:
                    break
            return result
        
        else:
            # Для Пирсона или если индекс не построен – линейный поиск
            scores = []
            for i, file_id in enumerate(self.file_ids):
                if file_id == target_id:
                    continue
                vec = self.matrix_norm[i].reshape(1, -1)
                if method == "pearson":
                    from scipy.stats import pearsonr
                    corr, _ = pearsonr(target_vec.flatten(), vec.flatten())
                    score = corr if not np.isnan(corr) else 0.0
                else:
                    # fallback на косинус
                    from sklearn.metrics.pairwise import cosine_similarity
                    score = float(cosine_similarity(target_vec, vec)[0][0])
                scores.append((file_id, score))
            scores.sort(key=lambda x: x[1], reverse=True)
            return scores[:limit]
    
    def save(self, path: str):
        """Сохраняет модель на диск"""
        os.makedirs(path, exist_ok=True)
        if self.index:
            faiss.write_index(self.index, f"{path}/index.faiss")
        np.save(f"{path}/file_ids.npy", np.array(self.file_ids))
        np.save(f"{path}/matrix_norm.npy", self.matrix_norm)
        if self.kmeans:
            import joblib
            joblib.dump(self.kmeans, f"{path}/kmeans.joblib")
        normalizer.save(f"{path}/normalizer.pkl")
        # сохраняем веса
        import json
        with open(f"{path}/weights.json", 'w') as f:
            json.dump(weighting.weights, f)
    
    def load(self, path: str):
        """Загружает модель"""
        if os.path.exists(f"{path}/index.faiss"):
            self.index = faiss.read_index(f"{path}/index.faiss")
        self.file_ids = np.load(f"{path}/file_ids.npy", allow_pickle=True).tolist()
        self.matrix_norm = np.load(f"{path}/matrix_norm.npy")
        import joblib
        if os.path.exists(f"{path}/kmeans.joblib"):
            self.kmeans = joblib.load(f"{path}/kmeans.joblib")
        normalizer.load(f"{path}/normalizer.pkl")
        import json
        with open(f"{path}/weights.json", 'r') as f:
            weights = json.load(f)
            weighting.set_weights(weights)

# Глобальный экземпляр модели
model = RecommendationModel(index_type="cosine")