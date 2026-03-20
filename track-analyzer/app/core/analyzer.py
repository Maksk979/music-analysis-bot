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
    """
    Главный класс для анализа аудиофайлов.
    Координирует работу всех экстракторов характеристик.
    """
    
    def __init__(self, 
                 sample_rate: int = 22050,
                 n_mfcc: int = 13,
                 duration: Optional[float] = None):  # Задаем временной промежуток для анализа
        """
        Инициализация анализатора.
        """
        self.audio_loader = AudioLoader(sample_rate=sample_rate, duration=duration)
        self.spectral_extractor = SpectralFeatureExtractor(n_mfcc=n_mfcc)
        self.rhythm_extractor = RhythmFeatureExtractor()
        self.harmonic_extractor = HarmonicFeatureExtractor()
        
        logger.info(f"Анализатор инициализирован (sr={sample_rate}, n_mfcc={n_mfcc})")
    
    def analyze_file(self, file_path: str) -> Dict[str, Any]:
        """
        Полный анализ аудиофайла.
        """
        start_time = time.time()
        
        try:
            logger.info(f"Начало анализа файла: {file_path}")
            y, sr = self.audio_loader.load(file_path)
            
            y = self.audio_loader.preprocess(y)
            
            features = {
                'file_info': self._extract_file_info(y, sr, file_path),
                'spectral': self.spectral_extractor.extract_all(y, sr),
                'rhythm': self.rhythm_extractor.extract_all(y, sr),
                'harmonic': self.harmonic_extractor.extract_all(y, sr)
            }
            
            features['high_level'] = self._compute_high_level_metrics(features)
            
            features['analysis_metadata'] = {
                'duration_analyzed': len(y) / sr,
                'processing_time': time.time() - start_time,
                'sample_rate': sr
            }
            
            logger.info(f"Анализ завершен за {features['analysis_metadata']['processing_time']:.2f}с")
            return features
            
        except Exception as e:
            logger.error(f"Ошибка при анализе {file_path}: {e}")
            raise
    
    def _extract_file_info(self, y: np.ndarray, sr: int, file_path: str) -> Dict[str, Any]:
        """Базовая информация о файле."""
        return {
            'filename': file_path.split('/')[-1],
            'duration': float(len(y) / sr),
            'sample_rate': sr,
            'n_samples': len(y),
            'rms_energy': float(np.sqrt(np.mean(y**2))),
            'peak_amplitude': float(np.max(np.abs(y)))
        }
    
    def _compute_high_level_metrics(self, features: Dict[str, Any]) -> Dict[str, float]:
        """
        Вычисление высокоуровневых метрик на основе низкоуровневых характеристик.
        Соответствует требованиям из лабораторной работы.
        """
        metrics = {}
        
        # Энергия (на основе RMS и спектрального центроида)
        rms = features['file_info']['rms_energy']
        spectral_centroid = features['spectral']['spectral_centroid_mean']
        # Нормализованная энергия (0-1)
        metrics['energy'] = float(np.clip((rms * 10 + spectral_centroid / 10000) / 2, 0, 1))
        
        # Танцевальность (комбинация темпа и ритмической четкости)
        tempo = features['rhythm']['tempo']
        beat_strength = features['rhythm']['mean_onset_strength']
        # Оптимальный темп для танцев ~120 BPM
        tempo_factor = 1 - abs(tempo - 120) / 120
        metrics['danceability'] = float(np.clip((tempo_factor + beat_strength) / 2, 0, 1))
        
        # Валентность (позитив/негатив) - на основе лада и спектра
        mode_confidence = features['harmonic']['mode_confidence']
        if features['harmonic']['mode'] == 'major':
            metrics['valence'] = float(0.5 + mode_confidence * 0.5)
        else:
            metrics['valence'] = float(0.5 - mode_confidence * 0.3)
        
        # Акустичность (отсутствие электронных эффектов)
        # Используем harmonic_ratio и спектральные характеристики
        harmonic_ratio = features['harmonic']['harmonic_ratio']
        spectral_bandwidth = features['spectral']['spectral_bandwidth_mean']
        # Акустичная музыка имеет более узкую полосу и высокий harmonic_ratio
        acoustic_factor = harmonic_ratio * (1 - spectral_bandwidth / 10000)
        metrics['acousticness'] = float(np.clip(acoustic_factor, 0, 1))
        
        # Инструментальность (отсутствие вокала)
        # Используем MFCC для детекции речи (упрощенно)
        mfcc_mean = features['spectral']['mfcc_mean']
        if mfcc_mean:
            # Высокие значения MFCC часто указывают на речь
            speech_indicator = np.mean(np.abs(mfcc_mean[1:5])) if len(mfcc_mean) > 4 else 0
            metrics['instrumentalness'] = float(np.clip(1 - speech_indicator * 2, 0, 1))
        else:
            metrics['instrumentalness'] = 0.5
        
        # Разговорность (наличие речи)
        metrics['speechiness'] = float(1 - metrics['instrumentalness'])
        
        # Громкость (нормализованная)
        metrics['loudness'] = float(np.clip(20 * np.log10(rms + 1e-6) + 20, -60, 0))
        
        return metrics
    
    def get_feature_vector(self, file_path: str) -> np.ndarray:
        """
        Получение плоского вектора признаков для машинного обучения.
        """
        features = self.analyze_file(file_path)
        
        vector = []
        
        # File info
        vector.extend([
            features['file_info']['duration'],
            features['file_info']['rms_energy'],
            features['file_info']['peak_amplitude']
        ])
        
        # Spectral
        vector.extend(features['spectral']['mfcc_mean'])
        vector.extend([
            features['spectral']['spectral_centroid_mean'],
            features['spectral']['spectral_rolloff_mean'],
            features['spectral']['spectral_bandwidth_mean']
        ])
        
        # Rhythm
        vector.extend([
            features['rhythm']['tempo'],
            features['rhythm']['mean_onset_strength']
        ])
        
        # High-level metrics
        vector.extend([
            features['high_level']['energy'],
            features['high_level']['danceability'],
            features['high_level']['valence'],
            features['high_level']['acousticness'],
            features['high_level']['instrumentalness'],
            features['high_level']['speechiness'],
            features['high_level']['loudness']
        ])
        
        return np.array(vector, dtype=np.float32)