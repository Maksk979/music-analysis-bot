from pydantic import BaseModel, Field
from typing import Optional, Dict, Any, List
from enum import Enum

class TaskStatus(str, Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class AnalysisResponse(BaseModel):
    task_id: str
    status: TaskStatus
    message: Optional[str] = None

class StatusResponse(BaseModel):
    task_id: str
    status: TaskStatus
    progress: Optional[float] = None  
    error: Optional[str] = None

class FileInfo(BaseModel):
    filename: str
    duration: float
    sample_rate: int
    n_samples: int
    rms_energy: float
    peak_amplitude: float

class SpectralFeatures(BaseModel):
    mfcc_mean: List[float]
    mfcc_std: List[float]
    mfcc_var: List[float]
    spectral_centroid_mean: float
    spectral_centroid_std: float
    spectral_rolloff_mean: float
    spectral_rolloff_std: float
    spectral_bandwidth_mean: float
    spectral_bandwidth_std: float
    chroma_mean: List[float]
    mel_spectrogram_mean: float
    mel_spectrogram_std: float

class RhythmFeatures(BaseModel):
    tempo: float
    tempo_confidence: float
    tempo_std: float
    n_beats: int
    mean_onset_strength: float
    std_onset_strength: float
    max_onset_strength: float

class HarmonicFeatures(BaseModel):
    key: str
    key_index: int
    mode: str
    mode_confidence: float
    key_confidence: float
    harmonic_ratio: float
    harmonic_energy: float
    percussive_energy: float

class HighLevelMetrics(BaseModel):
    energy: float
    danceability: float
    valence: float
    acousticness: float
    instrumentalness: float
    speechiness: float
    loudness: float

class AnalysisResult(BaseModel):
    task_id: str
    status: TaskStatus
    file_info: Optional[FileInfo] = None
    spectral: Optional[SpectralFeatures] = None
    rhythm: Optional[RhythmFeatures] = None
    harmonic: Optional[HarmonicFeatures] = None
    high_level: Optional[HighLevelMetrics] = None
    analysis_metadata: Optional[Dict[str, Any]] = None
    error: Optional[str] = None

class HealthResponse(BaseModel):
    status: str = "healthy"
    version: str = "0.1.0"