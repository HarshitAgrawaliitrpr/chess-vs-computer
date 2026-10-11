# Chess vs. Computer (Harness Open Source CI/CD)

A web-based Player-vs-Computer chess game with a custom Minimax/Alpha-Beta
engine, wrapped in a Harness Open Source (Gitness) CI/CD pipeline.

| Layer     | Tech |
|-----------|------|
| Frontend  | React 18 + Vite, `react-chessboard` (board UI), `chess.js` (rules) |
| Backend   | Python FastAPI, custom engine: **negamax + alpha-beta pruning** |
| Engine    | Iterative deepening, transposition table, MVV-LVA/killer/history ordering, quiescence search, check extensions |
| Accounts  | **Turso** (libSQL) via `libsql-client` — email/password, Google, guest; JWT sessions (bcrypt + PyJWT) |
| CI/CD     | `.harness/pipeline.yaml` — Build -> Test -> Dockerize -> Deploy |

## Difficulty ladder

| Profile  | Max depth | Time budget | Noise  | Depth in production* | Approx. Elo |
|----------|-----------|-------------|--------|----------------------|-------------|
| `easy`   | 1         | 150 ms      | 60 cp  | 1                    | ~750 (beginner) |
| `medium` | 3         | 1000 ms     | 15 cp  | 3                    | ~1250 (casual club) |
| `hard`   | 5         | 2500 ms     | 0      | 4                    | ~1650 (solid club) |
| `master` | 7         | 8000 ms     | 0      | 5                    | ~2000 (expert) |

Depth is an **upper bound**: the search stops when the wall-clock budget runs
out and always returns the best move of the deepest *completed* depth, so a
time cut-off never returns a half-analysed move. Dense middlegame positions
settle at a lower depth than open ones, exactly like a real time-controlled game.

\* measured on Vercel's serverless CPU (≈4x slower than a dev laptop) in dense
middlegames; on a fast local machine the same budgets reach the full caps
(hard = 5, master = 6-7). Budgets are tuned so the ladder stays **strictly
increasing where users actually play** — an earlier calibration had `hard`
and `master` both capped at depth 4 in production, playing identical moves
behind different Elo labels.

## NNUE evaluator (trained 2026-10-11, opt-in)

The engine can score positions with a small neural net instead of the
hand-written evaluation:

- **Architecture**: 768 → 32 (ReLU) → 1, side-to-move relative
  (2 perspectives × 6 piece types × 64 squares, kings excluded; the
  "black view" flips ranks). Search keeps **incremental accumulators**
  (copy-on-write stack; ~5 µs/push, ~0.8 µs forward vs ~11 µs for the
  hand eval), with a scratch rebuild fallback covered by a property test.
- **Training data**: 1,496 self-play games by the engine itself
  (depth 3 + quiescence teacher, 400 ms and 300 ms budgets, ±14 cp
  selection noise; labels are the clean pre-noise score of the chosen
  move) → 177,893 unique positions, mirror-augmented to 355,786 samples.
- **Training**: 20 epochs, Huber(δ=1) on cp/400, Adam 3e-3 with linear
  decay (`backend/scripts/nnue_train.py`). Final: val MAE 172 cp,
  Pearson r = 0.925 vs teacher scores.
- **Validation** (`backend/scripts/nnue_validate.py`): tactics **6/6**,
  head-to-head at equal depth vs the hand evaluator **9 wins – 5 losses
  (64 %)** with 6 games unfinished, and **97 % nps parity**. Startpos
  evaluates at −6 cp (no material bias).
- **Enable**: set `EVAL_BACKEND=nnue` (and optionally `NNUE_WEIGHTS` to a
  different JSON) — production ships `hand` by default; `/api/health`
  reports which evaluator is active. Retrain anytime:
  `python scripts/nnue_data.py … && python scripts/nnue_train.py …`
  (the weights JSON stays committed; regenerate then commit).

## Run locally

### Backend

```bash
cd backend
pip install -r requirements-dev.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm ci
npm run dev        # http://localhost:5173 (proxies /api to :8000)
```

### Docker

```bash
docker compose up --build   # frontend on :3000, backend on :8000
```

## API

```
GET  /api/health         -> {status: "ok"}
GET  /api/difficulties   -> profile metadata (depth, time, elo)
POST /api/engine/move    -> {fen, difficulty, depth?, time_limit_ms?}
     -> {move: {from,to,san,uci,promotion}, fen, score, score_type,
         mate_in, depth, nodes, time_ms, pv[], elo_estimate}

GET  /api/auth/config    -> {google_enabled, google_client_id}
POST /api/auth/register  -> {email, name, password}          -> {token, user} (201)
POST /api/auth/login     -> {email, password}                -> {token, user}
POST /api/auth/google    -> {credential}  (GIS ID token)     -> {token, user}
POST /api/auth/guest     -> {name?}                          -> {token, user} (201)
GET  /api/auth/me        -> current user (Bearer token)
POST /api/games          -> {pgn, result, player_color, ...} -> saved game (201)
GET  /api/games          -> the signed-in user's last 20 games
GET  /api/leaderboard    -> top players by points (win=1, draw=0.5); ?difficulty=&limit=

POST /api/online/games           create a match -> {code, ...} (you are White, 201)
POST /api/online/games/join      {code} -> join as Black (code is case-insensitive)
GET  /api/online/games/{id}      poll full state (participants only; strangers get 404)
POST /api/online/games/{id}/move {from, to, promotion?} -> validated by python-chess
POST /api/online/games/{id}/resign   lose on purpose (opponent wins)
POST /api/online/games/{id}/cancel   abort a waiting game (creator only)
```

## Online multiplayer (human vs human)

The "Play Online" tab lets two signed-in players play each other in real
time — no refresh needed:

* **Invite codes** — create a game to get a 6-character code (or a shareable
  `/?join=CODE` link that auto-joins), your friend enters it and you both land
  on the same board. Creator plays White.
* **Server-authoritative** — every move is validated server-side with
  python-chess (illegal moves are rejected with 422; stale writes lose a race
  with 409), so a tampered client cannot push an impossible position.
* **Short polling** — the frontend polls the game every 2.5s (paused while the
  tab is hidden) because Vercel's Python functions are stateless: no sockets,
  the game simply lives in Turso's `online_games` table.
* **Results count everywhere** — finished online games are written for *both*
  players into the history panel and the leaderboard (filter "online").
* **Resume** — your active game id is stored locally, so a refresh drops you
  back into the match. Auto-queen keeps move entry fast; Resign ends it early.

## Accounts & game history (Turso)

The game now has a login gate with three sign-in options — **email/password**,
**Google**, and **guest** — and every finished game (win, loss or draw) is
saved automatically to a **Turso** (libSQL/SQLite) database, with a
"My games" history panel under the board.

| Env var | Purpose | Required |
|---|---|---|
| `DATABASE_URL` | `libsql://<db>-<org>.turso.io` (prod) or `file:./chess.db` (local) — the `libsql://` form is auto-normalised to HRANA-over-HTTP, so both URL styles work | prod only |
| `DATABASE_AUTH_TOKEN` | Turso API token | prod only |
| `SECRET_KEY` | JWT signing secret (≥ 32 random chars) | prod (local generates `.jwt-secret`) |
| `GOOGLE_CLIENT_ID` | enables the Google button | optional |

* **Local dev needs nothing**: without config the backend falls back to
  `file:./chess.db` (gitignored) and a generated `.jwt-secret` file.
* **Engine endpoints never touch the database** — if the DB is unconfigured
  the chess game keeps working; only `/api/auth/*` and `/api/games` return 503.

### 1. Create the Turso database

```bash
turso db create chess-vs-computer
turso db show chess-vs-computer                 # -> URL for DATABASE_URL
turso db tokens create chess-vs-computer        # -> token for DATABASE_AUTH_TOKEN
```

`backend/scripts/turso_smoke.py` verifies the whole auth + games flow against
the live database and removes every row it created:

```bash
cd backend
$env:DATABASE_URL = "libsql://....turso.io"; $env:DATABASE_AUTH_TOKEN = "..."
python scripts/turso_smoke.py
```

To **see the actual data** (registered users with their emails, game history,
online matches) run the read-only viewer — Vercel masks secret env values by
design, so the owner views the database locally instead of through the
dashboard (emails are stored in plain text; only passwords are bcrypt-hashed):

```bash
cd backend
$env:DATABASE_URL = "https://....turso.io"; $env:DATABASE_AUTH_TOKEN = "..."
python scripts/view_db.py        # no env vars = local ./chess.db
```

### 2. Set the Vercel environment variables

Dashboard → your project → **Settings → Environment Variables**, add the four
variables above (Production + Preview), then **Redeploy** (env vars only apply
to new deployments — or just push again).

### 3. (Optional) Google sign-in

1. Google Cloud Console → **APIs & Services → Credentials → Create
   credentials → OAuth client ID → Web application**
2. Authorized origin: `https://chess-vs-computer-five.vercel.app`
   (plus `http://localhost:5173` for local testing)
3. Copy the client ID into the `GOOGLE_CLIENT_ID` env var and redeploy.
   Until then the login screen shows a note and the Google button stays hidden.

The Google button uses Identity Services (ID-token, `RS256` + audience check
server-side) — no client secret is ever needed.

## Tests

```bash
cd backend  && pytest -v     # tactical FEN tests (mate-in-N), API + auth tests
cd frontend && npm test       # engine client + game hook + login screen tests
```

`backend/tests/test_engine_tactics.py` feeds concrete FEN strings to the
engine and asserts it finds the forced mate (back-rank mate in one, two-rook
mate in two, promotion choice, time-limit compliance).
`backend/tests/test_auth_api.py` covers register/login/guest/Google-config,
JWT guards, game save/list and their validation errors (each test run gets an
isolated temp-file database via `tests/conftest.py`).

### Strength check (self-play)

```bash
cd backend && python scripts/selfplay.py 40   # easy vs master, both colours
```

Plays the two extreme profiles against each other with the production time
budgets and fails (exit 1) if the weaker profile ever beats the stronger one
— a monotonicity guard for the difficulty ladder.

Last run (40-ply cap, both colours): **master won 2/2** —
`master` averaged depth 5.6–6.1 at ~2.8 s/move, `easy` stayed at depth 1 in
single-digit milliseconds.

## CI/CD

`.harness/pipeline.yaml` runs on every push (default trigger):

1. **build** — `pip install` + `npm ci` + lint + production bundle
2. **test** — backend pytest (tactics) + frontend vitest
3. **dockerize** — Docker-in-Docker builds `chess-backend` and
   `chess-frontend`; on pushes to `main` the images are pushed to a registry
4. **deploy** — simulated cloud deployment, gated to pushes to `main`

Enable real registry pushes / webhooks by adding the `docker_registry` and
`deploy_webhook` secrets in *Pipeline Settings > Secrets* and following the
comments inside the pipeline file.

> Stages do not share a filesystem in Harness Open Source, so each stage
> installs its own dependencies from a fresh checkout.

## Deploy to Vercel (full website, one project)

Live site: **https://chess-vs-computer-five.vercel.app**

The repo is set up so a single Vercel project serves **both** the React
frontend and the FastAPI engine API on one domain:

| File | Role |
|---|---|
| `main.py` (root) | Vercel entrypoint — re-exports the FastAPI `app` |
| `requirements.txt` (root) | serverless runtime deps (`fastapi`, `python-chess`, `pydantic`, `libsql-client`, `bcrypt`, `PyJWT`) |
| `vercel.json` | `buildCommand` runs `npm ci && npm run build` in `frontend/` |
| `backend/app/main.py` | `app.frontend("/", ...)` serves `frontend/dist` — API routes take priority automatically |

Request flow on Vercel:

```
GET  /                -> CDN (built React app)
POST /api/engine/move -> Python function (minimax search, <= 3.5s per difficulty)
```

Measured on the live deployment: `easy` returns in ~0.5s wall including cold
start; `master` runs its full 3.5s search budget (depth 5, ~61k nodes) and
still finishes comfortably inside the default function timeout.

Deploy from your machine:

```bash
npm install -g vercel
vercel login                 # or export VERCEL_TOKEN=...
vercel deploy --yes --prod
```

Auto-deploy is connected: every push to `main` triggers a production build
on Vercel (verified — push to READY in ~30s, no credentials needed beyond
the repository's webhook).

> Created by **Harshit Agrawal with MiMo** — the credit line is rendered in the
> app footer.