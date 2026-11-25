"""Shared test fixtures.

Environment variables MUST be set before any `app.*` import: settings, the DB
engine and the ML model path are all resolved at import time.
"""
import os
import shutil
import tempfile
from pathlib import Path

_TMP_DIR = Path(tempfile.mkdtemp(prefix="rsd-tests-"))
os.environ["DATABASE_URL"] = f"sqlite:///{(_TMP_DIR / 'test.db').as_posix()}"
os.environ["DEBUG"] = "True"
os.environ["JWT_SECRET_KEY"] = "test-only-secret-key-at-least-32-characters-long"
os.environ["MODEL_PATH"] = str(_TMP_DIR / "model.pkl")
os.environ["SENTRY_DSN"] = ""

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import Base, SessionLocal, engine  # noqa: E402
from app.main import app  # noqa: E402
from app.rate_limit import login_limiter  # noqa: E402


def pytest_sessionfinish(session, exitstatus):
    engine.dispose()  # release the SQLite file handle (Windows) before cleanup
    shutil.rmtree(_TMP_DIR, ignore_errors=True)


@pytest.fixture(autouse=True)
def _clean_db():
    """Fresh schema for every test."""
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield


@pytest.fixture(autouse=True)
def _fresh_login_limiter():
    """Failed-login counters are global; never let one test's failures leak into another."""
    login_limiter.reset()
    yield
    login_limiter.reset()


@pytest.fixture
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture
def make_user(client):
    """Register + log in a user; returns Authorization headers."""
    def _make(email="user@example.com", password="password123"):
        r = client.post("/api/auth/register", json={"email": email, "password": password})
        assert r.status_code == 201, r.text
        r = client.post("/api/auth/login/json", json={"email": email, "password": password})
        assert r.status_code == 200, r.text
        return {"Authorization": f"Bearer {r.json()['access_token']}"}
    return _make


def assessment_payload(quality="Good", facility_name="HQ Main", **numeric):
    """Build a valid /api/risk/assess body with every qualitative field = quality.

    Numeric fields default to the RiskForm defaults; override via kwargs,
    e.g. assessment_payload(cctv_coverage=100).
    """
    n = {
        "cctv_coverage": 75,
        "cctv_functionality": 85,
        "guard_count_ratio": 70,
        "incident_severity_score": 40,
        "incident_type_score": 35,
        "response_time_score": 60,
        **numeric,
    }
    q = quality
    return {
        "facility_name": facility_name,
        "physical_security": {
            "perimeter_condition": q,
            "cctv_coverage": n["cctv_coverage"],
            "cctv_functionality": n["cctv_functionality"],
            "lighting_quality": q,
            "entry_exit_control": q,
        },
        "access_control": {
            "visitor_management": q,
            "id_verification": q,
            "restricted_area_protection": q,
            "after_hours_security": q,
        },
        "personnel": {
            "guard_count_ratio": n["guard_count_ratio"],
            "training_frequency": q,
            "background_checks": q,
            "shift_coverage": q,
        },
        "incident_history": {
            "incident_severity_score": n["incident_severity_score"],
            "incident_type_score": n["incident_type_score"],
            "response_time_score": n["response_time_score"],
            "documentation_quality": q,
        },
        "emergency_preparedness": {
            "emergency_plan": q,
            "drill_frequency": q,
            "communication_system": q,
            "staff_readiness": q,
        },
    }


@pytest.fixture
def create_assessment(client):
    """POST an assessment; returns the response JSON."""
    def _create(headers, **kwargs):
        r = client.post("/api/risk/assess", json=assessment_payload(**kwargs), headers=headers)
        assert r.status_code == 200, r.text
        return r.json()
    return _create
