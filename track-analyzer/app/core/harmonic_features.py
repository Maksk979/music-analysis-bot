"""
Модуль для извлечения гармонических характеристик аудио.
"""
import librosa
import numpy as np
from typing import Dict, Any, Tuple

class HarmonicFeatureExtractor:
    """Извлечение гармонических характеристик."""
    
    def __init__(self):
        self.key_names = ['C', 'C#', 'D', 'D#', 'E', 'F', 'F#', 'G', 'G#', 'A', 'A#', 'B']
        self.mode_names = ['minor', 'major']
    
    def extract_key_and_mode(self, y: np.ndarray, sr: int) -> Dict[str, Any]:
        """
        Извлечение тональности и лада.
        """
        # Используем хрому для определения тональности
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        
        chroma_mean = np.mean(chroma, axis=1)
        
        # Находим пик в хроме - это вероятная тоника
        key_index = int(np.argmax(chroma_mean))
        key = self.key_names[key_index]
        
        # Определение лада (мажор/минор) на основе распределения
        # В мажоре сильнее 1, 4, 5 ступени, в миноре - 1, 3b, 5
        major_profile = np.array([1, 0, 1, 0, 1, 1, 0, 1, 0, 1, 0, 1])
        minor_profile = np.array([1, 0, 0, 1, 1, 0, 0, 1, 0, 1, 0, 1])
        
        # Циклический сдвиг под тонику
        major_shifted = np.roll(major_profile, key_index)
        minor_shifted = np.roll(minor_profile, key_index)
        
        # Корреляция с профилями
        major_corr = np.corrcoef(chroma_mean, major_shifted)[0, 1]
        minor_corr = np.corrcoef(chroma_mean, minor_shifted)[0, 1]
        
        if major_corr > minor_corr:
            mode = 'major'
            mode_confidence = float(major_corr / (major_corr + minor_corr))
        else:
            mode = 'minor'
            mode_confidence = float(minor_corr / (major_corr + minor_corr))
        
        return {
            'key': key,
            'key_index': key_index,
            'mode': mode,
            'mode_confidence': mode_confidence,
            'key_confidence': float(np.max(chroma_mean) / np.sum(chroma_mean))
        }
    
    def extract_harmonic_ratio(self, y: np.ndarray, sr: int) -> Dict[str, float]:
        """
        Извлечение отношения гармонической/перкуссионной составляющей.
        """
        y_harmonic, y_percussive = librosa.effects.hpss(y)
        
        energy_harmonic = np.sum(y_harmonic**2)
        energy_percussive = np.sum(y_percussive**2)
        energy_total = energy_harmonic + energy_percussive
        
        if energy_total > 0:
            harmonic_ratio = energy_harmonic / energy_total
        else:
            harmonic_ratio = 0.5
        
        return {
            'harmonic_ratio': float(harmonic_ratio),
            'harmonic_energy': float(energy_harmonic),
            'percussive_energy': float(energy_percussive)
        }
    
    def extract_all(self, y: np.ndarray, sr: int) -> Dict[str, Any]:
        """
        Извлечение всех гармонических характеристик.
        """
        features = {}
        
        features.update(self.extract_key_and_mode(y, sr))
        
        features.update(self.extract_harmonic_ratio(y, sr))
        
        return features