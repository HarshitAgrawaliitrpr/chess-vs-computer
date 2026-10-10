# Chess vs. Computer (Harness Open Source CI/CD)

A web-based Player-vs-Computer chess game with a custom Minimax/Alpha-Beta
engine, wrapped in a Harness Open Source (Gitness) CI/CD pipeline.

| Layer     | Tech |
|-----------|------|
| Frontend  | React 18 + Vite, `react-chessboard` (board UI), `chess.js` (rules) |
| Backend   | Python FastAPI, custom engine: **negamax + alpha-beta pruning** |
| Engine    | Iterative deepening, transposition table, MVV-LVA/killer/history ordering, quiescence search, check extensions |
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
```

## Tests

```bash
cd backend  && pytest -v     # tactical FEN tests (mate-in-N), API tests
cd frontend && npm test       # engine client + game hook tests
```

`backend/tests/test_engine_tactics.py` feeds concrete FEN strings to the
engine and asserts it finds the forced mate (back-rank mate in one, two-rook
mate in two, promotion choice, time-limit compliance).

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