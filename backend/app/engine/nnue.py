"""NNUE-style neural evaluator: 768 -> H -> 1 with a ReLU hidden layer.

"Efficiently Updatable" is the whole point: the hidden-layer activations are
maintained INCREMENTALLY as moves are pushed, so a leaf evaluation costs a
handful of float adds instead of rebuilding the feature vector from scratch.
Pure Python at inference time - no numpy import on the server (numpy is a
training-time dependency only, see backend/scripts/nnue_train.py).

Architecture
------------
Inputs are one-hot "piece placed on square" features from the SIDE-TO-MOVE
perspective (768 = 2 perspectives * 6 piece types * 64 squares; kings are
excluded, the usual simplification).  Two hidden accumulators are kept - one
for each king-color perspective - and the forward pass simply picks the one
belonging to the side to move.  A single hidden layer of ReLU neurons maps to
one scalar: centipawns from the side to move's point of view (the same
negamax convention as evaluation.evaluate_for_turn).

Weights live in a JSON file (weights/*.json) produced by the training script.
The net is activated by setting EVAL_BACKEND=nnue (plus optionally
NNUE_WEIGHTS=/path/to/weights.json); with the default EVAL_BACKEND=hand the
engine behaves exactly as before, NNUE code paths excluded.
"""

from __future__ import annotations

import json
import os
from typing import Dict, List, Optional, Tuple

import chess

# Defaults (the training script writes matching metadata into the file).
DEFAULT_WEIGHTS = os.path.join(os.path.dirname(__file__), "weights", "nnue-32-v1.json")

# Accumulator: (white-perspective hidden, black-perspective hidden).
Accumulator = Tuple[List[float], List[float]]

_NULL_MOVE = chess.Move.null()


def _piece_color_is_white(board: chess.Board, square: int) -> bool:
    return bool(board.occupied_co[chess.WHITE] & (1 << square))


def _oriented(square: int, perspective_is_white: bool) -> int:
    """Map a square into a perspective (black sees the board rank-flipped)."""
    return square if perspective_is_white else square ^ 56


def _feature_index(piece: chess.Piece, square: int, perspective_white: bool) -> int:
    """One-hot input for `piece` on `square` seen from `perspective_white`."""
    own = piece.color == perspective_white
    base = (piece.piece_type - 1) * 64 if own else (piece.piece_type - 1 + 6) * 64
    return base + _oriented(square, perspective_white)


class Nnue:
    """The trained network: feature rows + hidden/output weights."""

    def __init__(
        self,
        w1: List[Tuple[float, ...]],  # [768][hidden] feature rows
        b1: Tuple[float, ...],  # [hidden]
        w2: Tuple[float, ...],  # [hidden]
        b2: float,
        hidden: int,
        meta: Optional[Dict] = None,
    ) -> None:
        if len(w1) != 768 or any(len(row) != hidden for row in w1):
            raise ValueError("w1 must be [768][hidden]")
        if len(b1) != hidden or len(w2) != hidden:
            raise ValueError("weight shapes do not match hidden size")
        self.w1 = w1
        self.b1 = b1
        self.w2 = w2
        self.b2 = b2
        self.hidden = hidden
        self.meta = meta or {}

    # ------------------------------------------------------------------ #
    # persistence
    # ------------------------------------------------------------------ #
    @classmethod
    def load(cls, path: str) -> "Nnue":
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        hidden = int(data["hidden"])
        w1 = [tuple(float(x) for x in row) for row in data["w1"]]
        b1 = tuple(float(x) for x in data["b1"])
        w2 = tuple(float(x) for x in data["w2"])
        b2 = float(data["b2"])
        meta = data.get("meta", {})
        return cls(w1=w1, b1=b1, w2=w2, b2=b2, hidden=hidden, meta=meta)

    # ------------------------------------------------------------------ #
    # accumulators
    # ------------------------------------------------------------------ #
    def initial(self, board: chess.Board) -> Accumulator:
        """Build both accumulators from scratch for `board`."""
        acc_w = list(self.b1)
        acc_b = list(self.b1)
        hidden = self.hidden
        for square, piece in board.piece_map().items():
            if piece.piece_type == chess.KING:
                continue
            row_w = self.w1[_feature_index(piece, square, True)]
            row_b = self.w1[_feature_index(piece, square, False)]
            for j in range(hidden):
                acc_w[j] += row_w[j]
                acc_b[j] += row_b[j]
        return acc_w, acc_b

    def push(self, board: chess.Board, move: chess.Move, acc: Accumulator) -> Accumulator:
        """Accumulator for the position AFTER `move` (board is pre-move).

        Handles quiet moves, captures, en passant, promotions (incl. under),
        castling (the rook teleports too) and null moves (no feature change).
        """
        acc_w, acc_b = list(acc[0]), list(acc[1])  # copy-on-write for the stack
        if move == _NULL_MOVE:
            return acc_w, acc_b

        # NOTE: piece_type_at (bitboard test), never piece_at - the latter
        # builds a full piece dict per call, which is ~10x slower.
        from_type = board.piece_type_at(move.from_square)
        if from_type is None:
            # Unknown state -> fall back to a scratch rebuild (never corrupt).
            return self.initial(board)
        piece = chess.Piece(
            from_type, _piece_color_is_white(board, move.from_square)
        )

        if (
            piece.piece_type == chess.KING
            and abs(
                chess.square_file(move.to_square) - chess.square_file(move.from_square)
            )
            not in (0, 1, 2)  # 2 files = castling (a legal king "teleport")
        ):
            return self.initial(board)

        # Removing the mover (and the rook on castling) happens before the
        # destination is added, using the pre-move board for capture info.
        captured: Optional[chess.Piece] = None
        capture_square: Optional[int] = None
        if board.is_en_passant(move):
            capture_square = chess.square(
                chess.square_file(move.to_square), chess.square_rank(move.from_square)
            )
        elif board.piece_type_at(move.to_square) is not None:
            capture_square = move.to_square
        if capture_square is not None:
            captured = chess.Piece(
                board.piece_type_at(capture_square),
                _piece_color_is_white(board, capture_square),
            )

        self._add_row(acc_w, acc_b, move.from_square, piece, -1.0)
        if captured is not None and capture_square is not None:
            self._add_row(acc_w, acc_b, capture_square, captured, -1.0)

        landed = piece
        if move.promotion:
            landed = chess.Piece(move.promotion, piece.color)
        self._add_row(acc_w, acc_b, move.to_square, landed, +1.0)

        # Castling: python-chess encodes it as a two-square king move; the
        # rook moves as well and must be reflected in the features.
        if piece.piece_type == chess.KING:
            from_file = chess.square_file(move.from_square)
            to_file = chess.square_file(move.to_square)
            if abs(to_file - from_file) == 2:
                rook_from = move.to_square + 1 if to_file == 6 else move.to_square - 2
                rook_to = move.to_square - 1 if to_file == 6 else move.to_square + 1
                rook = chess.Piece(chess.ROOK, piece.color)
                self._add_row(acc_w, acc_b, rook_from, rook, -1.0)
                self._add_row(acc_w, acc_b, rook_to, rook, +1.0)

        return acc_w, acc_b

    def _add_row(
        self, acc_w: List[float], acc_b: List[float], square: int, piece: chess.Piece, sign: float
    ) -> None:
        if piece is None or piece.piece_type == chess.KING:
            return  # kings are not features
        hidden = self.hidden
        row_w = self.w1[_feature_index(piece, square, True)]
        row_b = self.w1[_feature_index(piece, square, False)]
        if sign > 0:
            for j in range(hidden):
                acc_w[j] += row_w[j]
                acc_b[j] += row_b[j]
        else:
            for j in range(hidden):
                acc_w[j] -= row_w[j]
                acc_b[j] -= row_b[j]

    # ------------------------------------------------------------------ #
    # forward pass
    # ------------------------------------------------------------------ #
    def forward(self, acc: Accumulator, turn: bool) -> float:
        """Raw network output in centipawns from `turn`'s point of view."""
        hidden = self.hidden
        a = acc[0] if turn else acc[1]
        w2 = self.w2
        total = self.b2
        for j in range(hidden):
            v = a[j]
            if v > 0.0:
                total += w2[j] * v
        return total

    def evaluate(self, acc: Accumulator, turn: bool) -> int:
        """Integer centipawns (negamax convention) from `turn`'s view."""
        return int(round(self.forward(acc, turn)))

    def evaluate_board(self, board: chess.Board) -> int:
        """From-scratch evaluation (tests/probes; the search stays incremental)."""
        return self.evaluate(self.initial(board), board.turn)


# --------------------------------------------------------------------------- #
# module-level activation (EVAL_BACKEND=nnue)
# --------------------------------------------------------------------------- #
_ACTIVE: Optional[Nnue] = None
_LOAD_ATTEMPTED = False


def get_active() -> Optional[Nnue]:
    """The globally enabled net, or None to use the hand-written evaluator."""
    global _ACTIVE, _LOAD_ATTEMPTED
    if _ACTIVE is not None:
        return _ACTIVE
    if _LOAD_ATTEMPTED or os.environ.get("EVAL_BACKEND", "hand").lower() != "nnue":
        return None
    _LOAD_ATTEMPTED = True
    path = os.environ.get("NNUE_WEIGHTS", DEFAULT_WEIGHTS)
    if not os.path.exists(path):
        return None
    _ACTIVE = Nnue.load(path)
    return _ACTIVE


def set_active(net: Optional[Nnue]) -> None:
    """Force a net (tests, experiments); None restores the hand evaluator."""
    global _ACTIVE, _LOAD_ATTEMPTED
    _ACTIVE = net
    _LOAD_ATTEMPTED = net is not None
