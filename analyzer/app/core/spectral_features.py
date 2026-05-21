import librosa
import numpy as np
from typing import Dict, Any
from app.core.utils import safe_float


class SpectralFeatureExtractor:
    def __init__(self, n_mfcc: int = 13, n_fft: int = 2048, hop_length: int = 512):
        self.n_mfcc = n_mfcc
        self.n_fft = n_fft
        self.hop_length = hop_length

    def extract_mfcc(self, y: np.ndarray, sr: int) -> Dict[str, Any]:
        mfccs = librosa.feature.mfcc(
            y=y, sr=sr, n_mfcc=self.n_mfcc, n_fft=self.n_fft, hop_length=self.hop_length
        )
        return {
            "mfccs": mfccs.tolist(),
            "mfcc_mean": np.mean(mfccs, axis=1).tolist(),
            "mfcc_std": np.std(mfccs, axis=1).tolist(),
            "mfcc_var": np.var(mfccs, axis=1).tolist(),
        }

    def extract_spectral_centroid(self, y: np.ndarray, sr: int) -> Dict[str, float]:
        c = librosa.feature.spectral_centroid(
            y=y, sr=sr, n_fft=self.n_fft, hop_length=self.hop_length
        )
        return {
            "spectral_centroid_mean": safe_float(np.mean(c)),
            "spectral_centroid_std": safe_float(np.std(c)),
        }

    def extract_spectral_rolloff(self, y: np.ndarray, sr: int) -> Dict[str, float]:
        r = librosa.feature.spectral_rolloff(
            y=y, sr=sr, n_fft=self.n_fft, hop_length=self.hop_length
        )
        return {
            "spectral_rolloff_mean": safe_float(np.mean(r)),
            "spectral_rolloff_std": safe_float(np.std(r)),
        }

    def extract_spectral_bandwidth(self, y: np.ndarray, sr: int) -> Dict[str, float]:
        b = librosa.feature.spectral_bandwidth(
            y=y, sr=sr, n_fft=self.n_fft, hop_length=self.hop_length
        )
        return {
            "spectral_bandwidth_mean": safe_float(np.mean(b)),
            "spectral_bandwidth_std": safe_float(np.std(b)),
        }

    def extract_chroma(self, y: np.ndarray, sr: int) -> Dict[str, Any]:
        ch = librosa.feature.chroma_stft(
            y=y, sr=sr, n_fft=self.n_fft, hop_length=self.hop_length
        )
        return {"chroma": ch.tolist(), "chroma_mean": np.mean(ch, axis=1).tolist()}

    def extract_spectrogram(self, y: np.ndarray, sr: int) -> Dict[str, Any]:
        mel = librosa.feature.melspectrogram(
            y=y, sr=sr, n_fft=self.n_fft, hop_length=self.hop_length
        )
        mel_db = librosa.power_to_db(mel, ref=np.max)
        return {
            "mel_spectrogram": mel_db.tolist(),
            "mel_spectrogram_mean": safe_float(np.mean(mel_db)),
            "mel_spectrogram_std": safe_float(np.std(mel_db)),
        }

    def extract_all(self, y: np.ndarray, sr: int) -> Dict[str, Any]:
        features = {}
        features.update(self.extract_mfcc(y, sr))
        features.update(self.extract_spectral_centroid(y, sr))
        features.update(self.extract_spectral_rolloff(y, sr))
        features.update(self.extract_spectral_bandwidth(y, sr))
        features.update(self.extract_chroma(y, sr))
        features.update(self.extract_spectrogram(y, sr))
        return features
