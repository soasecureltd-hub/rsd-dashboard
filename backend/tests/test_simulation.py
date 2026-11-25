"""What-If simulation: real scoring + model on edited inputs, nothing saved."""
from app import models
from tests.conftest import assessment_payload

THREATS = ("unauthorized_access", "insider_threat", "emergency_failure", "perimeter_breach")


def _simulate(client, headers, a_id, body):
    return client.post(f"/api/risk/assess/{a_id}/simulate", json=body, headers=headers)


def test_responses_include_input_data(client, make_user, create_assessment):
    headers = make_user()
    created = create_assessment(headers, quality="Fair", cctv_coverage=42)
    assert created["input_data"]["physical_security"]["cctv_coverage"] == 42
    fetched = client.get(f"/api/risk/assess/{created['id']}", headers=headers).json()
    listed = client.get("/api/risk/assessments", headers=headers).json()[0]
    assert fetched["input_data"] == created["input_data"] == listed["input_data"]


def test_unchanged_scenario_matches_baseline(client, make_user, create_assessment):
    headers = make_user()
    created = create_assessment(headers, quality="Fair")
    r = _simulate(client, headers, created["id"], assessment_payload(quality="Fair"))
    assert r.status_code == 200
    body = r.json()
    assert body["scenario"] == body["baseline"]
    assert body["baseline"]["overall_score"] == created["overall_score"]


def test_improvements_lower_score_and_threats(client, make_user, create_assessment):
    headers = make_user()
    a_id = create_assessment(headers, quality="Fair")["id"]
    better = assessment_payload(quality="Excellent", cctv_coverage=100, guard_count_ratio=100)

    body = _simulate(client, headers, a_id, better).json()
    base, scen = body["baseline"], body["scenario"]
    assert scen["overall_score"] < base["overall_score"]
    assert scen["risk_level"] == "Low"
    for t in THREATS:
        assert scen["threats"][t] < base["threats"][t], t


def test_targeted_change_moves_its_category(client, make_user, create_assessment):
    """Editing only access-control answers changes Access Control, not Personnel."""
    headers = make_user()
    a_id = create_assessment(headers, quality="Fair")["id"]
    scenario = assessment_payload(quality="Fair")
    scenario["access_control"] = {k: "Excellent" for k in scenario["access_control"]}

    body = _simulate(client, headers, a_id, scenario).json()
    base, scen = body["baseline"]["category_scores"], body["scenario"]["category_scores"]
    assert scen["Access Control"] < base["Access Control"]
    assert scen["Personnel"] == base["Personnel"]


def test_simulation_saves_nothing(client, db, make_user, create_assessment):
    headers = make_user()
    a_id = create_assessment(headers, quality="Fair")["id"]
    _simulate(client, headers, a_id, assessment_payload(quality="Poor"))
    _simulate(client, headers, a_id, assessment_payload(quality="Excellent"))

    assert db.query(models.Assessment).count() == 1
    assert db.query(models.AIPrediction).count() == 0
    stored = client.get(f"/api/risk/assess/{a_id}", headers=headers).json()
    assert stored["risk_level"] == "Moderate"


def test_simulation_validates_input(client, make_user, create_assessment):
    headers = make_user()
    a_id = create_assessment(headers)["id"]
    bad = assessment_payload(cctv_coverage=150)
    assert _simulate(client, headers, a_id, bad).status_code == 422


def test_simulation_scoped_to_owner(client, make_user, create_assessment):
    a_id = create_assessment(make_user("alice@example.com"))["id"]
    bob = make_user("bob@example.com")
    assert _simulate(client, bob, a_id, assessment_payload()).status_code == 404


def test_simulation_requires_auth(client, make_user, create_assessment):
    a_id = create_assessment(make_user())["id"]
    r = client.post(f"/api/risk/assess/{a_id}/simulate", json=assessment_payload())
    assert r.status_code == 401
