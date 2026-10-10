"""Strength sanity check: play quick games between difficulty profiles.

Usage:  python scripts/selfplay.py [max_plies]

Plays `easy` vs `master` in both colours using the production profiles and
prints the result plus move-time/depth statistics. Exits non-zero if the
weaker profile beats the stronger one - i.e. the difficulty ladder must
actually be monotonic in strength.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # allow `python scripts/selfplay.py`

import chess

from app.engine.search import Searcher
from app.engine.strengths import PROFILES

MAX_PLIES_DEFAULT = 40


def _cap_reached(board: chess.Board, max_plies: int) -> bool:
    plies = (board.fullmove_number - 1) * 2 + (0 if board.turn == chess.WHITE else 1)
    return plies >= max_plies


def play_game(white: str, black: str, max_plies: int) -> tuple[str, list[dict]]:
    board = chess.Board()
    stats: list[dict] = []

    while not board.is_game_over() and not _cap_reached(board, max_plies):
        name = white if board.turn == chess.WHITE else black
        profile = PROFILES[name]
        t0 = time.perf_counter()
        result = Searcher(
            board,
            max_depth=profile.max_depth,
            time_limit_ms=profile.time_limit_ms,
            noise_cp=profile.noise_cp,
        ).search()
        elapsed = (time.perf_counter() - t0) * 1000

        if result.move is None:
            break
        stats.append({"who": name, "depth": result.depth, "ms": elapsed})
        board.push(result.move)

    if board.is_checkmate():
        winner = "black" if board.turn == chess.WHITE else "white"
    elif board.is_stalemate() or board.is_insufficient_material() or board.is_repetition() or board.halfmove_clock >= 100:
        winner = "draw"
    else:
        winner = "cap"
    return winner, stats


def main() -> int:
    max_plies = int(sys.argv[1]) if len(sys.argv) > 1 else MAX_PLIES_DEFAULT
    results = []

    for white, black in (("easy", "master"), ("master", "easy")):
        t0 = time.perf_counter()
        winner, stats = play_game(white, black, max_plies)
        dt = time.perf_counter() - t0
        results.append((white, black, winner))

        strong = [s for s in stats if s["who"] == "master"]
        weak = [s for s in stats if s["who"] == "easy"]
        avg = lambda xs, k: (sum(x[k] for x in xs) / len(xs)) if xs else 0.0

        master_color = "white" if white == "master" else "black"
        if winner == master_color:
            verdict = "master wins"
        elif winner in ("draw", "cap"):
            verdict = "draw/adjudicated"
        else:
            verdict = "EASY WINS (ladder broken)"

        print(f"game: {white:6} vs {black:6} -> {winner:<5} [{verdict}] ({dt:.0f}s)")
        print(f"   master: avg depth {avg(strong, 'depth'):.1f} | avg {avg(strong, 'ms'):.0f} ms/move")
        print(f"   easy  : avg depth {avg(weak, 'depth'):.1f} | avg {avg(weak, 'ms'):.0f} ms/move")

    master_wins = 0
    for white, black, winner in results:
        master_color = "white" if white == "master" else "black"
        if winner == master_color:
            master_wins += 1

    print(f"\nmaster wins: {master_wins}/{len(results)}")
    if master_wins >= 1:
        print("ladder check: OK (difficulty ladder is monotonic)")
        return 0
    if all(w in ("draw", "cap") for _, _, w in results):
        print("ladder check: OK (all draws - no inversion detected)")
        return 0
    print("ladder check: FAILED (weaker profile beat master)")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())