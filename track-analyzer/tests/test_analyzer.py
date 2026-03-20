"""
Тестирование модуля анализа аудио.
"""
from app.core.analyzer import AudioAnalyzer
import os
import sys
import tempfile
import pytest
import numpy as np
from pathlib import Path

# Добавляем путь к проекту
sys.path.insert(0, str(Path(__file__).parent.parent))


# Создаем тестовый аудиофайл (синусоида)

def create_test_audio(duration=5.0, sr=22050, freq=440):
    """Создание тестового аудиофайла."""
    import soundfile as sf
    import numpy as np

    t = np.linspace(0, duration, int(sr * duration))
    y = 0.5 * np.sin(2 * np.pi * freq * t)

    # Создаем временный файл
    with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as f:
        sf.write(f.name, y, sr)
        return f.name


def test_audio_analyzer_initialization():
    """Тест инициализации анализатора."""
    analyzer = AudioAnalyzer(sample_rate=22050, n_mfcc=13)
    assert analyzer.audio_loader.sample_rate == 22050
    assert analyzer.spectral_extractor.n_mfcc == 13
    print("✓ Тест инициализации пройден")


def test_analyze_sine_wave():
    """Тест анализа синусоиды."""
    # Создаем тестовый файл
    test_file = create_test_audio(duration=3.0, freq=440)

    try:
        # Анализируем
        analyzer = AudioAnalyzer()
        features = analyzer.analyze_file(test_file)

        # Проверяем наличие всех ключей
        assert 'file_info' in features
        assert 'spectral' in features
        assert 'rhythm' in features
        assert 'harmonic' in features
        assert 'high_level' in features
        assert 'analysis_metadata' in features

        # Проверяем значения
        assert features['file_info']['duration'] == pytest.approx(3.0, abs=0.1)
        assert features['harmonic']['mode'] in ['major', 'minor']

        print("✓ Тест анализа синусоиды пройден")
        print(f"  Длительность: {features['file_info']['duration']:.2f}с")
        print(f"  Энергия: {features['high_level']['energy']:.3f}")
        print(
            f"  Танцевальность: {features['high_level']['danceability']:.3f}")

    finally:
        # Удаляем временный файл
        os.unlink(test_file)


def test_feature_vector():
    """Тест получения вектора признаков."""
    test_file = create_test_audio(duration=2.0)

    try:
        analyzer = AudioAnalyzer()
        vector = analyzer.get_feature_vector(test_file)

        # Проверяем, что вектор не пустой и содержит числа
        assert len(vector) > 0
        assert np.all(np.isfinite(vector))

        print(f"✓ Тест вектора признаков пройден")
        print(f"  Размерность вектора: {len(vector)}")

    finally:
        os.unlink(test_file)


if __name__ == "__main__":
    print("=" * 50)
    print("ТЕСТИРОВАНИЕ МОДУЛЯ АНАЛИЗА АУДИО")
    print("=" * 50)

    test_audio_analyzer_initialization()
    test_analyze_sine_wave()
    test_feature_vector()

    print("=" * 50)
    print("ВСЕ ТЕСТЫ ПРОЙДЕНЫ УСПЕШНО!")
    print("=" * 50)
