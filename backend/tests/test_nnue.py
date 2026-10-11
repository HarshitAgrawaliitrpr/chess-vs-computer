"""NNUE core tests: feature correctness, incremental updates, persistence.

No trained weights are required - tests build synthetic nets with known
behaviour (a material-only net) and random-but-deterministic nets for the
incremental-update property test.
"""

from __future__ import annotations

import math
import random

import chess
import pytest

from app.engine import nnue
from app.engine.nnue import Nnue

PIECE_VALUES = {chess.PAWN: 100, chess.KNIGHT: 320, chess.BISHOP: 330, chess.ROOK: 500, chess.QUEEN: 900}


def _material_net() -> Nnue:
    """hidden=2 net whose output equals (white material - black material).

    Two neurons implement the identity through ReLU: relu(x) - relu(-x) = x.
    Own-group rows carry +value, enemy-group rows -value, so each accumulator
    already holds the signed material difference from its perspective.
    """
    w1 = [[0.0, 0.0] for _ in range(768)]
    for pt, value in PIECE_VALUES.items():
        for sq in range(64):
            w1[(pt - 1) * 64 + sq] = [float(value), float(-value)]  # own group
            w1[(pt - 1 + 6) * 64 + sq] = [-float(value), float(value)]  # enemy group
    return Nnue(
        w1=[tuple(row) for row in w1],
        b1=(0.0, 0.0),
        w2=(1.0, -1.0),
        b2=0.0,
        hidden=2,
    )


def _random_net(seed: int = 7) -> Nnue:
    rng = random.Random(seed)
    w1 = [tuple(rng.gauss(0.0, 0.05) for _ in range(8)) for _ in range(768)]
    b1 = tuple(rng.gauss(0.0, 0.1) for _ in range(8))
    w2 = tuple(rng.gauss(0.0, 1.0) for _ in range(8))
    return Nnue(w1=w1, b1=b1, w2=w2, b2=0.3, hidden=8)


@pytest.fixture(autouse=True)
def _no_active_net():
    nnue.set_active(None)
    yield
    nnue.set_active(None)


# --------------------------------------------------------------------------- #
# semantics
# --------------------------------------------------------------------------- #
def test_material_net_scores_material_difference() -> None:
    net = _material_net()
    board = chess.Board()
    assert net.evaluate_board(board) == 0

    board.push_uci("e2e4")
    board.push_uci("d7d5")
    board.push_uci("e4d5")  # white is up a pawn; BLACK to move
    # evaluate_board is side-to-move perspective (negamax convention)
    assert net.evaluate_board(board) == -100
    # ...and +100 from white's side of the same position
    assert net.evaluate(net.initial(board), chess.WHITE) == 100
    assert net.evaluate(net.initial(board), chess.BLACK) == -100


def test_queen_up_scores_about_900() -> None:
    net = _material_net()
    board = chess.Board("4k3/8/8/8/8/8/4Q3/4K3 w - - 0 1")
    assert net.evaluate_board(board) == 900


# --------------------------------------------------------------------------- #
# incremental == from scratch (the whole correctness bet)
# --------------------------------------------------------------------------- #
def _walk_random_games(net: Nnue, games: int = 12, max_plies: int = 90, seed: int = 11) -> int:
    rng = random.Random(seed)
    checked = 0
    for _ in range(games):
        board = chess.Board()
        acc = net.initial(board)
        for _ply in range(max_plies):
            if board.is_game_over():
                break
            move = rng.choice(list(board.legal_moves))
            acc = net.push(board, move, acc)
            board.push(move)
            checked += 1
            got = net.forward(acc, board.turn)
            want = net.forward(net.initial(board), board.turn)
            assert math.isclose(got, want, abs_tol=1e-6), (
                f"incremental {got} != scratch {want} at FEN {board.fen()}"
            )
    return checked


def test_incremental_matches_scratch_on_random_games() -> None:
    net = _random_net()
    checked = _walk_random_games(net)
    assert checked > 200  # the property was actually exercised


def test_special_moves_incremental_matches_scratch() -> None:
    net = _random_net(seed=3)
    sequences = [
        # white short castling (after clearing the way)
        ["e2e4", "e7e5", "g1f3", "b8c6", "f1c4", "f8c5", "e1g1"],
        # black long castling (clearing b8/c8/d8 first; black moves on odd indexes)
        ["b1c3", "b8c6", "d2d4", "d7d5", "c1f4", "c8f5", "d1d2", "d8d7", "a2a3", "e8c8"],
        # en passant both ways
        ["e2e4", "a7a6", "e4e5", "d7d5", "e5d6"],
        # promotion (under-promotion capture on the corner)
        ["h2h4", "g7g5", "h4g5", "h7h6", "g5g6", "h6h5", "g6g7", "h5h4", "g7h8n"],
        # capture a rook in the corner
        ["a2a4", "h7h5", "a4a5", "h5h4", "a5a6", "h4h3", "a6b7", "h3g2", "b7a8q"],
    ]
    for line in sequences:
        board = chess.Board()
        acc = net.initial(board)
        for uci in line:
            move = chess.Move.from_uci(uci)
            assert move in board.legal_moves, f"{uci} illegal in {board.fen()}"
            acc = net.push(board, move, acc)
            board.push(move)
            assert math.isclose(
                net.evaluate(acc, board.turn), net.evaluate(net.initial(board), board.turn), abs_tol=1e-6
            ), f"{uci}: incremental drift at {board.fen()}"
    # NOTE: the two perspectives are NOT negatives of each other for random
    # weights (only a trained net learns that symmetry) - the null-move test
    # above therefore only checks accumulator equality + scratch agreement.


def test_null_move_keeps_features_and_flips_perspective() -> None:
    net = _random_net(seed=5)
    board = chess.Board()
    board.push_uci("e2e4")
    acc = net.initial(board)
    new_acc = net.push(board, chess.Move.null(), acc)
    board.push(chess.Move.null())
    # no piece changed squares: accumulators unchanged, side to move flipped
    assert new_acc == acc
    assert math.isclose(
        net.evaluate(new_acc, board.turn), net.evaluate(net.initial(board), board.turn), abs_tol=1e-9
    )


def test_promotion_changes_the_landed_piece() -> None:
    net = _material_net()
    board = chess.Board("8/P6k/8/8/8/8/8/K7 w - - 0 1")
    move = chess.Move.from_uci("a7a8q")
    acc = net.push(board, move, net.initial(board))
    board.push(move)
    # the pawn became a queen (nothing captured): +900 from white's view
    assert net.evaluate(acc, board.turn) == -900


# --------------------------------------------------------------------------- #
# persistence + activation switch
# --------------------------------------------------------------------------- #
def test_save_load_roundtrip(tmp_path) -> None:
    net = _random_net(seed=9)
    path = tmp_path / "net.json"
    import json

    path.write_text(
        json.dumps(
            {
                "hidden": 8,
                "w1": [list(row) for row in net.w1],
                "b1": list(net.b1),
                "w2": list(net.w2),
                "b2": net.b2,
                "meta": {"note": "roundtrip"},
            }
        ),
        encoding="utf-8",
    )
    loaded = Nnue.load(str(path))
    board = chess.Board("r1bqkbnr/pppp1ppp/2n5/4p3/2B1P3/5N2/PPPP1PPP/RNBQK2R b KQkq - 3 3")
    assert loaded.evaluate_board(board) == net.evaluate_board(board)
    assert loaded.meta["note"] == "roundtrip"


def test_search_with_active_net_plays_legal_chess() -> None:
    """Full Searcher run with the accumulator stack engaged."""
    from app.engine.search import Searcher

    nnue.set_active(_material_net())
    # black queen hangs to Nxd5; the extra pawn keeps K+N vs K from being
    # scored as an insufficient-material draw
    board = chess.Board("4k3/8/8/3q4/8/2N5/4P3/4K3 w - - 0 1")
    searcher = Searcher(board, max_depth=3, time_limit_ms=2000)
    result = searcher.search()
    assert result.move is not None and result.move in board.legal_moves
    assert result.move == chess.Move.from_uci("c3d5")  # free queen, material net takes it
    assert result.score > 300  # up queen-for-knight after the trade
    assert len(searcher._acc_stack) == 1  # every push was popped


def test_activation_via_env(tmp_path, monkeypatch) -> None:
    net = _material_net()
    path = tmp_path / "w.json"
    import json

    path.write_text(
        json.dumps(
            {
                "hidden": 2,
                "w1": [list(row) for row in net.w1],
                "b1": list(net.b1),
                "w2": list(net.w2),
                "b2": net.b2,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.delenv("EVAL_BACKEND", raising=False)
    assert nnue.get_active() is None  # default: hand evaluator

    monkeypatch.setenv("EVAL_BACKEND", "nnue")
    monkeypatch.setenv("NNUE_WEIGHTS", str(path))
    active = nnue.get_active()
    assert active is not None
    assert active.hidden == 2
