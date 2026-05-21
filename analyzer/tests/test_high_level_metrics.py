"""
Unit tests for the audio analyzer microservice.

Tests cover the pure-logic layer (high-level metric derivation and Pydantic
schema validation) without requiring a real audio file or librosa.

Run with:  cd analyzer && pytest -q
"""
import numpy as np
import pytest

from app.core.analyzer import AudioAnalyzer
from app.models.schemas import (
    TaskStatus,
    HighLevelMetrics,
    AnalysisResponse,
    FileInfo,
)


# ─── High-level metric computation ────────────────────────────────────────────

@pytest.fixture
def analyzer():
    return AudioAnalyzer()


def make_features(rms=0.1, tempo=120.0, onset=2.5, harmonic_ratio=0.6,
                  mfcc_mean=None):
    return {
        "file_info": {
            "filename": "x.mp3",
            "duration": 30.0,
            "sample_rate": 22050,
            "n_samples": 22050 * 30,
            "rms_energy": rms,
            "peak_amplitude": 0.8,
        },
        "spectral": {"mfcc_mean": mfcc_mean or [0.1] * 13},
        "rhythm": {"tempo": tempo, "mean_onset_strength": onset},
        "harmonic": {"harmonic_ratio": harmonic_ratio},
    }


def test_energy_is_clamped_to_zero_one(analyzer):
    low = analyzer._compute_high_level_metrics(make_features(rms=0.0))
    high = analyzer._compute_high_level_metrics(make_features(rms=10.0))
    assert 0.0 <= low["energy"] <= 1.0
    assert 0.0 <= high["energy"] <= 1.0
    assert high["energy"] >= low["energy"]


def test_valence_tracks_harmonic_ratio(analyzer):
    sad = analyzer._compute_high_level_metrics(make_features(harmonic_ratio=0.1))
    happy = analyzer._compute_high_level_metrics(make_features(harmonic_ratio=0.9))
    assert happy["valence"] > sad["valence"]


def test_danceability_in_unit_range(analyzer):
    m = analyzer._compute_high_level_metrics(make_features(rms=0.05, tempo=128.0, onset=4.0))
    assert 0.0 <= m["danceability"] <= 1.0


def test_speechiness_and_instrumentalness_sum_to_one(analyzer):
    m = analyzer._compute_high_level_metrics(make_features())
    assert m["speechiness"] + m["instrumentalness"] == pytest.approx(1.0, abs=1e-6)


def test_loudness_in_db_range(analyzer):
    # We clip loudness to [-60, 0] dBFS
    m = analyzer._compute_high_level_metrics(make_features(rms=0.5))
    assert -60.0 <= m["loudness"] <= 0.0


def test_silence_produces_minimum_loudness(analyzer):
    m = analyzer._compute_high_level_metrics(make_features(rms=0.0))
    assert m["loudness"] == pytest.approx(-60.0, abs=1.0)


def test_short_mfcc_falls_back_to_default_instrumentalness(analyzer):
    m = analyzer._compute_high_level_metrics(make_features(mfcc_mean=[0.1, 0.2]))
    assert m["instrumentalness"] == pytest.approx(0.5)


# ─── Schema validation ───────────────────────────────────────────────────────

def test_task_status_enum_string_values():
    assert TaskStatus.PENDING.value == "pending"
    assert TaskStatus.PROCESSING.value == "processing"
    assert TaskStatus.COMPLETED.value == "completed"
    assert TaskStatus.FAILED.value == "failed"


def test_high_level_metrics_round_trip():
    m = HighLevelMetrics(
        energy=0.5, danceability=0.6, valence=0.7,
        acousticness=0.4, instrumentalness=0.3,
        speechiness=0.7, loudness=-10.0,
    )
    payload = m.model_dump()
    restored = HighLevelMetrics(**payload)
    assert restored.energy == pytest.approx(0.5)


def test_analysis_response_requires_task_id():
    with pytest.raises(Exception):
        AnalysisResponse(status=TaskStatus.PENDING)  # type: ignore[call-arg]


def test_file_info_accepts_valid_payload():
    info = FileInfo(
        filename="x.mp3",
        duration=30.0,
        sample_rate=22050,
        n_samples=661500,
        rms_energy=0.1,
        peak_amplitude=0.9,
    )
    assert info.duration == pytest.approx(30.0)
