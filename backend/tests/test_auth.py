"""Authentication endpoints."""


def test_register_login_and_me(client, make_user):
    headers = make_user("alice@example.com")
    r = client.get("/api/auth/me", headers=headers)
    assert r.status_code == 200
    assert r.json()["email"] == "alice@example.com"
    assert "hashed_password" not in r.json()


def test_duplicate_registration_rejected(client, make_user):
    make_user("alice@example.com")
    r = client.post("/api/auth/register",
                    json={"email": "alice@example.com", "password": "password123"})
    assert r.status_code == 400


def test_short_password_rejected(client):
    r = client.post("/api/auth/register", json={"email": "a@example.com", "password": "short"})
    assert r.status_code == 422


def test_wrong_password_rejected(client, make_user):
    make_user("alice@example.com", "password123")
    r = client.post("/api/auth/login/json",
                    json={"email": "alice@example.com", "password": "wrong-password"})
    assert r.status_code == 401


def test_form_login(client, make_user):
    make_user("alice@example.com", "password123")
    r = client.post("/api/auth/login",
                    data={"username": "alice@example.com", "password": "password123"})
    assert r.status_code == 200
    assert r.json()["token_type"] == "bearer"


def test_me_requires_token(client):
    assert client.get("/api/auth/me").status_code == 401


def test_me_rejects_garbage_token(client):
    r = client.get("/api/auth/me", headers={"Authorization": "Bearer not-a-jwt"})
    assert r.status_code == 401


def test_cors_allows_listed_origin(client):
    r = client.get("/health", headers={"Origin": "http://localhost:5173"})
    assert r.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_cors_rejects_unlisted_origin(client):
    r = client.get("/health", headers={"Origin": "https://evil.example.com"})
    assert "access-control-allow-origin" not in r.headers


def test_cors_origin_regex_for_preview_deployments():
    """ALLOWED_ORIGIN_REGEX admits Vercel previews but nothing look-alike."""
    from fastapi import FastAPI
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.add_middleware(CORSMiddleware, allow_origins=[], allow_credentials=True,
                       allow_origin_regex=r"^https://rsd-frontend(-[a-z0-9-]+)?\.vercel\.app$")
    app.get("/")(lambda: {})
    c = TestClient(app)
    allowed = lambda o: c.get("/", headers={"Origin": o}).headers.get("access-control-allow-origin") == o
    assert allowed("https://rsd-frontend.vercel.app")
    assert allowed("https://rsd-frontend-git-main-team.vercel.app")
    assert not allowed("https://rsd-frontend.vercel.app.evil.com")
    assert not allowed("https://evil-rsd-frontend.vercel.app")
