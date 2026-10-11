"""Validate a trained NNUE net against the hand-written evaluator.

Three checks, all on the same machine (relative comparisons are what matter):

1. tactics     - short mate-in-1 / free-piece positions both must solve
2. head-to-head - self-play at equal strength, net vs hand, alternating colors
3. speed       - depth/nodes reached at a fixed budget (incremental cost check)

Usage (from backend/):
    python scripts/nnue_validate.py --weights app/engine/weights/nnue-32-v1.json
"""

from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chess  # noqa: E402

from app.engine import nnue  # noqa: E402
from app.engine.search import MATE_THRESHOLD, Searcher  # noqa: E402

TACTICS = [
    # (fen, kind) - "mate": any mate; "win": any capture-winning >= 200 cp
    ("6k1/5ppp/8/8/8/8/5PPP/R5K1 w - - 0 1", "mate"),  # Ra8#
    ("r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5Q2/PPPP1PPP/RNB1K1NR w KQkq - 4 4", "mate"),  # Qxf7#
    ("7k/8/8/8/8/8/8/R1R3K1 w - - 0 1", "mate"),  # rook ladder
    ("4k3/8/8/3q4/8/2N5/4P3/4K3 w - - 0 1", "win"),  # Nxd5 free queen
    ("4k3/8/8/8/8/8/4P3/6K1 w - - 0 1", "quiet"),  # K+P only: no tactics, just must not crash
    ("2rq1rk1/pp1bppbp/2np1np1/8/3NP3/2N1BP2/PPPQ2PP/2KR3R w - - 0 12", "quiet"),  # dense middlegame
]

PROFILE = {"max_depth": 3, "time_limit_ms": 800, "noise_cp": 0}
LADDER_PROFILE = {"max_depth": 3, "time_limit_ms": 500, "noise_cp": 12}
LADDER_PLIES = 180


def run_tactics(net) -> int:
    passed = 0
    for fen, kind in TACTICS:
        nnue.set_active(net)
        board = chess.Board(fen)
        result = Searcher(board, seed=42, **PROFILE).search()
        nnue.set_active(None)
        if result.move is None:
            print(f"  FAIL {kind:6s} no move for {fen}")
            continue
        if kind == "mate":
            after = board.copy()
            after.push(result.move)
            ok = after.is_checkmate() or (
                abs(result.score) >= MATE_THRESHOLD and result.score > 0
            )
        elif kind == "win":
            ok = result.score >= 200
        else:
            ok = True  # quiet position: just must not crash / return a move
        print(f"  {'ok  ' if ok else 'FAIL'} {kind:6s} {board.san(result.move):8s} "
              f"score={result.score} {fen}")
        passed += ok
    return passed


def play_game(net_a, seed: int) -> tuple[str, int]:
    """net_a plays white when even seed, black when odd."""
    nnue.set_active(None)
    board = chess.Board()
    import random

    rng = random.Random(seed)
    for _ in range(rng.randint(0, 4)):  # short random opening
        board.push(rng.choice(list(board.legal_moves)))
    for _ply in range(LADDER_PLIES):
        if board.is_game_over():
            break
        active = net_a if (board.turn == chess.WHITE) == (seed % 2 == 0) else None
        nnue.set_active(active)
        move = Searcher(board, seed=rng.randrange(10**9), **LADDER_PROFILE).search().move
        nnue.set_active(None)
        if move is None:
            break
        board.push(move)
    if not board.is_game_over():
        return "unfinished", 0.0
    outcome = board.outcome(claim_draw=True)
    if outcome is None or outcome.winner is None:
        return "draw", 0.5
    net_is_white = seed % 2 == 0
    won = (outcome.winner == chess.WHITE) == net_is_white
    return ("win" if won else "loss"), 1.0 if won else 0.0


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--weights", default="app/engine/weights/nnue-32-v1.json")
    parser.add_argument("--games", type=int, default=20)
    args = parser.parse_args()

    net = nnue.Nnue.load(args.weights)
    print(f"net: hidden={net.hidden} meta={net.meta}\n")

    print("== tactics ==")
    score = run_tactics(net)
    print(f"tactics: {score}/{len(TACTICS)}\n")

    print(f"== head-to-head (net vs hand, {args.games} games, alternating colors) ==")
    points = 0.0
    played = 0
    for seed in range(args.games):
        result, p = play_game(net, seed)
        points += p
        if result != "unfinished":
            played += 1
        print(f"  game {seed:2d}: {result}  ({points}/{played or '-'})", flush=True)
    if played:
        print(f"score: {points}/{played} = {100 * points / played:.0f}%")

    print("\n== speed (fixed budget, same position) ==")
    board = chess.Board("r1bq1rk1/pp2ppbp/2np1np1/2p5/2P1P3/2NP1NP1/PP2QPBP/R1B1K2R w KQ - 2 9")
    for label, active in [("hand", None), ("nnue", net)]:
        nnue.set_active(active)
        r = Searcher(board, max_depth=6, time_limit_ms=5000).search()
        print(f"  {label:5s} depth={r.depth} nodes={r.nodes:8d} "
              f"nps={r.nodes / (r.time_ms / 1000):,.0f} move={board.san(r.move)}")
    nnue.set_active(None)


if __name__ == "__main__":
    main()
