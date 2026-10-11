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
    easy     1          100 ms       60 cp   1            750
    medium   3          400 ms       15 cp   3            1250
    hard     5          1800 ms      0       5            1650
    master   6          8000 ms      0       6            2000

    * measured on production serverless hardware (bom1 region) in a
    dense middlegame, October 2026: easy 6 ms, medium 103 ms,
    hard 921 ms, master ~5.5 s of search. Fast positions and local dev
    machines go deeper.

easy/medium/hard hit their DEPTH cap long before the budget (6/103/921
ms), so their budgets are pure worst-case safety nets - trimmed to
100/400/1800 ms with 4-16x headroom so a slow instance can never spend
seconds on a level that already decided what to play. `master` is the
inverse: its cap (7, October 2026 -> 6) used to sit above what the
budget could finish, so the engine burned the FULL 8 s attempting depth
7 and returning depth 6 anyway - capping at 6 lets it stop the moment
depth 6 completes (~5.5 s typical), same worst case, 2.5 s faster
typical. The wall-clock budget may never cut a level so low that it
collapses onto the level below it (master aborting to depth 5 == hard).

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
        time_limit_ms=100,
        noise_cp=60,
        elo=750,
    ),
    "medium": EngineProfile(
        name="medium",
        label="Club player",
        max_depth=3,
        time_limit_ms=400,
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
        max_depth=6,
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