import numpy as np
from typing import Dict, Any, Optional
import logging
import time

from app.core.audio_loader import AudioLoader
from app.core.spectral_features import SpectralFeatureExtractor
from app.core.rhythm_features import RhythmFeatureExtractor
from app.core.harmonic_features import HarmonicFeatureExtractor

logger = logging.getLogger(__name__)


class AudioAnalyzer:
    def __init__(self, sample_rate: int = 22050, n_mfcc: int = 13, duration: Optional[float] = None):
        self.audio_loader = AudioLoader(sample_rate=sample_rate, duration=duration)
        self.spectral_extractor = SpectralFeatureExtractor(n_mfcc=n_mfcc)
        self.rhythm_extractor = RhythmFeatureExtractor()
        self.harmonic_extractor = HarmonicFeatureExtractor()
        logger.info(f"Анализатор инициализирован (sr={sample_rate}, n_mfcc={n_mfcc})")

    def analyze_file(self, file_path: str) -> Dict[str, Any]:
        start_time = time.time()
        try:
            logger.info(f"Начало анализа файла: {file_path}")
            y, sr = self.audio_loader.load(file_path)
            y = self.audio_loader.preprocess(y)

            features = {
                'file_info': self._extract_file_info(y, sr, file_path),
                'spectral':  self.spectral_extractor.extract_all(y, sr),
                'rhythm':    self.rhythm_extractor.extract_all(y, sr),
                'harmonic':  self.harmonic_extractor.extract_all(y, sr),
            }
            features['high_level'] = self._compute_high_level_metrics(features)
            features['analysis_metadata'] = {
                'duration_analyzed': len(y) / sr,
                'processing_time': time.time() - start_time,
                'sample_rate': sr,
            }
            logger.info(f"Анализ завершен за {features['analysis_metadata']['processing_time']:.2f}с")
            return features
        except Exception as e:
            logger.error(f"Ошибка при анализе {file_path}: {e}")
            raise

    def _extract_file_info(self, y: np.ndarray, sr: int, file_path: str) -> Dict[str, Any]:
        return {
            'filename': file_path.split('/')[-1],
            'duration': float(len(y) / sr),
            'sample_rate': sr,
            'n_samples': len(y),
            'rms_energy': float(np.sqrt(np.mean(y ** 2))),
            'peak_amplitude': float(np.max(np.abs(y))),
        }

    def _compute_high_level_metrics(self, features: Dict[str, Any]) -> Dict[str, float]:
        metrics: Dict[str, float] = {}
        rms = features['file_info']['rms_energy']
        harmonic_ratio = features['harmonic'].get('harmonic_ratio', 0.5)
        tempo = features['rhythm'].get('tempo', 120.0)

        # Energy (0-1)
        metrics['energy'] = float(np.clip(rms * 10, 0, 1))

        # Danceability — high energy + regular beats → high danceability
        beat_strength = features['rhythm'].get('mean_onset_strength', 0.5)
        tempo_norm = float(np.clip((tempo - 60) / 120, 0, 1))
        metrics['danceability'] = float(np.clip(
            0.4 * metrics['energy'] + 0.4 * float(np.clip(beat_strength / 5, 0, 1)) + 0.2 * tempo_norm, 0, 1
        ))

        # Valence — harmonic pieces tend to feel more positive
        metrics['valence'] = float(np.clip(harmonic_ratio, 0, 1))

        # Acousticness — inverse of percussive energy ratio
        metrics['acousticness'] = float(np.clip(harmonic_ratio, 0, 1))

        # Instrumentalness
        mfcc_mean = features['spectral'].get('mfcc_mean', [])
        if len(mfcc_mean) > 4:
            speech_indicator = float(np.mean(np.abs(mfcc_mean[1:5])))
            metrics['instrumentalness'] = float(np.clip(1 - speech_indicator * 2, 0, 1))
        else:
            metrics['instrumentalness'] = 0.5

        # Speechiness
        metrics['speechiness'] = float(1 - metrics['instrumentalness'])

        # Loudness (dBFS, roughly)
        metrics['loudness'] = float(np.clip(20 * np.log10(rms + 1e-6) + 20, -60, 0))

        return metrics

    def get_feature_vector(self, file_path: str) -> np.ndarray:
        features = self.analyze_file(file_path)
        vector = [
            features['file_info']['duration'],
            features['file_info']['rms_energy'],
            features['file_info']['peak_amplitude'],
        ]
        vector.extend(features['spectral']['mfcc_mean'])
        vector.extend([
            features['spectral']['spectral_centroid_mean'],
            features['spectral']['spectral_rolloff_mean'],
            features['spectral']['spectral_bandwidth_mean'],
        ])
        vector.extend([features['rhythm']['tempo'], features['rhythm']['mean_onset_strength']])
        hl = features['high_level']
        vector.extend([hl['energy'], hl['danceability'], hl['valence'],
                        hl['acousticness'], hl['instrumentalness'],
                        hl['speechiness'], hl['loudness']])
        return np.array(vector, dtype=np.float32)
