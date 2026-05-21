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
        self.index_type = index_type
        self.index = None
        self.file_ids: List[str] = []   # UUID strings
        self.feature_dim = 10
        self.kmeans = None
        self.cluster_labels = None
        self.matrix_norm: np.ndarray = np.empty((0, 10), dtype=np.float32)

    def build_index(self, features_list: List[AudioFeatures]):
        matrix, file_ids = [], []
        for f in features_list:
            vec = np.array([
                f.tempo or 0.0, f.energy or 0.0, f.danceability or 0.0,
                f.valence or 0.0, f.acousticness or 0.0, f.instrumentalness or 0.0,
                f.speechiness or 0.0, f.loudness or 0.0,
                float(f.key or 0), float(f.mode or 0),
            ])
            matrix.append(vec)
            file_ids.append(f.audio_file_id)   # UUID string

        matrix = np.array(matrix, dtype=np.float32)
        if np.any(np.isnan(matrix)):
            matrix = normalizer.handle_missing(matrix, strategy="median")

        matrix_norm = normalizer.fit_transform(matrix) if not normalizer.fitted \
            else normalizer.transform(matrix)
        matrix_norm = weighting.apply(matrix_norm)

        if self.index_type == "cosine":
            idx = faiss.IndexFlatIP(self.feature_dim)
            faiss.normalize_L2(matrix_norm)
            idx.add(matrix_norm)
        elif self.index_type == "euclidean":
            idx = faiss.IndexFlatL2(self.feature_dim)
            idx.add(matrix_norm)
        else:
            idx = None

        self.index = idx
        self.file_ids = file_ids
        self.matrix_norm = matrix_norm

        if len(matrix_norm) > 10:
            n_clusters = min(20, len(matrix_norm) // 5)
            self.kmeans = KMeans(n_clusters=n_clusters, random_state=42)
            self.cluster_labels = self.kmeans.fit_predict(matrix_norm)

    def get_similar(
        self, target_vec: np.ndarray, target_id: str, method: str, limit: int = 10
    ) -> List[Tuple[str, float]]:
        target_vec = target_vec.reshape(1, -1).astype(np.float32)
        if normalizer.fitted:
            target_vec = normalizer.transform(target_vec)
        target_vec = weighting.apply(target_vec)

        if method in ("cosine", "euclidean") and self.index is not None:
            if method == "cosine":
                faiss.normalize_L2(target_vec)
                distances, indices = self.index.search(target_vec, limit + 1)
                sims = distances[0]
            else:
                distances, indices = self.index.search(target_vec, limit + 1)
                sims = 1.0 / (1.0 + distances[0])

            result = []
            for idx, sim in zip(indices[0], sims):
                fid = self.file_ids[idx]
                if fid != target_id:
                    result.append((fid, float(sim)))
                if len(result) == limit:
                    break
            return result
        else:
            scores = []
            for i, fid in enumerate(self.file_ids):
                if fid == target_id:
                    continue
                vec = self.matrix_norm[i].reshape(1, -1)
                if method == "pearson":
                    from scipy.stats import pearsonr
                    corr, _ = pearsonr(target_vec.flatten(), vec.flatten())
                    score = 0.0 if np.isnan(corr) else float(corr)
                else:
                    from sklearn.metrics.pairwise import cosine_similarity
                    score = float(cosine_similarity(target_vec, vec)[0][0])
                scores.append((fid, score))
            scores.sort(key=lambda x: x[1], reverse=True)
            return scores[:limit]

    def save(self, path: str):
        os.makedirs(path, exist_ok=True)
        if self.index:
            faiss.write_index(self.index, f"{path}/index.faiss")
        np.save(f"{path}/file_ids.npy", np.array(self.file_ids))
        np.save(f"{path}/matrix_norm.npy", self.matrix_norm)
        if self.kmeans:
            import joblib
            joblib.dump(self.kmeans, f"{path}/kmeans.joblib")
        normalizer.save(f"{path}/normalizer.pkl")
        import json
        with open(f"{path}/weights.json", 'w') as f:
            json.dump(weighting.weights, f)

    def load(self, path: str):
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
            weighting.set_weights(json.load(f))


model = RecommendationModel(index_type="cosine")
