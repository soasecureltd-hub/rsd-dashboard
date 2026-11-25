"""Key findings: only risk-raising answers are concerns, in plain language."""
import pytest

from app.services.findings_service import FIELD_COPY, build_findings, unusual_combination
from tests.conftest import assessment_payload


def _fields(items):
    return {i["field"] for i in items}


# ── The old engine's false alarms must not come back ──────────────────────────

def test_default_good_answers_raise_no_concerns():
    """Regression: 'Good' after-hours security used to be a HIGH anomaly."""
    result = build_findings(assessment_payload(quality="Good"))
    assert result["concerns"] == []


def test_excellent_facility_has_no_concerns_only_strengths():
    """Regression: an excellent facility used to get four HIGH alerts."""
    best = assessment_payload(quality="Excellent", cctv_coverage=100, cctv_functionality=100,
                              guard_count_ratio=100, incident_severity_score=5,
                              incident_type_score=5, response_time_score=95)  # quality: higher = faster
    result = build_findings(best)
    assert result["concerns"] == []
    assert {"cctv_coverage", "guard_count_ratio", "after_hours_security"} <= _fields(result["strengths"])


def test_poor_facility_everything_is_urgent():
    worst = assessment_payload(quality="Poor", cctv_coverage=10, cctv_functionality=10,
                               guard_count_ratio=10, incident_severity_score=95,
                               incident_type_score=95, response_time_score=5)
    result = build_findings(worst)
    assert len(result["concerns"]) == len(FIELD_COPY)
    assert all(c["severity"] == "urgent" for c in result["concerns"])
    assert result["strengths"] == []


# ── Severity bands follow the scoring scale ───────────────────────────────────

@pytest.mark.parametrize("quality,expected", [
    ("Poor", "urgent"), ("Fair", "attention"), ("Good", None), ("Excellent", None),
])
def test_qualitative_bands(quality, expected):
    payload = assessment_payload(quality="Good")
    payload["access_control"]["after_hours_security"] = quality
    concern = {c["field"]: c for c in build_findings(payload)["concerns"]}.get("after_hours_security")
    assert (concern["severity"] if concern else None) == expected


@pytest.mark.parametrize("coverage,expected", [
    (10, "urgent"),      # risk 90
    (20, "urgent"),      # risk 80
    (35, "attention"),   # risk 65
    (50, None),          # risk 50
    (90, "strength"),    # risk 10
])
def test_coverage_is_inverted(coverage, expected):
    """Coverage percentages: LOW coverage is the risk, high coverage a strength."""
    result = build_findings(assessment_payload(quality="Good", cctv_coverage=coverage))
    concern = {c["field"]: c for c in result["concerns"]}.get("cctv_coverage")
    if expected == "strength":
        assert "cctv_coverage" in _fields(result["strengths"])
    else:
        assert (concern["severity"] if concern else None) == expected


@pytest.mark.parametrize("score,expected", [(85, "urgent"), (65, "attention"), (40, None)])
def test_incident_scores_are_risk_scores(score, expected):
    result = build_findings(assessment_payload(quality="Good", incident_severity_score=score))
    concern = {c["field"]: c for c in result["concerns"]}.get("incident_severity_score")
    assert (concern["severity"] if concern else None) == expected


# ── Plain language ────────────────────────────────────────────────────────────

def test_finding_reads_plainly():
    payload = assessment_payload(quality="Good", cctv_coverage=30)
    payload["access_control"]["after_hours_security"] = "Poor"
    concerns = {c["field"]: c for c in build_findings(payload)["concerns"]}

    after_hours = concerns["after_hours_security"]
    assert after_hours["headline"] == "After-hours security is rated Poor"
    assert after_hours["category"] == "Access Control"
    assert after_hours["why"] and after_hours["action"]

    assert concerns["cctv_coverage"]["headline"] == "CCTV coverage is only 30%"
    assert concerns["cctv_coverage"]["answer"] == "30%"


def test_no_jargon_in_any_copy():
    for label, why, action in FIELD_COPY.values():
        text = f"{label} {why} {action}".lower()
        for jargon in ("z-score", "sigma", "σ", "baseline", "anomal", "deviation", "feature"):
            assert jargon not in text, (label, jargon)


def test_most_urgent_first():
    payload = assessment_payload(quality="Good", incident_severity_score=65)
    payload["physical_security"]["lighting_quality"] = "Poor"
    concerns = build_findings(payload)["concerns"]
    assert [c["field"] for c in concerns] == ["lighting_quality", "incident_severity_score"]


def test_every_form_field_has_copy():
    sections = assessment_payload()
    fields = {f for k, v in sections.items() if isinstance(v, dict) for f in v}
    assert fields == set(FIELD_COPY)


# ── Unusual combination ───────────────────────────────────────────────────────

def test_unusual_combination_uses_own_history_when_available():
    scores = {"Physical Security": 30, "Access Control": 30, "Personnel": 30,
              "Incident History": 30, "Emergency Preparedness": 30}
    assert unusual_combination(scores, [])["compared_with"] == "typical_profiles"
    history = [scores] * 5
    assert unusual_combination(scores, history)["compared_with"] == "own_history"


# ── Endpoint ──────────────────────────────────────────────────────────────────

def test_velocity_only_compares_the_same_facility(client, make_user, create_assessment):
    headers = make_user()
    create_assessment(headers, quality="Poor", facility_name="Warehouse 7")
    create_assessment(headers, quality="Excellent", facility_name="Head Office")
    current = create_assessment(headers, quality="Good", facility_name="Warehouse 7")["id"]

    velocity = client.get(f"/api/risk/assess/{current}/findings", headers=headers).json()["risk_velocity"]
    # vs the earlier Warehouse 7 (Poor), not the more recent Head Office (Excellent)
    assert velocity["direction"] == "improving"
    assert velocity["previous_created_at"]


def test_unnamed_facilities_compare_with_each_other(client, make_user, create_assessment):
    headers = make_user()
    create_assessment(headers, quality="Poor", facility_name=None)
    create_assessment(headers, quality="Excellent", facility_name="Head Office")
    current = create_assessment(headers, quality="Good", facility_name=None)["id"]
    velocity = client.get(f"/api/risk/assess/{current}/findings", headers=headers).json()["risk_velocity"]
    assert velocity["direction"] == "improving"


def test_findings_require_auth_and_ownership(client, make_user, create_assessment):
    a_id = create_assessment(make_user("alice@example.com"))["id"]
    assert client.get(f"/api/risk/assess/{a_id}/findings").status_code == 401
    bob = make_user("bob@example.com")
    assert client.get(f"/api/risk/assess/{a_id}/findings", headers=bob).status_code == 404


def test_frontend_form_hints_use_the_same_thresholds():
    """The form's live hints (frontend/src/utils/risk.js) must agree with these rules."""
    import re
    from pathlib import Path
    from app.services import findings_service as fs
    from app.services.risk_service import QUAL_MAPPING

    js_path = Path(__file__).resolve().parents[2] / "frontend" / "src" / "utils" / "risk.js"
    if not js_path.exists():
        pytest.skip("frontend not checked out")
    js = js_path.read_text(encoding="utf-8")
    for name in ("URGENT_AT", "ATTENTION_AT", "STRENGTH_AT"):
        value = float(re.search(rf"export const {name} = (\d+(?:\.\d+)?);", js).group(1))
        assert value == getattr(fs, name), name
    for quality, risk in QUAL_MAPPING.items():
        assert re.search(rf"\b{quality}: {risk}\b", js), quality
