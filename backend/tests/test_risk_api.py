"""Risk assessment API: scoring, ownership, anomalies, predictions, PDF report."""
import pytest

from tests.conftest import assessment_payload


# ── Assessments ───────────────────────────────────────────────────────────────

def test_create_and_get_assessment(client, make_user, create_assessment):
    headers = make_user()
    created = create_assessment(headers)
    assert created["facility_name"] == "HQ Main"
    assert 0 <= created["overall_score"] <= 100
    assert set(created["category_scores"]) == {
        "Physical Security", "Access Control", "Personnel",
        "Incident History", "Emergency Preparedness",
    }

    r = client.get(f"/api/risk/assess/{created['id']}", headers=headers)
    assert r.status_code == 200
    assert r.json()["overall_score"] == created["overall_score"]


def test_assess_requires_auth(client):
    assert client.post("/api/risk/assess", json=assessment_payload()).status_code == 401


def test_invalid_payload_rejected(client, make_user):
    body = assessment_payload()
    del body["personnel"]
    assert client.post("/api/risk/assess", json=body, headers=make_user()).status_code == 422


def test_poor_facility_scores_higher_than_excellent(make_user, create_assessment):
    headers = make_user()
    poor = create_assessment(headers, quality="Poor", cctv_coverage=10, guard_count_ratio=10)
    excellent = create_assessment(headers, quality="Excellent", cctv_coverage=100, guard_count_ratio=100)
    assert poor["overall_score"] > excellent["overall_score"]


def test_users_cannot_see_each_others_assessments(client, make_user, create_assessment):
    alice, bob = make_user("alice@example.com"), make_user("bob@example.com")
    a_id = create_assessment(alice)["id"]

    assert client.get(f"/api/risk/assess/{a_id}", headers=bob).status_code == 404
    assert client.post(f"/api/risk/anomaly/{a_id}", headers=bob).status_code == 404
    assert client.post(f"/api/risk/predict/{a_id}", headers=bob).status_code == 404
    assert client.get("/api/risk/assessments", headers=bob).json() == []


def test_list_assessments_newest_first(client, make_user, create_assessment):
    headers = make_user()
    ids = [create_assessment(headers)["id"] for _ in range(3)]
    listed = [a["id"] for a in client.get("/api/risk/assessments", headers=headers).json()]
    assert listed == list(reversed(ids))


# ── Anomalies ─────────────────────────────────────────────────────────────────

def test_anomaly_detection(client, make_user, create_assessment):
    headers = make_user()
    a_id = create_assessment(headers, incident_severity_score=95)["id"]
    r = client.post(f"/api/risk/anomaly/{a_id}", headers=headers)
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "warning"
    assert body["total_anomalies"] == len(body["anomalies"])
    assert "incident_score" in {a["feature"] for a in body["anomalies"]}
    assert 0 <= body["anomaly_score"] <= 1
    assert body["risk_velocity"] is None  # first assessment: nothing to compare


def test_risk_velocity_compares_with_most_recent_prior(client, make_user, create_assessment):
    """Oldest = Poor, previous = Excellent, current = Good.

    Against the most recent prior (Excellent) the trend is *worsening*;
    against the oldest (Poor) it would wrongly read as improving.
    """
    headers = make_user()
    create_assessment(headers, quality="Poor")
    create_assessment(headers, quality="Excellent")
    current = create_assessment(headers, quality="Good")["id"]

    velocity = client.post(f"/api/risk/anomaly/{current}", headers=headers).json()["risk_velocity"]
    assert velocity["direction"] == "worsening"
    assert velocity["overall_delta"] > 0


# ── Predictions ───────────────────────────────────────────────────────────────

def test_predictions(client, make_user, create_assessment):
    headers = make_user()
    a_id = create_assessment(headers)["id"]
    r = client.post(f"/api/risk/predict/{a_id}", headers=headers)
    assert r.status_code == 200
    body = r.json()
    for key in ("unauthorized_access", "insider_threat", "emergency_failure", "perimeter_breach"):
        assert 0 <= body[key] <= 1
    assert "confidence" not in body


# ── PDF report ────────────────────────────────────────────────────────────────

def _report_url(a_id):
    return f"/api/risk/assess/{a_id}/report"


@pytest.mark.parametrize("with_prediction", [False, True])
def test_report_download(client, make_user, create_assessment, with_prediction):
    headers = make_user()
    a_id = create_assessment(headers)["id"]
    if with_prediction:  # exercises the AI-predictions table in the PDF
        assert client.post(f"/api/risk/predict/{a_id}", headers=headers).status_code == 200

    r = client.get(_report_url(a_id), headers=headers)
    assert r.status_code == 200, r.text
    assert r.headers["content-type"] == "application/pdf"
    assert r.headers["content-disposition"] == f'attachment; filename="RSD_Report_HQ_Main_{a_id}.pdf"'
    assert r.content.startswith(b"%PDF")
    # Single page: the footer used to trigger an automatic page break.
    assert r.content.count(b"/Type /Page\n") == 1, "report should be one page"


def test_report_rejects_token_in_query_string(client, make_user, create_assessment):
    headers = make_user()
    a_id = create_assessment(headers)["id"]
    token = headers["Authorization"].split()[1]
    assert client.get(f"{_report_url(a_id)}?token={token}").status_code == 401


def test_report_requires_auth(client, make_user, create_assessment):
    a_id = create_assessment(make_user())["id"]
    assert client.get(_report_url(a_id)).status_code == 401


def test_report_scoped_to_owner(client, make_user, create_assessment):
    a_id = create_assessment(make_user("alice@example.com"))["id"]
    bob = make_user("bob@example.com")
    assert client.get(_report_url(a_id), headers=bob).status_code == 404


def test_report_filename_header_exposed_to_cors(client, make_user, create_assessment):
    headers = make_user()
    a_id = create_assessment(headers)["id"]
    r = client.get(_report_url(a_id), headers={**headers, "Origin": "http://localhost:5173"})
    assert "Content-Disposition" in r.headers.get("access-control-expose-headers", "")


# ── Stored prediction lookup (history view) ───────────────────────────────────

def test_get_prediction_404_before_any_run(client, make_user, create_assessment):
    headers = make_user()
    a_id = create_assessment(headers)["id"]
    assert client.get(f"/api/risk/predict/{a_id}", headers=headers).status_code == 404


def test_get_prediction_returns_latest_without_creating_rows(client, db, make_user, create_assessment):
    from app import models

    headers = make_user()
    a_id = create_assessment(headers)["id"]
    ran = client.post(f"/api/risk/predict/{a_id}", headers=headers).json()

    for _ in range(3):
        got = client.get(f"/api/risk/predict/{a_id}", headers=headers)
        assert got.status_code == 200
        assert got.json() == ran  # same stored probabilities
    assert db.query(models.AIPrediction).filter_by(assessment_id=a_id).count() == 1


def test_get_prediction_scoped_to_owner(client, make_user, create_assessment):
    alice = make_user("alice@example.com")
    a_id = create_assessment(alice)["id"]
    client.post(f"/api/risk/predict/{a_id}", headers=alice)
    bob = make_user("bob@example.com")
    assert client.get(f"/api/risk/predict/{a_id}", headers=bob).status_code == 404


def test_reopened_old_assessment_only_compares_with_earlier_ones(client, make_user, create_assessment):
    """History view: an old assessment must not be compared with newer ones."""
    headers = make_user()
    first = create_assessment(headers, quality="Poor")["id"]
    middle = create_assessment(headers, quality="Excellent")["id"]
    create_assessment(headers, quality="Good")  # newer than both

    first_result = client.post(f"/api/risk/anomaly/{first}", headers=headers).json()
    assert first_result["risk_velocity"] is None  # nothing earlier

    velocity = client.post(f"/api/risk/anomaly/{middle}", headers=headers).json()["risk_velocity"]
    assert velocity["direction"] == "improving"  # Excellent vs the earlier Poor
