"""Generate NNUE training data: engine self-play labeled by engine search.

Every position of every self-play game is labeled with the score the search
gives it (depth 3 + quiescence, centipawns from the side to move's view).
The same search both selects the played move and supplies its score, so each
position costs exactly one search. A little Gaussian noise on move selection
keeps the games (and therefore the positions) diverse while labels stay clean
(the pre-noise score of the chosen move).

Output: one JSONL shard per worker, one object per line:
    {"fen": "<fen>", "score": <int cp, side-to-move perspective>}

Usage (from backend/):
    python scripts/nnue_data.py --games 5000 --workers 11 --out data/nnue
"""

from __future__ import annotations

import argparse
import json
import os
import random
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import chess  # noqa: E402
from app.engine.search import MATE_THRESHOLD, Searcher  # noqa: E402

MAX_PLIES = 160
LABEL_CLAMP = 1500  # mate scores compress to +/- this

# The playing strength AND the labeler in one: depth 3 + quiescence.
TEACHER = {"max_depth": 3, "time_limit_ms": 400, "noise_cp": 14}
MAX_OPENING_PLIES = 6  # random dither before engine play starts


def play_game(seed: int, time_ms: int) -> list[dict]:
    rng = random.Random(seed)
    board = chess.Board()
    for _ in range(rng.randint(0, MAX_OPENING_PLIES)):
        moves = list(board.legal_moves)
        if not moves:
            return []
        board.push(rng.choice(moves))

    rows: list[dict] = []
    for _ply in range(MAX_PLIES):
        if board.is_game_over():
            break
        searcher = Searcher(
            board, seed=rng.randrange(10**9), time_limit_ms=time_ms, **{
                k: v for k, v in TEACHER.items() if k != "time_limit_ms"
            },
        )
        result = searcher.search()
        if result.move is None:
            break
        score = result.score
        if abs(score) >= MATE_THRESHOLD:
            score = LABEL_CLAMP if score > 0 else -LABEL_CLAMP
        rows.append({"fen": board.fen(), "score": int(score)})
        board.push(result.move)
    return rows


def worker(args: tuple[int, int, str, int, int]) -> tuple[str, int, int, float]:
    index, games, out_dir, time_ms, seed_base = args
    path = os.path.join(out_dir, f"shard-{index:03d}.jsonl")
    started = time.time()
    written = 0
    with open(path, "w", encoding="utf-8") as fh:
        for g in range(games):
            for row in play_game(seed=seed_base + index * 10**6 + g, time_ms=time_ms):
                fh.write(json.dumps(row) + "\n")
                written += 1
    return path, games, written, time.time() - started


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--games", type=int, default=5000, help="total self-play games")
    parser.add_argument("--workers", type=int, default=11, help="parallel processes")
    parser.add_argument("--out", default="data/nnue", help="output directory")
    parser.add_argument("--time-ms", type=int, default=400, help="teacher budget per move")
    parser.add_argument("--seed-base", type=int, default=0, help="shift all game seeds")
    args = parser.parse_args()

    os.makedirs(args.out, exist_ok=True)
    per_worker = max(1, args.games // args.workers)
    jobs = [(i, per_worker, args.out, args.time_ms, args.seed_base) for i in range(args.workers)]

    print(f"generating ~{per_worker * args.workers} games on {args.workers} workers...")
    started = time.time()
    total_rows = 0
    with __import__("multiprocessing").Pool(args.workers) as pool:
        for path, games, rows, elapsed in pool.imap_unordered(worker, jobs):
            total_rows += rows
            print(
                f"  {os.path.basename(path)}: {games} games, {rows} positions "
                f"({elapsed:.0f}s)",
                flush=True,
            )
    print(
        f"done: {total_rows} positions in {(time.time() - started) / 60:.1f} min -> {args.out}"
    )


if __name__ == "__main__":
    main()
