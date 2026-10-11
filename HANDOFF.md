# HANDOFF — Project State (read this first in a new session)

> Last updated: 2026-10-11 — everything below is deployed, live and verified.
> Secrets are deliberately NOT in this file; see "Where things live".

## What this is

Chess vs. computer (React 18 + Vite frontend, FastAPI backend with a custom
minimax/alpha-beta engine) **plus online human-vs-human multiplayer**;
accounts + game history on **Turso** (libSQL), Harness CI/CD, auto-deploy to
Vercel.

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
- [x] **Online multiplayer** (2026-10-11): invite codes + `/?join=CODE` links,
      server-authoritative moves (python-chess validated), 2.5s short polling
      (paused when tab hidden), auto-queen, resign/cancel, refresh-resume via
      localStorage; results written for BOTH players into history + leaderboard
      (`difficulty='online'`); prod E2E verified live
- [x] Tests: 43 backend (pytest) + 53 frontend (vitest) — all green
- [ ] Optional: Google button (needs GOOGLE_CLIENT_ID env var in Vercel; see README)
- [ ] Next: **NNUE evaluator** (user asked for it right after multiplayer)
- [x] Security: all temporary tokens (Vercel, Turso CLI-less flow) revoked/verified dead

## Where things live

- Backend app: `backend/app/` — `main.py` (engine routes + router wiring +
  static mount), `db.py` (libsql-client layer), `store.py` (schema + repo +
  leaderboard + `online_games`), `security.py` (bcrypt/JWT/Google),
  `routes_auth.py`, `routes_games.py`, `routes_leaderboard.py`,
  `routes_online.py` (create/join/poll/move/resign/cancel)
- Frontend: `frontend/src/` — `auth/AuthContext.jsx`, `api/authClient.js`,
  `api/onlineClient.js`, `components/LoginScreen.jsx`,
  `components/GameHistory.jsx`, `components/OnlinePlay.jsx` (lobby/waiting/board),
  `hooks/useChessGame.js` (engine game + pre-move),
  `hooks/useOnlineGame.js` (poll loop, resume, optimistic drop + rollback)
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
6. Frontend tests: no jest-dom — use plain DOM assertions (`.disabled`, not
   `toBeDisabled()`; `.textContent`, not `toHaveTextContent()`); `@testing-library/user-event`
   is installed for realistic form/click simulation; act() gotchas in hook tests
   (assert after act, waitFor sees final state with instant fake engines).
7. `backend/pytest.ini` has `addopts = -q` — running `pytest -q` again suppresses
   the summary line (looks like missing output; exit code is the truth).
8. This machine: Windows, miniconda py3.14, Node 24, **no Docker CLI**, **no
   browser tooling**, Vercel CLI present but fine-grained tokens can't use
   `whoami`/project settings (use REST API with `?teamId=` instead).
9. **Measure engine strength in PRODUCTION, not just locally.** Vercel's
   serverless CPU runs ~4x slower than this laptop; budgets tuned locally made
   `hard` and `master` both abort at depth 4 in production (identical play
   behind 1650 vs 2000 Elo — the "difficulty not increasing" incident).
   Current budgets (strengths.py): 150/1000/2500/8000 ms → prod depths
   1/3/4/5, local 1/3/5/6-7. Proven: function timeout > 10 s (a 10002 ms
   search returned), so master's 8 s budget + cold start fits.
10. **Quiescence must value checkmate**: a mated position on the horizon used
    to score as a ~500 cp static eval, so easy NEVER saw a mate and every
    profile was a ply late on tactics. `_quiescence` now returns
    `-MATE_SCORE + ply` for no-evasion positions and never stand-pats while
    in check.
11. **`waitFor` hangs under `vi.useFakeTimers()`** — it polls a `setTimeout`
    that fake timers swallowed (test times out at 5s). With fake timers, flush
    with `await vi.advanceTimersByTimeAsync(ms)` inside `act()` (it awaits the
    timer callback's microtasks too) and assert synchronously afterwards.
12. **Multiplayer on serverless = short polling, not sockets.** Vercel Python
    functions are stateless; the online game lives in Turso and both clients
    poll `GET .../{id}` every 2.5s (paused on hidden tab). Moves are validated
    server-side by replaying the stored PGN (so threefold repetition works)
    and committed with `WHERE fen = <expected>` so two simultaneous writers
    can't both win the race (loser gets 409).

## Dev commands

```bash
cd backend  && python -m pytest          # 43 tests
cd frontend && npx vitest run            # 53 tests
cd frontend && npx eslint src            # lint
cd frontend && npm run build             # production bundle
cd backend  && uvicorn app.main:app --reload --port 8000
```

## Ideas queued

Multiplayer + leaderboard — DONE (2026-10-11). Next up per user: **NNUE
evaluator** (train a small net in numpy to replace/augment the hand-written
eval; needs self-play data + eval flag + tactics validation before flipping).
Other ideas: sound effects, mobile polish, Google login completion, move
annotations for the engine (why did it play that).
