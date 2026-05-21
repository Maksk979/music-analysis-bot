import librosa
import numpy as np
from typing import Dict, Any
from app.core.utils import safe_float


class HarmonicFeatureExtractor:
    def __init__(self):
        self.key_names = [
            "C",
            "C#",
            "D",
            "D#",
            "E",
            "F",
            "F#",
            "G",
            "G#",
            "A",
            "A#",
            "B",
        ]

    def extract_key_and_mode(self, y: np.ndarray, sr: int) -> Dict[str, Any]:
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        chroma_mean = np.mean(chroma, axis=1)
        key_index = int(np.argmax(chroma_mean))
        key = self.key_names[key_index]

        major_profile = np.array([1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 0, 1], dtype=float)
        minor_profile = np.array([1, 0, 0, 1, 1, 0, 0, 1, 0, 1, 0, 1], dtype=float)
        major_shifted = np.roll(major_profile, key_index)
        minor_shifted = np.roll(minor_profile, key_index)

        major_corr = np.corrcoef(chroma_mean, major_shifted)[0, 1]
        minor_corr = np.corrcoef(chroma_mean, minor_shifted)[0, 1]

        if major_corr > minor_corr:
            mode = "major"
            mode_confidence = safe_float(major_corr / (major_corr + minor_corr + 1e-9))
        else:
            mode = "minor"
            mode_confidence = safe_float(minor_corr / (major_corr + minor_corr + 1e-9))

        return {
            "key": key,
            "key_index": key_index,
            "mode": mode,
            "mode_confidence": mode_confidence,
            "key_confidence": safe_float(
                np.max(chroma_mean) / (np.sum(chroma_mean) + 1e-9)
            ),
        }

    def extract_harmonic_ratio(self, y: np.ndarray, sr: int) -> Dict[str, float]:
        y_harmonic, y_percussive = librosa.effects.hpss(y)
        e_h = np.sum(y_harmonic**2)
        e_p = np.sum(y_percussive**2)
        total = e_h + e_p
        return {
            "harmonic_ratio": safe_float(e_h / total if total > 0 else 0.5),
            "harmonic_energy": safe_float(e_h),
            "percussive_energy": safe_float(e_p),
        }

    def extract_all(self, y: np.ndarray, sr: int) -> Dict[str, Any]:
        features = {}
        features.update(self.extract_key_and_mode(y, sr))
        features.update(self.extract_harmonic_ratio(y, sr))
        return features
