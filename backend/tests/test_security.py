"""Password hashing, JWTs, inactive accounts and login rate limiting."""
import base64
import json
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app import models, security
from app.rate_limit import LoginRateLimiter

# Produced by the previous stack (passlib CryptContext(["argon2"]) and
# python-jose) before the switch, to prove existing users are unaffected.
LEGACY_PASSLIB_HASH = (
    "$argon2id$v=19$m=65536,t=3,p=4$/J8T4ryX0pqTkvKeM4Ywhg$"
    "UPXkHl2DnanVTlW7ZT0FOSqknR6uhf9eMglTCm+acQM"
)
LEGACY_PASSWORD = "legacy-password-123"
LEGACY_JOSE_TOKEN = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJzdWIiOiJsZWdhY3lAZXhhbXBsZS5jb20iLCJleHAiOjIxMTA5MjgyMTR9."
    "zy_zYDJDGWRbjAfbdorTwpmvyZVQznJorezP9W0_uOg"
)
LEGACY_SECRET = "compat-secret-key-that-is-at-least-32-chars"


def _login(client, email, password):
    return client.post("/api/auth/login/json", json={"email": email, "password": password})


def _b64(obj):
    return base64.urlsafe_b64encode(json.dumps(obj).encode()).rstrip(b"=").decode()


# ── Passwords ─────────────────────────────────────────────────────────────────

def test_hash_roundtrip():
    h = security.hash_password("correct horse battery")
    assert h.startswith("$argon2id$")
    assert security.verify_password("correct horse battery", h) == (True, None)
    assert security.verify_password("wrong", h) == (False, None)


def test_passlib_hashes_still_verify():
    assert security.verify_password(LEGACY_PASSWORD, LEGACY_PASSLIB_HASH)[0] is True
    assert security.verify_password("nope", LEGACY_PASSLIB_HASH)[0] is False


def test_garbage_hash_is_rejected_not_crashing():
    assert security.verify_password("x", "not-a-hash") == (False, None)


def test_weak_hash_upgraded_on_login(client, db):
    from argon2 import PasswordHasher
    weak = PasswordHasher(time_cost=1, memory_cost=1024, parallelism=1).hash("password123")
    db.add(models.User(email="old@example.com", hashed_password=weak))
    db.commit()

    assert _login(client, "old@example.com", "password123").status_code == 200
    db.expire_all()
    stored = db.query(models.User).filter_by(email="old@example.com").one().hashed_password
    assert stored != weak and "m=65536" in stored


def test_legacy_user_can_log_in(client, db):
    db.add(models.User(email="legacy@example.com", hashed_password=LEGACY_PASSLIB_HASH))
    db.commit()
    assert _login(client, "legacy@example.com", LEGACY_PASSWORD).status_code == 200


# ── Tokens ────────────────────────────────────────────────────────────────────

def test_python_jose_tokens_still_valid(monkeypatch):
    monkeypatch.setattr(security.settings, "JWT_SECRET_KEY", LEGACY_SECRET)
    assert security.decode_access_token(LEGACY_JOSE_TOKEN) == "legacy@example.com"


def test_token_roundtrip():
    assert security.decode_access_token(security.create_access_token("a@example.com")) == "a@example.com"


def test_tampered_token_rejected():
    header, payload, sig = security.create_access_token("a@example.com").split(".")
    forged = ".".join([header, _b64({"sub": "admin@example.com", "exp": 9999999999}), sig])
    assert security.decode_access_token(forged) is None


def test_alg_none_rejected():
    unsigned = ".".join([_b64({"alg": "none", "typ": "JWT"}), _b64({"sub": "a@example.com", "exp": 9999999999}), ""])
    assert security.decode_access_token(unsigned) is None


def test_wrong_secret_rejected():
    token = jwt.encode({"sub": "a@example.com", "exp": 9999999999}, "x" * 40, algorithm="HS256")
    assert security.decode_access_token(token) is None


def test_expired_token_rejected():
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    token = jwt.encode({"sub": "a@example.com", "exp": past}, security.settings.JWT_SECRET_KEY, algorithm="HS256")
    assert security.decode_access_token(token) is None


@pytest.mark.parametrize("claims", [{"sub": "a@example.com"}, {"exp": 9999999999}])
def test_token_missing_required_claims_rejected(claims):
    token = jwt.encode(claims, security.settings.JWT_SECRET_KEY, algorithm="HS256")
    assert security.decode_access_token(token) is None


# ── Inactive accounts ─────────────────────────────────────────────────────────

def test_inactive_user_cannot_log_in_or_use_token(client, db, make_user):
    headers = make_user("gone@example.com")
    db.query(models.User).filter_by(email="gone@example.com").update({"is_active": False})
    db.commit()

    assert client.get("/api/auth/me", headers=headers).status_code == 401
    assert client.get("/api/risk/assessments", headers=headers).status_code == 401
    assert _login(client, "gone@example.com", "password123").status_code == 401


# ── Rate limiting (endpoint) ──────────────────────────────────────────────────

def test_lockout_after_repeated_failures(client, make_user):
    make_user("alice@example.com", "password123")
    for _ in range(5):
        assert _login(client, "alice@example.com", "wrong-password").status_code == 401

    r = _login(client, "alice@example.com", "password123")  # even the right password
    assert r.status_code == 429
    assert 0 < int(r.headers["Retry-After"]) <= 15 * 60
    assert "Try again in" in r.json()["detail"]


def test_form_login_shares_the_limit(client, make_user):
    make_user("alice@example.com", "password123")
    for _ in range(5):
        _login(client, "alice@example.com", "wrong-password")
    r = client.post("/api/auth/login", data={"username": "alice@example.com", "password": "password123"})
    assert r.status_code == 429


def test_success_resets_the_counter(client, make_user):
    make_user("alice@example.com", "password123")
    for _ in range(4):
        _login(client, "alice@example.com", "wrong-password")
    assert _login(client, "alice@example.com", "password123").status_code == 200
    for _ in range(4):
        assert _login(client, "alice@example.com", "wrong-password").status_code == 401
    assert _login(client, "alice@example.com", "password123").status_code == 200


def test_lockout_is_per_account(client, make_user):
    make_user("alice@example.com", "password123")
    make_user("bob@example.com", "password123")
    for _ in range(5):
        _login(client, "alice@example.com", "wrong-password")
    assert _login(client, "bob@example.com", "password123").status_code == 200


def test_unknown_emails_count_too(client):
    for _ in range(5):
        assert _login(client, "nobody@example.com", "x").status_code == 401
    assert _login(client, "nobody@example.com", "x").status_code == 429


# ── Rate limiting (unit, with a fake clock) ───────────────────────────────────

class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def test_window_expires():
    clock = FakeClock()
    limiter = LoginRateLimiter(window_seconds=900, clock=clock)
    for _ in range(5):
        limiter.record_failure("a@x.com", "1.1.1.1")
    assert limiter.retry_after("a@x.com", "1.1.1.1") == 900
    clock.now += 600
    assert limiter.retry_after("a@x.com", "1.1.1.1") == 300
    clock.now += 300
    assert limiter.retry_after("a@x.com", "1.1.1.1") == 0


def test_owner_on_another_ip_not_locked_out():
    limiter = LoginRateLimiter(clock=FakeClock())
    for _ in range(5):
        limiter.record_failure("victim@x.com", "6.6.6.6")  # attacker
    assert limiter.retry_after("victim@x.com", "6.6.6.6") > 0
    assert limiter.retry_after("victim@x.com", "2.2.2.2") == 0  # real owner


def test_password_spraying_from_one_ip_is_limited():
    limiter = LoginRateLimiter(clock=FakeClock())
    for i in range(30):
        limiter.record_failure(f"user{i}@x.com", "6.6.6.6")
    assert limiter.retry_after("fresh@x.com", "6.6.6.6") > 0
    assert limiter.retry_after("fresh@x.com", "2.2.2.2") == 0


def test_distributed_attack_on_one_account_is_limited():
    limiter = LoginRateLimiter(clock=FakeClock())
    for i in range(50):
        limiter.record_failure("target@x.com", f"10.0.0.{i}")
    assert limiter.retry_after("target@x.com", "10.0.1.1") > 0


def test_email_case_and_whitespace_normalised():
    limiter = LoginRateLimiter(clock=FakeClock())
    for _ in range(5):
        limiter.record_failure(" Alice@X.com ", "1.1.1.1")
    assert limiter.retry_after("alice@x.com", "1.1.1.1") > 0
