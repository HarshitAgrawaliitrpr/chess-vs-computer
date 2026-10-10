"""Static evaluation for the negamax search.

Scores are centipawns from White's point of view (the same convention used by
chess.js / Stockfish) so the API layer can report them directly.  The search
negates this value for the side to move.

The evaluation is intentionally lightweight so that thousands of nodes can be
scored per second inside the strict time budget imposed by the API:

  * material + piece-square tables (placement)
  * tapered king placement (middlegame vs. endgame tables)
  * bishop pair bonus
"""

from __future__ import annotations

import chess

# Material values in centipawns.
PIECE_VALUE: dict[int, int] = {
    chess.PAWN: 100,
    chess.KNIGHT: 320,
    chess.BISHOP: 330,
    chess.ROOK: 500,
    chess.QUEEN: 900,
    chess.KING: 0,
}

# How much each piece type contributes to the game "phase" (0..24).
PHASE_WEIGHT: dict[int, int] = {
    chess.PAWN: 0,
    chess.KNIGHT: 1,
    chess.BISHOP: 1,
    chess.ROOK: 2,
    chess.QUEEN: 4,
    chess.KING: 0,
}

BISHOP_PAIR_BONUS = 30
TEMPO_BONUS = 8  # small bonus for the side to move

# Tables are written visually: first row = rank 8, last row = rank 1.
# Indexing: white piece -> table[square ^ 56], black piece -> table[square].
PAWN_TABLE = (
      0,   0,   0,   0,   0,   0,   0,   0,
     50,  50,  50,  50,  50,  50,  50,  50,
     10,  10,  20,  30,  30,  20,  10,  10,
      5,   5,  10,  25,  25,  10,   5,   5,
      0,   0,   0,  20,  20,   0,   0,   0,
      5,  -5, -10,   0,   0, -10,  -5,   5,
      5,  10,  10, -20, -20,  10,  10,   5,
      0,   0,   0,   0,   0,   0,   0,   0,
)

KNIGHT_TABLE = (
    -50, -40, -30, -30, -30, -30, -40, -50,
    -40, -20,   0,   0,   0,   0, -20, -40,
    -30,   0,  10,  15,  15,  10,   0, -30,
    -30,   5,  15,  20,  20,  15,   5, -30,
    -30,   0,  15,  20,  20,  15,   0, -30,
    -30,   5,  10,  15,  15,  10,   5, -30,
    -40, -20,   0,   5,   5,   0, -20, -40,
    -50, -40, -30, -30, -30, -30, -40, -50,
)

BISHOP_TABLE = (
    -20, -10, -10, -10, -10, -10, -10, -20,
    -10,   0,   0,   0,   0,   0,   0, -10,
    -10,   0,   5,  10,  10,   5,   0, -10,
    -10,   5,   5,  10,  10,   5,   5, -10,
    -10,   0,  10,  10,  10,  10,   0, -10,
    -10,  10,  10,  10,  10,  10,  10, -10,
    -10,   5,   0,   0,   0,   0,   5, -10,
    -20, -10, -10, -10, -10, -10, -10, -20,
)

ROOK_TABLE = (
      0,   0,   0,   0,   0,   0,   0,   0,
      5,  10,  10,  10,  10,  10,  10,   5,
     -5,   0,   0,   0,   0,   0,   0,  -5,
     -5,   0,   0,   0,   0,   0,   0,  -5,
     -5,   0,   0,   0,   0,   0,   0,  -5,
     -5,   0,   0,   0,   0,   0,   0,  -5,
     -5,   0,   0,   0,   0,   0,   0,  -5,
      0,   0,   0,   5,   5,   0,   0,   0,
)

QUEEN_TABLE = (
    -20, -10, -10,  -5,  -5, -10, -10, -20,
    -10,   0,   0,   0,   0,   0,   0, -10,
    -10,   0,   5,   5,   5,   5,   0, -10,
     -5,   0,   5,   5,   5,   5,   0,  -5,
      0,   0,   5,   5,   5,   5,   0,  -5,
    -10,   5,   5,   5,   5,   5,   0, -10,
    -10,   0,   5,   0,   0,   0,   0, -10,
    -20, -10, -10,  -5,  -5, -10, -10, -20,
)

KING_MIDGAME_TABLE = (
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -30, -40, -40, -50, -50, -40, -40, -30,
    -20, -30, -30, -40, -40, -30, -30, -20,
    -10, -20, -20, -20, -20, -20, -20, -10,
     20,  20,   0,   0,   0,   0,  20,  20,
     20,  30,  10,   0,   0,  10,  30,  20,
)

KING_ENDGAME_TABLE = (
    -50, -40, -30, -20, -20, -30, -40, -50,
    -30, -20, -10,   0,   0, -10, -20, -30,
    -30, -10,  20,  30,  30,  20, -10, -30,
    -30, -10,  30,  40,  40,  30, -10, -30,
    -30, -10,  30,  40,  40,  30, -10, -30,
    -30, -10,  20,  30,  30,  20, -10, -30,
    -30, -30,   0,   0,   0,   0, -30, -30,
    -50, -30, -30, -30, -30, -30, -30, -50,
)

TABLES: dict[int, tuple[int, ...]] = {
    chess.PAWN: PAWN_TABLE,
    chess.KNIGHT: KNIGHT_TABLE,
    chess.BISHOP: BISHOP_TABLE,
    chess.ROOK: ROOK_TABLE,
    chess.QUEEN: QUEEN_TABLE,
}


def _iter_squares(bitboard: int):
    """Yield every square set in a bitboard (lowest first), no dict building."""
    while bitboard:
        lowest = bitboard & -bitboard
        yield lowest.bit_length() - 1
        bitboard ^= lowest


def evaluate(board: chess.Board) -> int:
    """Return a static evaluation in centipawns (White - Black)."""
    score = 0
    phase_weight = 0

    # Material + placement, via bitboards (avoids constructing a piece dict
    # for every leaf node - this is the hottest code in the whole engine).
    for piece_type in (chess.PAWN, chess.KNIGHT, chess.BISHOP, chess.ROOK, chess.QUEEN):
        white = board.pieces_mask(piece_type, chess.WHITE)
        black = board.pieces_mask(piece_type, chess.BLACK)
        if not white and not black:
            continue

        table = TABLES[piece_type]
        value = PIECE_VALUE[piece_type]
        phase_weight += PHASE_WEIGHT[piece_type] * (
            chess.popcount(white) + chess.popcount(black)
        )

        for square in _iter_squares(white):
            score += value + table[square ^ 56]
        for square in _iter_squares(black):
            score -= value + table[square]

    if chess.popcount(board.pieces_mask(chess.BISHOP, chess.WHITE)) >= 2:
        score += BISHOP_PAIR_BONUS
    if chess.popcount(board.pieces_mask(chess.BISHOP, chess.BLACK)) >= 2:
        score -= BISHOP_PAIR_BONUS

    # Tapered king placement: blend middlegame/endgame tables by remaining
    # phase. Integer maths only - this runs millions of times per search.
    phase = min(phase_weight, 24)
    white_king = board.king(chess.WHITE)
    black_king = board.king(chess.BLACK)
    white_king_score = (
        KING_MIDGAME_TABLE[white_king ^ 56] * phase
        + KING_ENDGAME_TABLE[white_king ^ 56] * (24 - phase)
    ) // 24
    black_king_score = (
        KING_MIDGAME_TABLE[black_king] * phase
        + KING_ENDGAME_TABLE[black_king] * (24 - phase)
    ) // 24
    score += white_king_score - black_king_score

    return score


def evaluate_for_turn(board: chess.Board) -> int:
    """Evaluate from the point of view of the side to move (negamax form)."""
    score = evaluate(board)
    if board.turn == chess.BLACK:
        score = -score
    return score + TEMPO_BONUS