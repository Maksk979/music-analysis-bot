"""
Unit tests for the recommendations microservice.

Tests cover the pure-math layer (similarity scores, normalization, weighting)
without requiring a database, Redis, or FAISS-built model.

Run with:  cd recs && pytest -q
"""
import numpy as np
import pytest

from app.similarity import (
    cosine_similarity_score,
    euclidean_distance_score,
    pearson_correlation_score,
    compute_similarity,
)
from app.normalization import FeatureNormalizer
from app.weighting import FeatureWeighting, DEFAULT_WEIGHTS


# ─── Similarity scores ────────────────────────────────────────────────────────

def test_cosine_identical_vectors_is_one():
    v = np.array([[1.0, 2.0, 3.0]])
    assert cosine_similarity_score(v, v) == pytest.approx(1.0, abs=1e-6)


def test_cosine_orthogonal_vectors_is_zero():
    v1 = np.array([[1.0, 0.0]])
    v2 = np.array([[0.0, 1.0]])
    assert cosine_similarity_score(v1, v2) == pytest.approx(0.0, abs=1e-6)


def test_cosine_opposite_vectors_is_minus_one():
    v1 = np.array([[1.0, 1.0]])
    v2 = np.array([[-1.0, -1.0]])
    assert cosine_similarity_score(v1, v2) == pytest.approx(-1.0, abs=1e-6)


def test_euclidean_identical_vectors_is_one():
    v = np.array([[1.0, 2.0, 3.0]])
    assert euclidean_distance_score(v, v) == pytest.approx(1.0, abs=1e-6)


def test_euclidean_decreases_with_distance():
    v1 = np.array([[0.0, 0.0]])
    near = np.array([[0.1, 0.1]])
    far = np.array([[10.0, 10.0]])
    assert euclidean_distance_score(v1, near) > euclidean_distance_score(v1, far)


def test_pearson_perfectly_correlated_is_one():
    v1 = np.array([[1.0, 2.0, 3.0, 4.0]])
    v2 = np.array([[2.0, 4.0, 6.0, 8.0]])
    assert pearson_correlation_score(v1, v2) == pytest.approx(1.0, abs=1e-6)


def test_pearson_constant_input_returns_zero():
    # Pearson is undefined for constant inputs; should not blow up.
    v1 = np.array([[1.0, 1.0, 1.0]])
    v2 = np.array([[1.0, 2.0, 3.0]])
    assert pearson_correlation_score(v1, v2) == 0.0


def test_compute_similarity_dispatches_correctly():
    v1 = np.array([[1.0, 0.0]])
    v2 = np.array([[1.0, 0.0]])
    assert compute_similarity(v1, v2, "cosine") == pytest.approx(1.0)
    assert compute_similarity(v1, v2, "euclidean") == pytest.approx(1.0)


def test_compute_similarity_unknown_method_raises():
    v = np.array([[1.0]])
    with pytest.raises(ValueError):
        compute_similarity(v, v, "manhattan")


# ─── Normalization ────────────────────────────────────────────────────────────

def test_normalizer_min_max_to_zero_one():
    n = FeatureNormalizer()
    matrix = np.array([[0.0, 100.0], [50.0, 200.0], [100.0, 300.0]])
    out = n.fit_transform(matrix)
    assert out.min() == pytest.approx(0.0)
    assert out.max() == pytest.approx(1.0)


def test_normalizer_handle_missing_median():
    n = FeatureNormalizer()
    m = np.array([[1.0, np.nan, 3.0], [4.0, 2.0, 6.0], [7.0, 8.0, np.nan]])
    out = n.handle_missing(m, strategy="median")
    assert not np.any(np.isnan(out))


def test_normalizer_handle_missing_zero():
    n = FeatureNormalizer()
    m = np.array([[1.0, np.nan]])
    out = n.handle_missing(m.copy(), strategy="zero")
    assert out[0, 1] == 0.0


def test_normalizer_transform_without_fit_raises():
    n = FeatureNormalizer()
    with pytest.raises(ValueError):
        n.transform(np.array([[1.0, 2.0]]))


# ─── Weighting ────────────────────────────────────────────────────────────────

def test_weighting_default_does_not_change_high_weight_features():
    # tempo has weight 1.0 by default → value preserved
    w = FeatureWeighting()
    vec = np.ones((1, len(DEFAULT_WEIGHTS)))
    out = w.apply(vec)
    # Position 0 is "tempo" with weight 1.0
    assert out[0, 0] == pytest.approx(1.0)


def test_weighting_update_weight_changes_output():
    w = FeatureWeighting()
    w.update_weight("tempo", 2.0)
    vec = np.ones((1, len(DEFAULT_WEIGHTS)))
    out = w.apply(vec)
    assert out[0, 0] == pytest.approx(2.0)


def test_weighting_unknown_feature_raises():
    w = FeatureWeighting()
    with pytest.raises(ValueError):
        w.update_weight("definitely_not_a_feature", 1.0)


def test_weighting_set_weights_bulk():
    w = FeatureWeighting()
    w.set_weights({"tempo": 0.0, "energy": 0.0})
    vec = np.ones((1, len(DEFAULT_WEIGHTS)))
    out = w.apply(vec)
    assert out[0, 0] == pytest.approx(0.0)  # tempo
    assert out[0, 1] == pytest.approx(0.0)  # energy
