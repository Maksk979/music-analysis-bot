from pydantic import BaseModel, Field
from typing import List, Optional

class FeaturesIn(BaseModel):
    tempo: float
    energy: float
    danceability: float
    valence: float
    acousticness: float
    instrumentalness: float
    speechiness: float
    loudness: float
    key: int
    mode: int

class RecommendationOut(BaseModel):
    file_id: int
    similarity_score: float
    features: Optional[FeaturesIn] = None

class BatchRecommendationRequest(BaseModel):
    file_ids: List[int]
    limit: int = 10
    method: str = "cosine"  # cosine, euclidean, pearson