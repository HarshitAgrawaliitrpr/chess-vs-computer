# HANDOFF — Project State (read this first in a new session)

> Last updated: 2026-10-11 — everything below is deployed, live and verified.
> Secrets are deliberately NOT in this file; see "Where things live".

## What this is

Player-vs-Computer chess: React 18 + Vite frontend, FastAPI backend with a
custom minimax/alpha-beta engine, accounts + game history on **Turso**
(libSQL), Harness CI/CD, auto-deploy to Vercel.

- **Live:** https://chess-vs-computer-five.vercel.app
- **Repo:** https://github.com/HarshitAgrawaliitrpr/chess-vs-computer (public, branch `main`)
- Auto-deploy: push to `main` → production in ~30s (verified repeatedly).

## Status: feature-complete

- [x] Engine (negamax + alpha-beta, TT, quiescence, 4 difficulty profiles)
- [x] Full chess rules via chess.js + pre-move queue (single slot, auto-play, discard-if-illegal)
- [x] Game-over overlay (win/loss/draw) + Play again
- [x] Footer credit "CREATED BY HARSHIT AGRAWAL WITH MIMO"
- [x] Auth: email/password (bcrypt), guest (UUID), Google (GIS ID token — code ready, disabled until GOOGLE_CLIENT_ID)
- [x] JWT sessions (HS256, 30 days), `users` + `games` tables on Turso
- [x] Auto-save finished games + "My games" panel
- [x] Leaderboard: top players by points (win=1, draw=0.5), difficulty filter,
      top-3 medals; public endpoint `GET /api/leaderboard`, refreshes on
      `game-saved` like the history panel
- [x] Tests: 34 backend (pytest) + 39 frontend (vitest) — all green
- [ ] Optional: Google button (needs GOOGLE_CLIENT_ID env var in Vercel; see README)
- [x] Security: all temporary tokens (Vercel, Turso CLI-less flow) revoked/verified dead

## Where things live

- Backend app: `backend/app/` — `main.py` (engine routes + router wiring +
  static mount), `db.py` (libsql-client layer), `store.py` (schema + repo +
  leaderboard aggregate), `security.py` (bcrypt/JWT/Google), `routes_auth.py`,
  `routes_games.py`, `routes_leaderboard.py`
- Frontend: `frontend/src/` — `auth/AuthContext.jsx`, `api/authClient.js`,
  `components/LoginScreen.jsx`, `components/GameHistory.jsx`,
  `hooks/useChessGame.js` (all game + pre-move logic)
- Tests: `backend/tests/` (incl. `conftest.py` — isolated temp DB per session),
  `frontend/src/__tests__/`
- Vercel env vars (set in dashboard, scopes Production+Preview):
  `DATABASE_URL` (libsql://…turso.io), `DATABASE_AUTH_TOKEN`, `SECRET_KEY`
- Turso DB: `turso-db-create-chess-vs-computer-harshit-iitrpr` (ap-south-1) —
  note the odd DB name (dashboard wizard swallowed the CLI phrase); harmless.
- `backend/scripts/turso_smoke.py` — full live-DB check (uses env vars, deletes its rows)
- `backend/scripts/selfplay.py` — engine strength monotonicity guard

## Gotchas discovered the hard way (don't re-learn these)

1. **Python 3.14 has no `libsql` wheel** (Rust build fails) — the project uses
   pure-Python `libsql-client` instead.
2. **`libsql://` = WebSocket transport** and newer Turso DBs reject it (400).
   `app/db.py` auto-normalizes `libsql://` → `https://` (HRANA over HTTP).
3. **libsql-client sync clients hang interpreter exit if not `close()`d** —
   `db.py` opens+closes a client per call (pytest would hang otherwise).
4. **Vercel env vars are scoped** — a var saved with only "Preview" checked is
   invisible in production (this caused the one production 503 incident).
   After changing env vars you must Redeploy (or push) — they don't hot-reload.
5. react-chessboard v4: board highlights prop is `customSquareStyles`;
   `onPieceDrop(source, target)` returns false to keep pieces in place (pre-move).
6. Frontend tests: no jest-dom — use plain DOM assertions; `@testing-library/user-event`
   is installed for realistic form/click simulation; act() gotchas in hook tests
   (assert after act, waitFor sees final state with instant fake engines).
7. `backend/pytest.ini` has `addopts = -q` — running `pytest -q` again suppresses
   the summary line (looks like missing output; exit code is the truth).
8. This machine: Windows, miniconda py3.14, Node 24, **no Docker CLI**, **no
   browser tooling**, Vercel CLI present but fine-grained tokens can't use
   `whoami`/project settings (use REST API with `?teamId=` instead).

## Dev commands

```bash
cd backend  && python -m pytest          # 30 tests
cd frontend && npx vitest run            # 35 tests
cd frontend && npx eslint src            # lint
cd frontend && npm run build             # production bundle
cd backend  && uvicorn app.main:app --reload --port 8000
```

## Ideas queued (user hasn't picked yet)

Leaderboard/ratings — DONE (2026-10-11, see above); remaining ideas: sound
effects, mobile polish, Google login completion, move annotations for the
engine (why did it play that).
