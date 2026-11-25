"""Password hashing and access tokens.

- Passwords: argon2id via argon2-cffi (replaces the unmaintained passlib).
  Hashes are standard PHC strings ("$argon2id$v=19$m=65536,t=3,p=4$..."), so
  hashes created earlier through passlib verify unchanged.
- Tokens: HS256 JWTs via PyJWT (replaces python-jose, which is unmaintained
  and has published CVEs). Same format, so tokens issued before the switch
  stay valid until they expire.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

from app.config import settings

# argon2-cffi defaults: argon2id, m=64 MiB, t=3, p=4 (same as the old passlib setup).
_hasher = PasswordHasher()

# Verified against when the email doesn't exist, so "unknown email" and
# "wrong password" take the same time and can't be told apart by timing.
_DUMMY_HASH = _hasher.hash("timing-equaliser; not a real password")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, hashed: str) -> Tuple[bool, Optional[str]]:
    """Return (valid, new_hash). new_hash is set when the stored hash uses
    outdated parameters and should be replaced (transparent upgrade on login)."""
    try:
        _hasher.verify(hashed, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False, None
    if _hasher.check_needs_rehash(hashed):
        return True, _hasher.hash(password)
    return True, None


def spend_verify_time(password: str) -> None:
    """Do the work of a failed verification (see _DUMMY_HASH)."""
    try:
        _hasher.verify(_DUMMY_HASH, password)
    except VerifyMismatchError:
        pass


def create_access_token(subject: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": subject,
        "iat": now,
        "exp": now + timedelta(minutes=settings.JWT_EXPIRE_MINUTES),
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> Optional[str]:
    """Return the token's subject (email), or None if the token is invalid,
    expired, tampered with, or uses an unexpected algorithm."""
    if not token:
        return None
    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET_KEY,
            algorithms=[settings.JWT_ALGORITHM],  # pinned: never trust the token's own "alg"
            options={"require": ["exp", "sub"]},
        )
    except jwt.PyJWTError:
        return None
    subject = payload.get("sub")
    return subject if isinstance(subject, str) and subject else None
