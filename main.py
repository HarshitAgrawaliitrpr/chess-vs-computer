"""Vercel entrypoint.

Vercel detects this root-level `main.py`, loads the FastAPI instance named
`app`, and routes every request to it:

    /api/engine/move  -> FastAPI engine API
    /, /assets/*      -> the built React app (served via app.frontend)

Locally nothing imports this file: development runs `uvicorn app.main:app`
from `backend/` plus the Vite dev server.
"""

from backend.app.main import app  # noqa: F401

__all__ = ["app"]