"""Authentication endpoints: email/password, Google ID tokens, and guest play.

All three flows return the same `{token, user}` shape; the token is a bearer
JWT the frontend stores in localStorage. `GET /api/auth/config` tells the UI
whether Google sign-in has been configured (it needs a GOOGLE_CLIENT_ID).
"""

from __future__ import annotations

import os
import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from . import db, security, store
from .schemas import (
    AuthConfig,
    AuthResponse,
    GoogleLoginRequest,
    GuestLoginRequest,
    LoginRequest,
    RegisterRequest,
    UserOut,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])

_DB_UNAVAILABLE = "Database unavailable - set DATABASE_URL (Turso) to enable accounts."


def _google_client_id() -> Optional[str]:
    # Read per request so tests (and `vercel env pull`) can change it freely.
    return os.getenv("GOOGLE_CLIENT_ID") or None


def _user_out(user: dict) -> UserOut:
    return UserOut(**user)


@router.get("/config", response_model=AuthConfig)
def auth_config() -> AuthConfig:
    client_id = _google_client_id()
    return AuthConfig(google_enabled=bool(client_id), google_client_id=client_id)


@router.post("/register", response_model=AuthResponse, status_code=201)
def register(payload: RegisterRequest) -> AuthResponse:
    email = payload.email.strip().lower()
    if not security.is_valid_email(email):
        raise HTTPException(status_code=422, detail="Enter a valid email address.")
    name = payload.name.strip() or "Player"
    password_hash = security.hash_password(payload.password)
    try:
        user = store.create_user(name=name, provider="email", email=email, password_hash=password_hash)
    except store.DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail=_DB_UNAVAILABLE) from exc
    except db.DatabaseError as exc:
        if store.is_unique_violation(exc):
            raise HTTPException(status_code=409, detail="An account with that email already exists.")
        raise HTTPException(status_code=503, detail=_DB_UNAVAILABLE) from exc
    return AuthResponse(token=security.create_token(user["id"]), user=_user_out(user))


@router.post("/login", response_model=AuthResponse)
def login(payload: LoginRequest) -> AuthResponse:
    email = payload.email.strip().lower()
    try:
        found = store.get_user_with_password(email)
    except db.DatabaseError as exc:
        raise HTTPException(status_code=503, detail=_DB_UNAVAILABLE) from exc
    if found is None or not security.verify_password(payload.password, found[1]):
        raise HTTPException(status_code=401, detail="Incorrect email or password.")
    user = found[0]
    return AuthResponse(token=security.create_token(user["id"]), user=_user_out(user))


@router.post("/google", response_model=AuthResponse)
def google_login(payload: GoogleLoginRequest) -> AuthResponse:
    client_id = _google_client_id()
    if not client_id:
        raise HTTPException(
            status_code=503, detail="Google sign-in is not configured (set GOOGLE_CLIENT_ID)."
        )
    try:
        claims = security.verify_google_credential(payload.credential, client_id)
    except security.GoogleVerificationError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    sub = claims.get("sub") or None
    email = (claims.get("email") or "").strip().lower() or None
    name = claims.get("name") or (email.split("@")[0] if email else "Player")

    try:
        user = store.get_user_by_google_sub(sub) if sub else None
        if user is None and email:
            # First Google sign-in for an existing email account: link it.
            user = store.get_user_by_email(email)
            if user is not None and sub:
                store.attach_google_sub(user["id"], sub)
        if user is None:
            try:
                user = store.create_user(
                    name=name, provider="google", email=email, google_sub=sub
                )
            except db.DatabaseError as create_exc:
                if store.is_unique_violation(create_exc):
                    user = store.get_user_by_google_sub(sub) if sub else None
                    if user is None and email:
                        user = store.get_user_by_email(email)
                if user is None:
                    raise create_exc
    except store.DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail=_DB_UNAVAILABLE) from exc
    except db.DatabaseError as exc:
        raise HTTPException(status_code=503, detail=_DB_UNAVAILABLE) from exc

    return AuthResponse(token=security.create_token(user["id"]), user=_user_out(user))


@router.post("/guest", response_model=AuthResponse, status_code=201)
def guest_login(payload: GuestLoginRequest) -> AuthResponse:
    suffix = uuid.uuid4().hex[:4].upper()
    name = (payload.name or "").strip() or f"Guest-{suffix}"
    try:
        user = store.create_user(name=name[:40], provider="guest")
    except db.DatabaseError as exc:
        raise HTTPException(status_code=503, detail=_DB_UNAVAILABLE) from exc
    return AuthResponse(token=security.create_token(user["id"]), user=_user_out(user))


@router.get("/me", response_model=UserOut)
def me(user: dict = Depends(security.get_current_user)) -> UserOut:
    return _user_out(user)
