import librosa
import numpy as np
from typing import Dict, Any


class SpectralFeatureExtractor:
    """Извлечение спектральных характеристик."""

    def __init__(self, n_mfcc: int = 13, n_fft: int = 2048, hop_length: int = 512):
        """
        Инициализация экстрактора.
        """
        self.n_mfcc = n_mfcc
        self.n_fft = n_fft
        self.hop_length = hop_length

    def extract_mfcc(self, y: np.ndarray, sr: int) -> Dict[str, Any]:
        """
        Извлечение MFCC коэффициентов.(мел-частотные кепстральные коэффициенты)
        """
        mfccs = librosa.feature.mfcc(
            y=y,
            sr=sr,
            n_mfcc=self.n_mfcc,
            n_fft=self.n_fft,
            hop_length=self.hop_length
        )

        mfcc_mean = np.mean(mfccs, axis=1)
        mfcc_std = np.std(mfccs, axis=1)
        mfcc_var = np.var(mfccs, axis=1)

        return {
            'mfccs': mfccs.tolist(),
            'mfcc_mean': mfcc_mean.tolist(),
            'mfcc_std': mfcc_std.tolist(),
            'mfcc_var': mfcc_var.tolist()
        }

    def extract_spectral_centroid(self, y: np.ndarray, sr: int) -> Dict[str, float]:
        """
        Извлечение спектрального центроида.(интенсивности)
        """
        centroid = librosa.feature.spectral_centroid(
            y=y,
            sr=sr,
            n_fft=self.n_fft,
            hop_length=self.hop_length
        )

        return {
            'spectral_centroid_mean': float(np.mean(centroid)),
            'spectral_centroid_std': float(np.std(centroid))
        }

    def extract_spectral_rolloff(self, y: np.ndarray, sr: int) -> Dict[str, float]:
        """
        Извлечение спектрального спада (rolloff).
        """
        rolloff = librosa.feature.spectral_rolloff(
            y=y,
            sr=sr,
            n_fft=self.n_fft,
            hop_length=self.hop_length
        )

        return {
            'spectral_rolloff_mean': float(np.mean(rolloff)),
            'spectral_rolloff_std': float(np.std(rolloff))
        }

    def extract_spectral_bandwidth(self, y: np.ndarray, sr: int) -> Dict[str, float]:
        """
        Извлечение спектральной ширины полосы.
        """
        bandwidth = librosa.feature.spectral_bandwidth(
            y=y,
            sr=sr,
            n_fft=self.n_fft,
            hop_length=self.hop_length
        )

        return {
            'spectral_bandwidth_mean': float(np.mean(bandwidth)),
            'spectral_bandwidth_std': float(np.std(bandwidth))
        }

    def extract_chroma(self, y: np.ndarray, sr: int) -> Dict[str, Any]:
        """
        Извлечение хромограммы.(храмтическая гамма)
        """
        chroma = librosa.feature.chroma_stft(
            y=y,
            sr=sr,
            n_fft=self.n_fft,
            hop_length=self.hop_length
        )

        chroma_mean = np.mean(chroma, axis=1)

        return {
            'chroma': chroma.tolist(),
            'chroma_mean': chroma_mean.tolist()
        }

    def extract_spectrogram(self, y: np.ndarray, sr: int) -> Dict[str, Any]:
        """
        Извлечение мел-спектрограммы.
        """
        mel_spec = librosa.feature.melspectrogram(
            y=y,
            sr=sr,
            n_fft=self.n_fft,
            hop_length=self.hop_length
        )

        mel_spec_db = librosa.power_to_db(mel_spec, ref=np.max)

        return {
            'mel_spectrogram': mel_spec_db.tolist(),
            'mel_spectrogram_mean': float(np.mean(mel_spec_db)),
            'mel_spectrogram_std': float(np.std(mel_spec_db))
        }

    def extract_all(self, y: np.ndarray, sr: int) -> Dict[str, Any]:
        """
        Извлечение всех спектральных характеристик.
        """
        features = {}

        # MFCC
        features.update(self.extract_mfcc(y, sr))

        # Спектральные характеристики
        features.update(self.extract_spectral_centroid(y, sr))
        features.update(self.extract_spectral_rolloff(y, sr))
        features.update(self.extract_spectral_bandwidth(y, sr))

        # Хрома и спектрограмма
        features.update(self.extract_chroma(y, sr))
        features.update(self.extract_spectrogram(y, sr))

        return features
