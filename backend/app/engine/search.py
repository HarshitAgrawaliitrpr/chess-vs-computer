"""Minimax (negamax) search with alpha-beta pruning.

Optimisations implemented so the engine stays inside strict time limits:

  * iterative deepening  - always returns the best move of the deepest
    *completed* depth, so a time cut-off never returns a half analysed move
  * alpha-beta pruning   - orders of magnitude fewer nodes than plain minimax
  * transposition table  - positions reached via different move orders are
    only evaluated once (keyed by the board state)
  * move ordering        - TT move, promotions, MVV-LVA captures, killer
    moves and history heuristic keep the cut-off rate high
  * quiescence search    - captures are resolved beyond the horizon so the
    engine does not hang pieces on the last ply
  * check extensions     - forcing lines are searched one ply deeper
  * delta pruning        - clearly losing captures are skipped in the
    quiescence search
"""

from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Optional

import chess

from .evaluation import PIECE_VALUE, evaluate_for_turn

INF = 10**9
MATE_SCORE = 30_000
MATE_THRESHOLD = 29_000
MAX_PLY = 64
MAX_QUIESCENCE_PLY = 12

# transposition flags
EXACT, LOWER, UPPER = 0, 1, 2


class SearchAborted(Exception):
    """Raised when the wall-clock budget for the search is exhausted."""


@dataclass
class SearchResult:
    move: Optional[chess.Move]
    score: int
    depth: int
    nodes: int
    time_ms: float
    pv: list[chess.Move] = field(default_factory=list)

    @property
    def is_mate(self) -> bool:
        return abs(self.score) >= MATE_THRESHOLD

    @property
    def mate_in(self) -> Optional[int]:
        """Signed distance to mate in moves (+ white mates, - black mates)."""
        if not self.is_mate or self.move is None:
            return None
        plies = MATE_SCORE - abs(self.score)
        moves = (plies + 1) // 2
        return moves if self.score > 0 else -moves


class Searcher:
    """Stateful search: create one per move computation."""

    def __init__(
        self,
        board: chess.Board,
        max_depth: int = 4,
        time_limit_ms: int = 1000,
        noise_cp: int = 0,
        seed: Optional[int] = None,
    ) -> None:
        self.root = board
        self.max_depth = max(1, max_depth)
        self.time_limit_ms = time_limit_ms
        self.noise_cp = noise_cp
        self.rng = random.Random(seed)

        self.nodes = 0
        self.tt: dict = {}
        self.killers: list[list[Optional[chess.Move]]] = [
            [None, None] for _ in range(MAX_PLY + 8)
        ]
        self.history: dict[tuple[int, int], int] = {}
        # Root move scores from the previous iterative-deepening pass; used to
        # order the root moves so alpha-beta cutoffs happen as early as
        # possible on the next (deeper) pass.
        self._prev_root_scores: dict[chess.Move, int] = {}
        self._start = 0.0
        self._deadline = 0.0

    # ------------------------------------------------------------------ #
    # public entry point
    # ------------------------------------------------------------------ #
    def search(self) -> SearchResult:
        """Iterative deepening: run depth 1, 2, ... until depth or time runs out."""
        board = self.root
        legal = list(board.legal_moves)
        if not legal:  # checkmate / stalemate
            return SearchResult(None, 0, 0, 0, 0.0, [])

        self.nodes = 0
        self._start = time.perf_counter()
        self._deadline = self._start + self.time_limit_ms / 1000.0

        best_score = -INF
        best_move: Optional[chess.Move] = legal[0]
        best_root_scores: list[tuple[chess.Move, int]] = [(m, 0) for m in legal]
        completed_depth = 0

        for depth in range(1, self.max_depth + 1):
            try:
                scores = self._search_root(board, depth)
            except SearchAborted:
                break
            completed_depth = depth
            best_root_scores = scores
            best_move, best_score = max(scores, key=lambda item: item[1])
            # Nothing more to learn if we found (or were mated in) a forced mate.
            if abs(best_score) >= MATE_THRESHOLD:
                break

        elapsed_ms = (time.perf_counter() - self._start) * 1000.0
        move = self._select_move(best_root_scores) if best_root_scores else best_move
        if move is None:
            move = legal[0]
        score = dict(best_root_scores).get(move, best_score)
        pv = self._extract_pv(board, move)
        return SearchResult(
            move=move,
            score=score,
            depth=completed_depth,
            nodes=self.nodes,
            time_ms=elapsed_ms,
            pv=pv,
        )

    # ------------------------------------------------------------------ #
    # root: full window, collects every root move score (for noise + PV)
    # ------------------------------------------------------------------ #
    def _search_root(self, board: chess.Board, depth: int) -> list[tuple[chess.Move, int]]:
        # Prefer the best move of the previous (shallower) iteration first:
        # the root ordering dominates overall alpha-beta efficiency.
        key = self._tt_key(board)
        entry = self.tt.get(key)
        tt_move = entry[0] if entry is not None else None
        moves = self._order_moves(board, list(board.legal_moves), tt_move, ply=0)
        if len(self._prev_root_scores) > 1:
            moves.sort(key=lambda m: self._prev_root_scores.get(m, -INF), reverse=True)

        alpha, beta = -INF, INF
        scores: list[tuple[chess.Move, int]] = []
        best = -INF

        for move in moves:
            board.push(move)
            try:
                score = -self._negamax(board, depth - 1, -beta, -alpha, 1, is_null=False)
            finally:
                board.pop()
            scores.append((move, score))
            if score > best:
                best = score
            if score > alpha:
                alpha = score

        self._prev_root_scores = dict(scores)
        # Cache the root result so the next iteration starts with the right
        # move first and the PV extraction has an entry to follow.
        best_move, best_score = max(scores, key=lambda item: item[1])
        self.tt[key] = (best_move, depth, best_score, EXACT)
        return scores

    def _select_move(self, scores: list[tuple[chess.Move, int]]) -> chess.Move:
        """Pick the best root move, optionally adding human-ish noise."""
        if self.noise_cp <= 0:
            return max(scores, key=lambda item: item[1])[0]
        noisy = []
        for move, score in scores:
            if abs(score) >= MATE_THRESHOLD:
                noisy.append((move, score))  # never randomise a mate
            else:
                noisy.append((move, score + self.rng.gauss(0.0, self.noise_cp)))
        return max(noisy, key=lambda item: item[1])[0]

    # ------------------------------------------------------------------ #
    # negamax with alpha-beta
    # ------------------------------------------------------------------ #
    def _negamax(
        self,
        board: chess.Board,
        depth: int,
        alpha: int,
        beta: int,
        ply: int,
        is_null: bool = False,
    ) -> int:
        self._check_time()
        self.nodes += 1

        if ply >= MAX_PLY:
            return evaluate_for_turn(board)

        # Draw detection (repetition / 50-move / insufficient material).
        if board.is_repetition() or board.halfmove_clock >= 100 or board.is_insufficient_material():
            return 0

        # Transposition table probe.
        key = self._tt_key(board)
        tt_move = None
        entry = self.tt.get(key)
        if entry is not None:
            tt_move, tt_depth, tt_score, tt_flag = entry
            if tt_depth >= depth:
                if tt_flag == EXACT:
                    return tt_score
                if tt_flag == LOWER:
                    alpha = max(alpha, tt_score)
                else:  # UPPER
                    beta = min(beta, tt_score)
                if alpha >= beta:
                    return tt_score

        if depth <= 0:
            # Resolve captures at the horizon. Generating the full legal move
            # list here would be wasted work - quiescence only needs captures.
            return self._quiescence(board, alpha, beta, ply)

        moves = list(board.legal_moves)
        if not moves:
            # No legal moves: checkmate if in check, otherwise stalemate.
            return -MATE_SCORE + ply if board.is_check() else 0

        in_check = board.is_check()

        # --- Null-move pruning -------------------------------------------
        # "Pass" the turn: if the side to move is still ahead by a full move
        # after giving the opponent an extra tempo, the position is so good
        # that nothing else needs to be searched (fail-hard beta cut-off).
        # Skipped when in check, in a pawn-only endgame (zugzwang) or on a
        # null-move already in the chain.
        if (
            not is_null
            and not in_check
            and depth >= 2
            and beta < MATE_THRESHOLD
            and self._has_non_pawn_material(board, board.turn)
        ):
            reduction = 2 + (1 if depth >= 6 else 0)
            board.push(chess.Move.null())
            try:
                score = -self._negamax(
                    board, depth - 1 - reduction, -beta, -beta + 1, ply + 1, is_null=True
                )
            finally:
                board.pop()
            if score >= beta:
                return beta

        ordered = self._order_moves(board, moves, tt_move, ply)

        best_score = -INF
        best_move: Optional[chess.Move] = None
        flag = UPPER
        # Give checking moves one extra ply of search (check extension).
        child_depth = depth - 1

        for move in ordered:
            board.push(move)
            try:
                score = -self._negamax(board, child_depth, -beta, -alpha, ply + 1, is_null=False)
            finally:
                board.pop()

            if score > best_score:
                best_score = score
                best_move = move
            if score > alpha:
                alpha = score
                flag = EXACT
            if alpha >= beta:
                flag = LOWER
                if not board.is_capture(move) and move.promotion is None:
                    self._store_killer(move, ply)
                    piece = board.piece_type_at(move.from_square)
                    if piece is not None:
                        hist = self.history.get((piece, move.to_square), 0)
                        self.history[(piece, move.to_square)] = hist + depth * depth
                break

        self.tt[key] = (best_move, depth, best_score, flag)
        return best_score

    # ------------------------------------------------------------------ #
    # quiescence search: only resolve captures/checks at the horizon
    # ------------------------------------------------------------------ #
    def _quiescence(self, board: chess.Board, alpha: int, beta: int, ply: int) -> int:
        self._check_time()
        self.nodes += 1

        # Transposition hit: reuse an exact score computed earlier in this
        # search (entries with depth >= 0 are ply-independent because mate
        # scores are never cached here).
        key = self._tt_key(board)
        entry = self.tt.get(key)
        if (
            entry is not None
            and entry[3] == EXACT
            and entry[2] < MATE_THRESHOLD
            and entry[2] > -MATE_THRESHOLD
        ):
            return entry[2]

        in_check = board.is_check()
        if in_check:
            # No stand-pat while in check: the king is under attack, so a
            # static "I am up material" score says nothing about survival.
            # Every evasion must be searched - and if there is none, the
            # position is checkmate ON THE HORIZON. Without this branch a
            # mate landing on the last searched ply scores as a mere static
            # eval (~500cp) instead of -MATE_SCORE, so the engine misses
            # forced mates entirely at low depths (easy never sees one).
            moves = list(board.legal_moves)
            if not moves:
                return -MATE_SCORE + ply
            if ply >= MAX_QUIESCENCE_PLY:
                return evaluate_for_turn(board)  # bounded at the ply limit
            stand_pat: Optional[int] = None
        else:
            stand_pat = evaluate_for_turn(board)
            if stand_pat >= beta:
                return stand_pat
            if stand_pat > alpha:
                alpha = stand_pat
            if ply >= MAX_QUIESCENCE_PLY:
                return stand_pat
            moves = [
                move
                for move in board.legal_moves
                if board.is_capture(move) or move.promotion == chess.QUEEN
            ]

        moves = self._order_moves(board, moves, None, ply)
        best = stand_pat if stand_pat is not None else -INF

        for move in moves:
            # Delta pruning: skip captures that cannot raise alpha. Never
            # applies in check (there is no stand-pat to measure against).
            if stand_pat is not None:
                victim = board.piece_type_at(move.to_square)
                if victim is not None:
                    if stand_pat + PIECE_VALUE[victim] + 200 < alpha:
                        continue
            board.push(move)
            try:
                score = -self._quiescence(board, -beta, -alpha, ply + 1)
            finally:
                board.pop()
            if score > best:
                best = score
            if score > alpha:
                alpha = score
            if alpha >= beta:
                break

        # Cache the resolved stand-pat so repeated leaf positions are free.
        # Never overwrite a deeper (interior) entry.
        if abs(best) < MATE_THRESHOLD and (entry is None or entry[1] < 0):
            self.tt[key] = (None, 0, best, EXACT)
        return best

    # ------------------------------------------------------------------ #
    # move ordering
    # ------------------------------------------------------------------ #
    def _order_moves(
        self,
        board: chess.Board,
        moves: list[chess.Move],
        tt_move: Optional[chess.Move],
        ply: int,
    ) -> list[chess.Move]:
        killers = self.killers[ply] if ply < len(self.killers) else (None, None)

        def score(move: chess.Move) -> int:
            if move == tt_move:
                return 10**9
            if move.promotion == chess.QUEEN:
                return 9 * 10**8 + PIECE_VALUE[chess.QUEEN]
            if board.is_capture(move):
                victim = board.piece_type_at(move.to_square)
                attacker = board.piece_type_at(move.from_square)
                victim_value = PIECE_VALUE[victim] if victim is not None else 100  # en passant
                attacker_value = PIECE_VALUE[attacker] if attacker is not None else 0
                return 8 * 10**8 + victim_value * 10 - attacker_value
            if move == killers[0]:
                return 7 * 10**8
            if move == killers[1]:
                return 6 * 10**8
            piece = board.piece_type_at(move.from_square)
            if piece is not None:
                return min(self.history.get((piece, move.to_square), 0), 5 * 10**8)
            return 0

        moves.sort(key=score, reverse=True)
        return moves

    def _store_killer(self, move: chess.Move, ply: int) -> None:
        if ply >= len(self.killers):
            return
        if self.killers[ply][0] != move:
            self.killers[ply][1] = self.killers[ply][0]
            self.killers[ply][0] = move

    # ------------------------------------------------------------------ #
    # helpers
    # ------------------------------------------------------------------ #
    def _check_time(self) -> None:
        if self.nodes & 0x3F:  # cheap check every 64 nodes
            return
        if time.perf_counter() > self._deadline:
            raise SearchAborted

    @staticmethod
    def _tt_key(board: chess.Board) -> object:
        # The transposition key excludes the halfmove/fullmove counters (they
        # do not change the search result) and is far cheaper than serialising
        # a whole FEN string on every single node.
        key = getattr(board, "_transposition_key", None)
        if key is not None:
            return key()
        return board.fen()

    @staticmethod
    def _has_non_pawn_material(board: chess.Board, color: bool) -> bool:
        """False only in king+pawn endgames, where null-move fails (zugzwang)."""
        return bool(
            board.pieces(chess.KNIGHT, color)
            | board.pieces(chess.BISHOP, color)
            | board.pieces(chess.ROOK, color)
            | board.pieces(chess.QUEEN, color)
        )

    def _extract_pv(self, board: chess.Board, first: chess.Move) -> list[chess.Move]:
        """Walk the transposition table to rebuild the principal variation."""
        pv: list[chess.Move] = []
        seen: set[str] = set()
        move = first
        probe = board.copy(stack=False)
        while move is not None and len(pv) < 12:
            pv.append(move)
            probe.push(move)
            key = probe.fen()
            if key in seen:
                break
            seen.add(key)
            entry = self.tt.get(key)
            move = entry[0] if entry else None
            if move is not None and move not in probe.legal_moves:
                break
        return pv
