"""Difficulty profiles.

Each profile couples a **maximum** search depth with a wall-clock budget. The
engine always returns the best move of the deepest *completed* depth, so the
depth is an upper bound: dense middlegame positions settle at a lower depth
than open ones within the same budget.

The budgets are tuned for the CPU that actually runs the games - Vercel's
serverless CPU is roughly 4x slower than a dev laptop, and before this
tuning `hard` and `master` BOTH hit their caps at depth 4 in production
(identical moves, identical strength behind different Elo labels). The
numbers below guarantee a strict ladder where the user plays:

    profile  max depth  time budget  noise   prod depth*  ~Elo
    easy     1          150 ms       60 cp   1            750
    medium   3          1000 ms      15 cp   3            1250
    hard     5          2500 ms      0       4            1650
    master   7          8000 ms      0       5            2000

    * typical completed depth on production serverless hardware in dense
      middlegames; fast positions and local dev machines go deeper.

On a fast machine the same budgets reach the full caps (hard=5, master=6-7).
The wall-clock budget is only a safety net behind the depth cap - it may
never cut a level so low that it collapses onto the level below it.

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
        time_limit_ms=1000,
        noise_cp=15,
        elo=1250,
    ),
    "hard": EngineProfile(
        name="hard",
        label="Strong club player",
        max_depth=5,
        time_limit_ms=2500,
        noise_cp=0,
        elo=1650,
    ),
    "master": EngineProfile(
        name="master",
        label="Expert",
        max_depth=7,
        time_limit_ms=8000,
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