import librosa
import numpy as np
from typing import Tuple, Optional
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class AudioLoader:
    """Класс для загрузки и первичной обработки аудиофайлов."""
    
    def __init__(self, sample_rate: int = 22050, duration: Optional[float] = None):
        """
        Инициализация загрузчика.
        """
        self.sample_rate = sample_rate
        self.duration = duration
    
    def load(self, file_path: str) -> Tuple[np.ndarray, int]:
        """
        Загрузка аудиофайла с предобработкой.
        """
        try:
            y, sr = librosa.load(
                file_path, 
                sr=self.sample_rate,
                duration=self.duration,
                mono=True
            )
            
            logger.info(f"Файл {file_path} загружен. Длительность: {len(y)/sr:.2f}с")
            return y, sr
            
        except Exception as e:
            logger.error(f"Ошибка загрузки файла {file_path}: {e}")
            raise
    
    def preprocess(self, y: np.ndarray) -> np.ndarray:
        """
        Предварительная обработка сигнала.
        """
        if np.max(np.abs(y)) > 0:
            y = y / np.max(np.abs(y))
        
        y = y - np.mean(y)
        
        return y
    
    def get_segment(self, y: np.ndarray, sr: int, start: float, duration: float) -> np.ndarray:
        """
        Извлечение сегмента аудио для анализа.
        """
        start_sample = int(start * sr)
        end_sample = int((start + duration) * sr)
        return y[start_sample:end_sample]