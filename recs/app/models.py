from pydantic import BaseModel
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
    # file_id is a UUID string (matches Rust audio_files.id)
    file_id: str
    similarity_score: float
    features: Optional[FeaturesIn] = None


class BatchRecommendationRequest(BaseModel):
    file_ids: List[str]   # list of UUID strings
    limit: int = 10
    method: str = "cosine"


class WeightsUpdateRequest(BaseModel):
    weights: dict
