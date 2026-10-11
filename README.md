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

| Profile  | Max depth | Time budget | Noise  | Typical depth reached | Approx. Elo |
|----------|-----------|-------------|--------|----------------------|-------------|
| `easy`   | 1         | 150 ms      | 60 cp  | 1                    | ~750 (beginner) |
| `medium` | 3         | 700 ms      | 15 cp  | 2-3                  | ~1250 (casual club) |
| `hard`   | 5         | 1800 ms     | 0      | 4-5                  | ~1650 (solid club) |
| `master` | 7         | 3500 ms     | 0      | 4-6                  | ~2000 (expert) |

Depth is an **upper bound**: the search stops when the wall-clock budget runs
out and always returns the best move of the deepest *completed* depth, so a
time cut-off never returns a half-analysed move. Dense middlegame positions
settle at a lower depth than open ones, exactly like a real time-controlled game.

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
```

## Accounts & game history (Turso)

The game now has a login gate with three sign-in options — **email/password**,
**Google**, and **guest** — and every finished game (win, loss or draw) is
saved automatically to a **Turso** (libSQL/SQLite) database, with a
"My games" history panel under the board.

| Env var | Purpose | Required |
|---|---|---|
| `DATABASE_URL` | `libsql://<db>-<org>.turso.io` (prod) or `file:./chess.db` (local) | prod only |
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