"""Input validation on the assessment and list endpoints."""
import pytest

from tests.conftest import assessment_payload


def _post(client, headers, body):
    return client.post("/api/risk/assess", json=body, headers=headers)


@pytest.mark.parametrize("section,field,value", [
    ("physical_security", "perimeter_condition", "Gud"),       # typo
    ("access_control", "after_hours_security", "good"),         # wrong case
    ("emergency_preparedness", "staff_readiness", ""),          # empty
    ("personnel", "training_frequency", 30),                    # number instead of rating
])
def test_invalid_quality_rejected(client, make_user, section, field, value):
    body = assessment_payload()
    body[section][field] = value
    r = _post(client, make_user(), body)
    assert r.status_code == 422
    assert r.json()["detail"][0]["loc"][-1] == field


@pytest.mark.parametrize("section,field,value", [
    ("physical_security", "cctv_coverage", 101),
    ("physical_security", "cctv_functionality", -1),
    ("personnel", "guard_count_ratio", 1000),
    ("incident_history", "incident_severity_score", None),
    ("incident_history", "response_time_score", "fast"),
])
def test_invalid_numeric_rejected(client, make_user, section, field, value):
    body = assessment_payload()
    body[section][field] = value
    assert _post(client, make_user(), body).status_code == 422


@pytest.mark.parametrize("value", [0, 100, 55.5])
def test_numeric_boundaries_accepted(client, make_user, value):
    body = assessment_payload(cctv_coverage=value, incident_type_score=value)
    assert _post(client, make_user(), body).status_code == 200


def test_every_quality_value_accepted(client, make_user):
    headers = make_user()
    for quality in ("Poor", "Fair", "Good", "Excellent"):
        assert _post(client, headers, assessment_payload(quality=quality)).status_code == 200


def test_facility_name_stripped_and_limited(client, make_user):
    headers = make_user()
    r = _post(client, headers, assessment_payload(facility_name="  Warehouse 7  "))
    assert r.status_code == 200
    assert r.json()["facility_name"] == "Warehouse 7"

    assert _post(client, headers, assessment_payload(facility_name="x" * 201)).status_code == 422
    assert _post(client, headers, assessment_payload(facility_name=None)).status_code == 200


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "limit=-5", "skip=-1"])
def test_list_pagination_bounds(client, make_user, query):
    r = client.get(f"/api/risk/assessments?{query}", headers=make_user())
    assert r.status_code == 422


def test_list_pagination_in_bounds(client, make_user, create_assessment):
    headers = make_user()
    ids = [create_assessment(headers)["id"] for _ in range(3)]
    r = client.get("/api/risk/assessments?skip=1&limit=1", headers=headers)
    assert r.status_code == 200
    assert [a["id"] for a in r.json()] == [ids[1]]
