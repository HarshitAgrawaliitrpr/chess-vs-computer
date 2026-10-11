"""Tiny database layer: Turso (libSQL over HTTP) in production, file: SQLite locally.

Design notes
------------
* Every call opens a *short-lived* synchronous `libsql_client` and closes it
  before returning. The sync client keeps a background thread alive until
  `close()` is called, which would hang interpreter shutdown (pytest/CI), so we
  never hold one open between requests. Opening a `file:` connection is cheap
  (microseconds) and a Turso connection is a plain HTTP client.
* The same SQL runs on both backends because Turso *is* SQLite. DDL uses
  `IF NOT EXISTS`, so schema creation is idempotent per call.
* The engine endpoints never touch this layer - if the database is missing or
  unconfigured the chess game keeps working and only the auth endpoints
  degrade to 503.
"""

from __future__ import annotations

import os
from typing import Any, List, Optional, Sequence, Tuple

import libsql_client
from libsql_client import Statement

DEFAULT_DATABASE_URL = "file:./chess.db"


class DatabaseError(Exception):
    """Any database failure (unreachable, read-only FS, constraint, ...)."""


def database_url() -> str:
    # .strip(): copy-paste from the Turso dashboard often drags a trailing
    # newline into the value.
    url = os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL).strip()
    # `libsql://` selects the WebSocket transport in libsql_client, which newer
    # Turso databases reject (HRANA over HTTP only). The https endpoint speaks
    # the same protocol everywhere, so normalise - both URL forms then work.
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://") :]
    return url


def database_auth_token() -> Optional[str]:
    return os.getenv("DATABASE_AUTH_TOKEN", "").strip() or None


def _open() -> libsql_client.ClientSync:
    url = database_url()
    token = database_auth_token()
    kwargs = {"auth_token": token} if token else {}
    try:
        return libsql_client.create_client_sync(url, **kwargs)
    except Exception as exc:  # pragma: no cover - depends on the environment
        raise DatabaseError(f"cannot open database {url!r}: {exc}") from exc


def _args(params: Sequence[Any]) -> Optional[list]:
    return list(params) if params else None


def query(sql: str, params: Sequence[Any] = ()) -> List[Tuple[Any, ...]]:
    """Run a SELECT and return the rows as plain tuples."""
    client = _open()
    try:
        result = client.execute(Statement(sql, _args(params)))
        return [tuple(row) for row in result.rows]
    except Exception as exc:
        raise DatabaseError(str(exc)) from exc
    finally:
        client.close()


def execute(sql: str, params: Sequence[Any] = ()) -> int:
    """Run a write statement; returns the number of affected rows."""
    client = _open()
    try:
        result = client.execute(Statement(sql, _args(params)))
        return int(getattr(result, "rows_affected", 0) or 0)
    except Exception as exc:
        raise DatabaseError(str(exc)) from exc
    finally:
        client.close()
