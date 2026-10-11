"""Shared test setup.

Environment variables must be in place *before* any test module imports
`app.main` (which pulls in the db/security layers). conftest.py is imported
first by pytest, so this is the right place: an isolated temp-file database
per test session and a fixed JWT secret (no `.jwt-secret` side file in CI).
"""

from __future__ import annotations

import os
import tempfile
import uuid

os.environ["DATABASE_URL"] = "file:" + os.path.join(
    tempfile.gettempdir(), f"chess_test_{uuid.uuid4().hex}.db"
)
os.environ.setdefault("SECRET_KEY", "test-secret-key-0123456789abcdef0123456789abcdef")
os.environ.pop("GOOGLE_CLIENT_ID", None)  # keep `google_enabled` assertions stable
