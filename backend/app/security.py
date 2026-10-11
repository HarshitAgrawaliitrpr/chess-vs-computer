"""Password hashing, JWT sessions and the `current_user` FastAPI dependency.

Sessions are stateless HS256 JWTs. The signing secret comes from `SECRET_KEY`
when set; otherwise a random secret is persisted to `<repo>/.jwt-secret` so
local sessions survive restarts (on a read-only host such as a serverless
function the fallback is an ephemeral secret - set SECRET_KEY there).
"""

from __future__ import annotations

import logging
import os
import re
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, Optional

import bcrypt
import jwt as pyjwt
from fastapi import Header, HTTPException

from . import store

logger = logging.getLogger("chess.auth")

JWT_ALGORITHM = "HS256"
JWT_EXPIRE_DAYS = int(os.getenv("JWT_EXPIRE_DAYS", "30"))
GOOGLE_JWKS_URI = "https://www.googleapis.com/oauth2/v3/certs"

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

_UNAUTHENTICATED = {"WWW-Authenticate": "Bearer"}


def is_valid_email(email: str) -> bool:
    return bool(EMAIL_RE.match(email)) and len(email) <= 254


# ---------------------------------------------------------------------------
# Secret + passwords
# ---------------------------------------------------------------------------


def _resolve_secret() -> str:
    env = os.getenv("SECRET_KEY")
    if env:
        return env
    path = Path(__file__).resolve().parents[2] / ".jwt-secret"
    try:
        if path.exists():
            existing = path.read_text(encoding="utf-8").strip()
            if existing:
                return existing
        secret = secrets.token_urlsafe(32)
        path.write_text(secret, encoding="utf-8")
        return secret
    except OSError:
        logger.warning("SECRET_KEY unset and %s is not writable; using an ephemeral secret.", path)
        return secrets.token_urlsafe(32)


SECRET_KEY = _resolve_secret()


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_password(password: str, password_hash: Optional[str]) -> bool:
    if not password_hash:
        return False
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("ascii"))
    except ValueError:  # pragma: no cover - malformed stored hash
        return False


# ---------------------------------------------------------------------------
# JWT sessions
# ---------------------------------------------------------------------------


def create_token(user_id: str) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": user_id,
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=JWT_EXPIRE_DAYS)).timestamp()),
    }
    return pyjwt.encode(payload, SECRET_KEY, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> Optional[str]:
    try:
        payload = pyjwt.decode(token, SECRET_KEY, algorithms=[JWT_ALGORITHM])
    except pyjwt.PyJWTError:
        return None
    sub = payload.get("sub")
    return sub if isinstance(sub, str) and sub else None


def get_current_user(authorization: Optional[str] = Header(default=None)) -> Dict[str, Any]:
    """FastAPI dependency: resolve the Bearer token into a user row."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Not authenticated", headers=_UNAUTHENTICATED)
    user_id = decode_token(authorization.split(" ", 1)[1].strip())
    if not user_id:
        raise HTTPException(
            status_code=401, detail="Invalid or expired token", headers=_UNAUTHENTICATED
        )
    try:
        user = store.get_user(user_id)
    except store.DatabaseUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Database unavailable.") from exc
    if user is None:
        raise HTTPException(status_code=401, detail="Unknown user", headers=_UNAUTHENTICATED)
    return user


# ---------------------------------------------------------------------------
# Google ID tokens
# ---------------------------------------------------------------------------


class GoogleVerificationError(Exception):
    """The Google credential could not be verified."""


def verify_google_credential(credential: str, client_id: str) -> Dict[str, Any]:
    """Verify a Google Identity Services ID token (RS256 + audience check)."""
    try:
        jwks = pyjwt.PyJWKClient(GOOGLE_JWKS_URI)
        signing_key = jwks.get_signing_key_from_jwt(credential).key
        return pyjwt.decode(
            credential,
            signing_key,
            algorithms=["RS256"],
            audience=client_id,
            options={"require": ["exp", "iat", "aud", "sub"]},
        )
    except Exception as exc:
        raise GoogleVerificationError("Google sign-in failed or the token expired.") from exc
