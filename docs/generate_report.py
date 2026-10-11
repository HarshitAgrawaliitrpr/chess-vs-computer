"""Generate PROJECT_OVERVIEW.pdf - a complete, shareable report of the
chess-vs-computer project (features, architecture, API, database, deployment,
testing, security, and hard-won technical notes).

Usage:
    pip install fpdf2
    python docs/generate_report.py     # writes PROJECT_OVERVIEW.pdf at repo root

Text is intentionally ASCII (core PDF fonts are latin-1).
"""

from __future__ import annotations

import os
from typing import Sequence

from fpdf import FPDF
from fpdf.fonts import FontFace

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT = os.path.join(REPO_ROOT, "PROJECT_OVERVIEW.pdf")

GREEN = (129, 182, 76)  # chess.com-style accent
DARK = (34, 31, 26)
MUTED = (120, 116, 106)
LIGHT = (244, 246, 240)


class Report(FPDF):
    def header(self) -> None:
        if self.page_no() == 1:
            return
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 6, "Chess vs. Computer  -  Project Report", new_x="LMARGIN", new_y="NEXT")
        self.set_draw_color(*GREEN)
        self.set_line_width(0.4)
        self.line(self.l_margin, 14, self.w - self.r_margin, 14)
        self.ln(4)

    def footer(self) -> None:
        self.set_y(-14)
        self.set_font("Helvetica", "", 8)
        self.set_text_color(*MUTED)
        self.cell(0, 6, f"Page {self.page_no()} / {{nb}}", align="C")


pdf = Report()
pdf.set_auto_page_break(auto=True, margin=18)
pdf.set_margins(left=18, top=18, right=18)
pdf.alias_nb_pages()


def h1(text: str) -> None:
    pdf.ln(2)
    pdf.set_font("Helvetica", "B", 15)
    pdf.set_text_color(*GREEN)
    pdf.cell(0, 9, text, new_x="LMARGIN", new_y="NEXT")
    pdf.set_draw_color(*GREEN)
    pdf.set_line_width(0.3)
    y = pdf.get_y()
    pdf.line(pdf.l_margin, y, pdf.w - pdf.r_margin, y)
    pdf.ln(2.5)
    pdf.set_text_color(*DARK)


def h2(text: str) -> None:
    pdf.ln(1.5)
    pdf.set_font("Helvetica", "B", 11.5)
    pdf.set_text_color(*DARK)
    pdf.cell(0, 7, text, new_x="LMARGIN", new_y="NEXT")


def para(text: str) -> None:
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*DARK)
    pdf.multi_cell(0, 5.2, text, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(1)


def bullet(text: str) -> None:
    pdf.set_font("Helvetica", "", 10)
    pdf.set_text_color(*DARK)
    x = pdf.get_x()
    pdf.cell(5, 5.2, "-")
    pdf.multi_cell(0, 5.2, text, new_x="LMARGIN", new_y="NEXT")
    pdf.set_x(x)


def table(headers: Sequence[str], rows: Sequence[Sequence[str]], widths: Sequence[int]) -> None:
    pdf.set_font("Helvetica", "", 9)
    style = FontFace(emphasis="BOLD", color=GREEN, fill_color=LIGHT)
    with pdf.table(
        col_widths=tuple(widths),
        text_align="LEFT",
        headings_style=style,
        line_height=5.6,
        padding=1.6,
    ) as t:
        row = t.row()
        for cell in headers:
            row.cell(str(cell))
        for cells in rows:
            row = t.row()
            for cell in cells:
                row.cell(str(cell))
    pdf.ln(2)


# ---------------------------------------------------------------------------
# Cover
# ---------------------------------------------------------------------------
pdf.add_page()
pdf.ln(30)
pdf.set_font("Helvetica", "B", 30)
pdf.set_text_color(*DARK)
pdf.multi_cell(0, 13, "Chess vs. Computer", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.set_font("Helvetica", "", 14)
pdf.set_text_color(*GREEN)
pdf.multi_cell(0, 8, "Full-stack PvE chess with a custom engine,\ncloud accounts and online rankings", align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(10)
pdf.set_font("Helvetica", "", 11)
pdf.set_text_color(*DARK)
pdf.multi_cell(0, 6.5, (
    "Live site:  https://chess-vs-computer-five.vercel.app\n"
    "Repository: https://github.com/HarshitAgrawaliitrpr/chess-vs-computer\n\n"
    "Created by Harshit Agrawal with MiMo\n"
    "Report date: 11 October 2026"
), align="C", new_x="LMARGIN", new_y="NEXT")
pdf.ln(14)
pdf.set_font("Helvetica", "I", 9.5)
pdf.set_text_color(*MUTED)
pdf.multi_cell(0, 5.5, (
    "React + Vite frontend, FastAPI backend, minimax/alpha-beta engine,\n"
    "Turso (libSQL) database, JWT auth, GitHub + Vercel auto-deploy,\n"
    "Harness Open Source CI/CD pipeline."
), align="C", new_x="LMARGIN", new_y="NEXT")

# ---------------------------------------------------------------------------
# 1. Overview
# ---------------------------------------------------------------------------
pdf.add_page()
h1("1. Overview")
para(
    "A complete browser chess game where a human plays against a custom-written "
    "minimax engine with adjustable strength. It ships with accounts (email, Google "
    "and guest), automatic game saving, a personal history panel and a public "
    "leaderboard - all running as one Vercel project on a single domain."
)
table(
    ["Layer", "Technology"],
    [
        ["Frontend", "React 18 + Vite, react-chessboard (board UI), chess.js (rules)"],
        ["Backend", "Python FastAPI, Pydantic models, per-call libsql-client DB layer"],
        ["Engine", "Negamax + alpha-beta: iterative deepening, transposition table,"],
        ["", "MVV-LVA/killer/history ordering, quiescence search, check extensions"],
        ["Database", "Turso (libSQL/SQLite) - users, games; file: SQLite for local dev"],
        ["Auth", "bcrypt passwords, HS256 JWT sessions, Google ID-token verification"],
        ["CI/CD", "Harness Open Source pipeline (build -> test -> dockerize -> deploy)"],
        ["Hosting", "Vercel serverless (FastAPI function + CDN-served React bundle)"],
    ],
    [24, 148],
)

h2("What makes it complete")
for line in [
    "Full move legality (castling, en passant, promotion, 50-move, threefold repetition).",
    "Pre-move queue: drag a move while the engine thinks; it auto-plays when your turn arrives.",
    "Game-over dialog with retry, plus win/loss/draw messaging.",
    "Three sign-in options; guests can play and still keep history.",
    "Every finished game auto-saves; leaderboard ranks players by chess points.",
    "65 automated tests (34 backend + 39 frontend), lint and production build all green.",
]:
    bullet(line)

# ---------------------------------------------------------------------------
# 2. Engine
# ---------------------------------------------------------------------------
h1("2. The Engine and Difficulty Ladder")
para(
    "The engine is a hand-written negamax with alpha-beta pruning. Depth is an upper "
    "bound: the search stops at a wall-clock budget and always returns the best move "
    "of the deepest COMPLETED depth, so a time cut-off never returns a half-analysed "
    "move. Easy levels add positional noise so weaker opponents feel human."
)
table(
    ["Profile", "Max depth", "Time budget", "Noise", "Approx. Elo"],
    [
        ["easy", "1", "150 ms", "60 cp", "~750 (beginner)"],
        ["medium", "3", "700 ms", "15 cp", "~1250 (casual club)"],
        ["hard", "5", "1800 ms", "0", "~1650 (solid club)"],
        ["master", "7", "3500 ms", "0", "~2000 (expert)"],
    ],
    [26, 24, 30, 22, 70],
)
para(
    "A self-play guard (scripts/selfplay.py) pits easy vs master with production time "
    "budgets and fails CI if the weaker profile ever wins - keeping the ladder monotonic."
)

# ---------------------------------------------------------------------------
# 3. Architecture
# ---------------------------------------------------------------------------
pdf.add_page()
h1("3. Architecture")
h2("Single-domain deployment")
para(
    "One Vercel project serves both apps: the FastAPI function handles /api/* and the "
    "same function serves the built React bundle for every other path. In development "
    "Vite proxies /api to uvicorn on localhost:8000."
)
table(
    ["Request", "Route"],
    [
        ["GET /", "CDN -> built React SPA (index.html)"],
        ["POST /api/engine/move", "FastAPI: minimax search (<= 3.5 s budget)"],
        ["POST /api/auth/* , /api/games, /api/leaderboard", "FastAPI + Turso (libSQL over HTTP)"],
    ],
    [72, 100],
)
h2("Key files")
table(
    ["Path", "Role"],
    [
        ["backend/app/main.py", "Engine routes, router wiring, static mount"],
        ["backend/app/engine/", "search.py (negamax), strengths.py (profiles)"],
        ["backend/app/db.py", "libsql-client layer; per-call open+close; URL normalisation"],
        ["backend/app/store.py", "Schema (idempotent ensure_schema) + repository queries"],
        ["backend/app/security.py", "bcrypt, JWT, Google verification, current-user dependency"],
        ["backend/app/routes_auth.py", "config/register/login/google/guest/me"],
        ["backend/app/routes_games.py", "save + list finished games"],
        ["backend/app/routes_leaderboard.py", "public ranking endpoint"],
        ["frontend/src/hooks/useChessGame.js", "All game state: moves, engine calls, pre-move queue"],
        ["frontend/src/auth/AuthContext.jsx", "Session restore + auth actions"],
        ["frontend/src/components/", "ChessGame, LoginScreen, GameHistory, Leaderboard, overlays"],
        [".harness/pipeline.yaml", "CI/CD: build -> test -> dockerize -> deploy"],
    ],
    [64, 108],
)

# ---------------------------------------------------------------------------
# 4. Accounts and data
# ---------------------------------------------------------------------------
h1("4. Accounts, Database and Leaderboard")
para(
    "Three sign-in flows produce the same {token, user} JWT session: email+password "
    "(bcrypt), Google Identity Services ID token (RS256 + audience check server-side), "
    "and one-click guest (UUID user, name Guest-XXXX). The token lives in "
    "localStorage and is sent as a Bearer header."
)
h2("Database tables (Turso = SQLite)")
table(
    ["users", "games"],
    [
        ["id TEXT PK", "id TEXT PK, user_id -> users.id"],
        ["email TEXT UNIQUE (null for guests)", "pgn TEXT, result (win/loss/draw)"],
        ["name, provider (email/google/guest)", "result_detail, player_color (w/b)"],
        ["password_hash (bcrypt), google_sub", "difficulty, moves_count, created_at"],
        ["created_at", "idx: (user_id, created_at DESC)"],
    ],
    [86, 86],
)
h2("Leaderboard rules")
for line in [
    "Points = wins + 0.5 * draws (classic chess scoring); ranking by points,",
    "ties broken on wins, then games played, then name - all in one SQL aggregate.",
    "Optional ?difficulty=easy|medium|hard|master filter; ?limit=1..50 (default 10).",
    "Top 3 get medals in the UI; the panel refreshes the moment a game is saved.",
]:
    bullet(line)

# ---------------------------------------------------------------------------
# 5. API reference
# ---------------------------------------------------------------------------
pdf.add_page()
h1("5. API Reference")
table(
    ["Method + path", "Auth", "Purpose"],
    [
        ["GET /api/health", "-", "Liveness probe (CI/CD)"],
        ["GET /api/difficulties", "-", "Difficulty profile metadata"],
        ["POST /api/engine/move", "-", "Best move for the side to move in a FEN"],
        ["GET /api/auth/config", "-", "Is Google sign-in configured? (+ client id)"],
        ["POST /api/auth/register", "-", "Create email account -> token (201)"],
        ["POST /api/auth/login", "-", "Email sign-in -> token"],
        ["POST /api/auth/google", "-", "Verify GIS ID token -> token"],
        ["POST /api/auth/guest", "-", "Anonymous account -> token (201)"],
        ["GET /api/auth/me", "JWT", "Current user profile"],
        ["POST /api/games", "JWT", "Store a finished game (201)"],
        ["GET /api/games", "JWT", "Own games, newest first (last 20)"],
        ["GET /api/leaderboard", "-", "Top players by points (difficulty filter)"],
    ],
    [58, 14, 100],
)
para(
    "Errors: 401 (bad/missing token), 409 (duplicate email), 422 (validation), "
    "503 with a helpful JSON detail when the database is unconfigured - engine "
    "endpoints never depend on the database and keep working regardless."
)

# ---------------------------------------------------------------------------
# 6. Deployment
# ---------------------------------------------------------------------------
h1("6. Deployment and Infrastructure")
table(
    ["Piece", "Detail"],
    [
        ["Repository", "github.com/HarshitAgrawaliitrpr/chess-vs-computer (public, main)"],
        ["Hosting", "Vercel: root main.py re-exports the FastAPI app; vercel.json builds"],
        ["", "the frontend (npm ci && npm run build) before each deployment"],
        ["Auto-deploy", "Every push to main -> production in ~30 s (webhook, verified)"],
        ["Database", "Turso, ap-south-1 region; schema created idempotently on demand"],
        ["Env vars", "DATABASE_URL, DATABASE_AUTH_TOKEN, SECRET_KEY (Production+Preview)"],
        ["", "optional GOOGLE_CLIENT_ID enables the Google button (no code change)"],
        ["CI/CD", "Harness pipeline: build -> test -> dockerize -> deploy (main only)"],
    ],
    [34, 138],
)
para(
    "Local development needs zero configuration: without env vars the backend falls "
    "back to a file:./chess.db SQLite database and a generated .jwt-secret file."
)

# ---------------------------------------------------------------------------
# 7. Testing
# ---------------------------------------------------------------------------
h1("7. Testing and Quality")
table(
    ["Suite", "Count", "Covers"],
    [
        ["backend pytest", "34", "Engine tactics (mate-in-N), API, auth, leaderboard"],
        ["frontend vitest", "39", "Engine client, game hook (pre-moves), login, leaderboard"],
        ["lint", "clean", "eslint (react + react-hooks) on all frontend source"],
        ["build", "clean", "Production Vite bundle (~292 KB / 92 KB gzip)"],
        ["engine guard", "selfplay", "Easy never beats master (monotonicity check)"],
    ],
    [34, 20, 118],
)
para(
    "Tests run on every push via the Harness pipeline and use an isolated temp-file "
    "database per session (tests/conftest.py), so they never touch real data."
)

# ---------------------------------------------------------------------------
# 8. Security
# ---------------------------------------------------------------------------
h1("8. Security Notes")
for line in [
    "Passwords: bcrypt with default cost; login answers a generic 401 either way.",
    "Sessions: stateless HS256 JWT (30 days) with exp; secret from SECRET_KEY env.",
    "Google: ID tokens verified server-side (JWKS, RS256, audience) - no client secret.",
    "Sensitive values (DB token, JWT secret) live only in Vercel encrypted env vars;",
    "temporary access tokens used during setup were revoked and verified dead.",
    "Leaderboard exposes display names and stats only - never emails or tokens.",
    "CORS is open (*) because the SPA and API share one origin in production.",
]:
    bullet(line)

# ---------------------------------------------------------------------------
# 9. Hard-won notes
# ---------------------------------------------------------------------------
pdf.add_page()
h1("9. Hard-won Technical Notes")
para("Details that cost real debugging time - recorded so they are never re-learned:")
for line in [
    "Python 3.14 has no 'libsql' wheel (Rust build fails) -> pure-Python libsql-client.",
    "libsql:// URLs use WebSockets, which newer Turso DBs reject (HTTP 400). db.py",
    "normalises libsql:// to https:// (HRANA over HTTP) so both URL styles work.",
    "libsql-client sync clients hang interpreter exit if not close()d - the DB layer",
    "opens and closes a short-lived client per call (otherwise pytest never exits).",
    "Vercel env vars are SCOPED: a variable saved with only 'Preview' is invisible in",
    "production (caused one production outage); changes need a redeploy, not a save.",
    "react-chessboard v4 highlights prop is customSquareStyles; returning false from",
    "onPieceDrop keeps pieces in place - which is exactly what pre-moves need.",
    "Pre-move design: single-slot queue + engine loop that answers the human move,",
    "applies the queued pre-move, then answers again; illegal pre-moves are discarded.",
    "Test ergonomics: no jest-dom (plain DOM assertions), user-event for realistic",
    "clicks/submits, and assertions must respect React act() batching.",
]:
    bullet(line)

# ---------------------------------------------------------------------------
# 10. Timeline and roadmap
# ---------------------------------------------------------------------------
h1("10. Timeline and Roadmap")
h2("Shipped, in order")
for line in [
    "Game + engine + tests + Harness CI/CD pipeline + Docker packaging.",
    "Creator credit footer, GitHub repository, Vercel deployment with auto-deploy.",
    "Game-over dialog (win/loss/draw + retry) and the pre-move system.",
    "Accounts: Turso database, email/Google/guest auth, JWT, auto-saved history.",
    "Production hardening: libsql URL fix, env-var scoping, whitespace tolerance.",
    "Leaderboard with points, difficulty filter and top-3 medals.",
]:
    bullet(line)
h2("Ideas for next")
for line in [
    "Complete Google sign-in (create OAuth client ID, set GOOGLE_CLIENT_ID).",
    "Sound effects and mobile polish; per-game move analysis from the engine.",
    "Seasonal leaderboards, rating changes per game (Elo from the games table).",
]:
    bullet(line)

pdf.ln(4)
pdf.set_font("Helvetica", "I", 9)
pdf.set_text_color(*MUTED)
pdf.multi_cell(0, 5, "Generated by docs/generate_report.py - rebuild after any milestone.", align="C", new_x="LMARGIN", new_y="NEXT")

pdf.output(OUTPUT)
size_kb = round(os.path.getsize(OUTPUT) / 1024, 1)
print(f"Wrote {OUTPUT}")
print(f"Pages: {pdf.page_no()}, size: {size_kb} KB")
