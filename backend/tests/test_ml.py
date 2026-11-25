"""Threat-likelihood model: graded output that follows the documented rules."""
import joblib
import numpy as np
import pytest

from app.services import ml_service as ml
from app.services.risk_service import compute_scores


def _assessment(quality, numeric):
    """overall + category scores for a facility where every rating = quality."""
    cctv, guards, severity, incident_type, response = numeric
    data = {
        "Physical Security": {"a": quality, "cctv_coverage": cctv, "cctv_functionality": cctv,
                              "b": quality, "c": quality},
        "Access Control": {k: quality for k in "abcd"},
        "Personnel": {"guard_count_ratio": guards, "a": quality, "b": quality, "c": quality},
        "Incident History": {"incident_severity_score": severity, "incident_type_score": incident_type,
                             "response_time_score": response, "d": quality},
        "Emergency Preparedness": {k: quality for k in "abcd"},
    }
    categories, _, overall = compute_scores(data)
    return {"overall_score": overall, "category_scores": categories}


EXCELLENT = _assessment("Excellent", (95, 90, 10, 10, 90))  # last = response quality
GOOD = _assessment("Good", (80, 75, 30, 30, 70))
FAIR = _assessment("Fair", (55, 55, 55, 50, 45))
POOR = _assessment("Poor", (25, 30, 80, 80, 15))


def test_output_shape():
    p = ml.predict(GOOD)
    assert set(p) == set(ml.TARGET_NAMES)  # no misleading "confidence" any more
    assert all(0.0 <= v <= 1.0 for v in p.values())


@pytest.mark.parametrize("profile,low,high", [
    (EXCELLENT, 0.00, 0.15),
    (GOOD, 0.00, 0.20),
    (FAIR, 0.25, 0.85),   # moderate facility → genuinely uncertain, not ~100%
    (POOR, 0.85, 1.00),
])
def test_probabilities_are_graded(profile, low, high):
    for name, value in ml.predict(profile).items():
        assert low <= value <= high, (name, value)


def test_worse_facility_never_scores_lower():
    ladder = [ml.predict(p) for p in (EXCELLENT, GOOD, FAIR, POOR)]
    for name in ml.TARGET_NAMES:
        values = [p[name] for p in ladder]
        assert values == sorted(values), (name, values)


def test_model_tracks_rule_curve():
    """On fresh synthetic facilities, the model reproduces the documented rules."""
    rng = np.random.default_rng(123)
    raw = ml._sample_raw_scores(rng, 2000)
    model = ml._get_model()
    predicted = np.column_stack([p[:, 1] for p in model.predict_proba(ml._engineer_features(raw))])
    error = np.abs(predicted - ml.threat_probabilities(raw))
    assert error.mean() < 0.06
    assert np.percentile(error, 95) < 0.15


def test_threat_follows_its_drivers():
    """Weak access control raises unauthorized-access far more than perimeter breach."""
    weak_access = {**GOOD, "category_scores": {**GOOD["category_scores"], "Access Control": 90.0}}
    base, weak = ml.predict(GOOD), ml.predict(weak_access)
    assert weak["unauthorized_access"] - base["unauthorized_access"] > 0.2
    assert weak["unauthorized_access"] - base["unauthorized_access"] > \
        weak["perimeter_breach"] - base["perimeter_breach"]


def test_outdated_cached_model_is_retrained(tmp_path, monkeypatch):
    path = tmp_path / "old.pkl"
    joblib.dump({"version": ml.MODEL_VERSION - 1, "model": object()}, path)
    monkeypatch.setattr(ml.settings, "MODEL_PATH", str(path))
    monkeypatch.setattr(ml, "_model", None)

    ml._get_model()
    assert joblib.load(path)["version"] == ml.MODEL_VERSION


def test_legacy_unversioned_model_file_is_retrained(tmp_path, monkeypatch):
    path = tmp_path / "legacy.pkl"
    joblib.dump(["not", "a", "bundle"], path)  # pre-versioning files were bare pipelines
    monkeypatch.setattr(ml.settings, "MODEL_PATH", str(path))
    monkeypatch.setattr(ml, "_model", None)

    ml._get_model()
    assert joblib.load(path)["version"] == ml.MODEL_VERSION


def test_model_from_other_sklearn_version_is_retrained(tmp_path, monkeypatch):
    path = tmp_path / "other-sklearn.pkl"
    joblib.dump({"version": ml.MODEL_VERSION, "sklearn": "0.0.1", "model": object()}, path)
    monkeypatch.setattr(ml.settings, "MODEL_PATH", str(path))
    monkeypatch.setattr(ml, "_model", None)

    ml._get_model()
    assert joblib.load(path)["sklearn"] == ml._sklearn_version()
