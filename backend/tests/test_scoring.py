"""Unit tests for risk scoring and risk velocity."""

import pytest

from app.services.risk_service import (
    compute_risk_velocity,
    compute_scores,
    map_score,
    risk_level,
)


# ── map_score ─────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("label,expected", [
    ("Poor", 90), ("Fair", 60), ("Good", 30), ("Excellent", 10), ("Unknown", 50),
])
def test_qualitative_mapping(label, expected):
    assert map_score(label) == expected


@pytest.mark.parametrize("field", ["cctv_coverage", "cctv_functionality", "guard_count_ratio", "response_time_score"])
def test_positive_fields_are_inverted(field):
    # Higher coverage/adequacy = better security = LOWER risk.
    assert map_score(100, field) == 0
    assert map_score(0, field) == 100
    assert map_score(75, field) == 25


def test_positive_fields_are_clamped():
    assert map_score(150, "cctv_coverage") == 0
    assert map_score(-20, "cctv_coverage") == 100


def test_risk_oriented_numeric_fields_pass_through():
    assert map_score(40, "incident_severity_score") == 40
    assert map_score(40) == 40


# ── compute_scores ────────────────────────────────────────────────────────────

def test_better_cctv_coverage_lowers_risk():
    def physical(coverage):
        data = {"Physical Security": {
            "perimeter_condition": "Good", "cctv_coverage": coverage,
            "cctv_functionality": 85, "lighting_quality": "Good", "entry_exit_control": "Good",
        }}
        return compute_scores(data)[0]["Physical Security"]

    assert physical(100) < physical(0)


def test_weights_and_overall():
    data = {cat: {"x": "Poor"} for cat in [
        "Physical Security", "Access Control", "Personnel",
        "Incident History", "Emergency Preparedness",
    ]}
    category_scores, contributions, overall = compute_scores(data)
    assert all(v == 90 for v in category_scores.values())
    assert contributions["Access Control"] == pytest.approx(27.0)    # 90 * 0.30
    assert contributions["Emergency Preparedness"] == pytest.approx(9.0)  # 90 * 0.10
    assert overall == pytest.approx(90.0)  # weights sum to 1


@pytest.mark.parametrize("score,level", [
    (0, "Low"), (40, "Low"), (40.01, "Moderate"), (60, "Moderate"),
    (60.01, "High"), (80, "High"), (80.01, "Critical"), (100, "Critical"),
])
def test_risk_level_boundaries(score, level):
    assert risk_level(score)[1] == level


# ── Risk velocity ─────────────────────────────────────────────────────────────

def test_risk_velocity_flags_significant_changes():
    prev = {"Physical Security": 30, "Access Control": 30}
    curr = {"Physical Security": 45, "Access Control": 32}
    v = compute_risk_velocity(curr, 40.0, prev, 30.0)
    assert v["overall_delta"] == 10.0
    assert v["direction"] == "worsening"
    assert v["significant"] is True
    assert set(v["category_changes"]) == {"Physical Security"}
    assert v["category_changes"]["Physical Security"]["direction"] == "worsened"


def test_risk_velocity_small_change_not_significant():
    scores = {"Physical Security": 30}
    v = compute_risk_velocity(scores, 30.0, {"Physical Security": 28}, 27.0)
    assert v["direction"] == "worsening"
    assert v["significant"] is False
    assert v["category_changes"] == {}
