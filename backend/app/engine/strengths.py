"""Difficulty profiles.

Each profile couples a **maximum** search depth with a wall-clock budget. The
engine always returns the best move of the deepest *completed* depth, so the
depth is an upper bound: dense middlegame positions settle at a lower depth
than open ones within the same budget (typical measured depths below).

    profile  max depth  time budget  noise   typical depth reached   ~Elo
    easy     1          150 ms       60 cp   1                       750
    medium   3          700 ms       15 cp   2-3                     1250
    hard     5          1800 ms      0       4-5                     1650
    master   7          3500 ms      0       4-6                     2000

The gaussian noise on the weaker levels makes them behave like a human
beginner (occasional sub-optimal moves) instead of a rigid 1-ply bot, while
the stronger levels search deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class EngineProfile:
    name: str
    label: str
    max_depth: int
    time_limit_ms: int
    noise_cp: int  # gaussian noise (centipawns) applied to root moves
    elo: int


PROFILES: dict[str, EngineProfile] = {
    "easy": EngineProfile(
        name="easy",
        label="Beginner",
        max_depth=1,
        time_limit_ms=150,
        noise_cp=60,
        elo=750,
    ),
    "medium": EngineProfile(
        name="medium",
        label="Club player",
        max_depth=3,
        time_limit_ms=700,
        noise_cp=15,
        elo=1250,
    ),
    "hard": EngineProfile(
        name="hard",
        label="Strong club player",
        max_depth=5,
        time_limit_ms=1800,
        noise_cp=0,
        elo=1650,
    ),
    "master": EngineProfile(
        name="master",
        label="Expert",
        max_depth=7,
        time_limit_ms=3500,
        noise_cp=0,
        elo=2000,
    ),
}

DEFAULT_PROFILE = PROFILES["medium"]
MIN_DEPTH = 1
MAX_DEPTH = 10


def resolve_profile(difficulty: str, depth: int | None, time_limit_ms: int | None) -> EngineProfile:
    """Merge an API request onto a named difficulty profile."""
    profile = PROFILES.get(difficulty, DEFAULT_PROFILE)
    if depth is None and time_limit_ms is None:
        return profile
    return EngineProfile(
        name=profile.name,
        label=profile.label,
        max_depth=max(MIN_DEPTH, min(depth if depth is not None else profile.max_depth, MAX_DEPTH)),
        time_limit_ms=max(50, min(time_limit_ms if time_limit_ms is not None else profile.time_limit_ms, 10_000)),
        noise_cp=profile.noise_cp if depth is None else 0,
        elo=profile.elo,
    )