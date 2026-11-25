"""Shared FastAPI dependencies"""
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from app.db import get_db
from app import crud
from app.security import decode_access_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


def authenticate_token(token: str, db: Session):
    """Validate a JWT string and return the active user, or None.

    Used by get_current_user. Tokens must arrive in the Authorization header;
    never accept them as URL query params (they leak into logs and history).
    """
    email = decode_access_token(token)
    if email is None:
        return None
    user = crud.get_user_by_email(db, email=email)
    if user is None or not user.is_active:
        return None  # deactivated accounts lose access immediately
    return user


def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    """Validate JWT and return the current user."""
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    user = authenticate_token(token, db)
    if user is None:
        raise credentials_exception
    return user


def client_ip(request: Request) -> str:
    """Client address for rate limiting.

    Behind a proxy (Render), uvicorn runs with --proxy-headers and
    FORWARDED_ALLOW_IPS so request.client is the real client, not the proxy.
    """
    return request.client.host if request.client else "unknown"
