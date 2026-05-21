import librosa
import numpy as np
from typing import Dict, Any
from app.core.utils import safe_float


class RhythmFeatureExtractor:
    def __init__(self, hop_length: int = 512):
        self.hop_length = hop_length

    def extract_tempo(self, y: np.ndarray, sr: int) -> Dict[str, Any]:
        tempo, beat_frames = librosa.beat.beat_track(
            y=y, sr=sr, hop_length=self.hop_length
        )
        if isinstance(tempo, np.ndarray):
            tempo = tempo[0]
        beat_times = librosa.frames_to_time(
            beat_frames, sr=sr, hop_length=self.hop_length
        )
        if len(beat_times) > 1:
            intervals = np.diff(beat_times)
            tempo_std = float(np.std(60.0 / intervals)) if len(intervals) > 0 else 0.0
        else:
            tempo_std = 0.0
        return {
            "tempo": safe_float(tempo),
            "tempo_confidence": safe_float(
                self._calculate_tempo_confidence(y, sr, tempo)
            ),
            "tempo_std": tempo_std,
            "n_beats": len(beat_frames),
        }

    def _calculate_tempo_confidence(
        self, y: np.ndarray, sr: int, detected_tempo: float
    ) -> float:
        try:
            onset_env = librosa.onset.onset_strength(
                y=y, sr=sr, hop_length=self.hop_length
            )
            tempogram = librosa.feature.tempogram(
                onset_envelope=onset_env, sr=sr, hop_length=self.hop_length
            )
            tempo_freqs = librosa.tempo_frequencies(
                sr=sr, hop_length=self.hop_length, n_bins=tempogram.shape[0]
            )
            tempo_idx = np.argmin(np.abs(tempo_freqs - detected_tempo))
            confidence = safe_float(
                np.mean(tempogram[tempo_idx, :]) / (np.max(tempogram) + 1e-6)
            )
            return min(confidence, 1.0)
        except Exception as e:
            print(f"Предупреждение: ошибка при расчете уверенности темпа: {e}")
            return 0.5

    def extract_beat_strength(self, y: np.ndarray, sr: int) -> Dict[str, float]:
        onset_env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=self.hop_length)
        return {
            "mean_onset_strength": safe_float(np.mean(onset_env)),
            "std_onset_strength": safe_float(np.std(onset_env)),
            "max_onset_strength": safe_float(np.max(onset_env)),
        }

    def extract_all(self, y: np.ndarray, sr: int) -> Dict[str, Any]:
        features = {}
        features.update(self.extract_tempo(y, sr))
        features.update(self.extract_beat_strength(y, sr))
        return features
