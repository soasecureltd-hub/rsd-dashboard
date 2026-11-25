"""Authentication routes: register, login, me"""
import math

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from app import schemas, crud
from app.db import get_db
from app.dependencies import client_ip, get_current_user
from app.rate_limit import login_limiter
from app.security import create_access_token

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _login(db: Session, email: str, password: str, ip: str) -> schemas.Token:
    """Shared by both login endpoints: rate limit, verify, issue token."""
    wait = login_limiter.retry_after(email, ip)
    if wait:
        minutes = max(1, math.ceil(wait / 60))
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Too many failed login attempts. Try again in {minutes} minute{'s' if minutes > 1 else ''}.",
            headers={"Retry-After": str(wait)},
        )

    user = crud.authenticate_user(db, email, password)
    if not user:
        login_limiter.record_failure(email, ip)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    login_limiter.record_success(email, ip)
    return schemas.Token(access_token=create_access_token(user.email))


@router.post("/register", response_model=schemas.UserResponse, status_code=201)
def register(user: schemas.UserCreate, db: Session = Depends(get_db)):
    if crud.get_user_by_email(db, user.email):
        raise HTTPException(status_code=400, detail="Email already registered")
    return crud.create_user(db, user)


@router.post("/login", response_model=schemas.Token)
def login_form(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    """OAuth2 form-based login (username field = email). Used by FastAPI's OAuth2 docs."""
    return _login(db, form_data.username, form_data.password, client_ip(request))


@router.post("/login/json", response_model=schemas.Token)
def login_json(request: Request, credentials: schemas.UserLogin, db: Session = Depends(get_db)):
    """JSON body login — convenience endpoint for frontend."""
    return _login(db, credentials.email, credentials.password, client_ip(request))


@router.get("/me", response_model=schemas.UserResponse)
def get_me(current_user=Depends(get_current_user)):
    return current_user
