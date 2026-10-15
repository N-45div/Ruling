"""Per-match aggregates and the public figures the engine is calibrated against.

Targets are ranges for the mean over many simulated matches (both teams combined).
`sourced` targets come from published season aggregates; the others are working
estimates with no single public figure behind them, and are labelled as such.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from statistics import mean

from . import events as ev
from .clubs import league
from .engine import DEFAULT_PARAMS, Params, simulate


@dataclass(frozen=True)
class Target:
    low: float
    high: float
    sourced: bool
    note: str


TARGETS: dict[str, Target] = {
    "goals": Target(2.6, 3.2, True, "2.93 per match, 2024-25 season (1,115 goals in 380 matches)"),
    "shots": Target(24.0, 30.0, True, "28.7 per match over a partial 2023-24 sample"),
    "passes": Target(850.0, 980.0, True, "893 (2024-25) to 941 (2023-24) per match"),
    "pass_accuracy": Target(0.76, 0.84, True, "77-82% per team, five leagues 2020-25 (arXiv 2506.22119)"),
    "corners": Target(9.5, 12.0, True, "about 10.8 per match early in 2024-25"),
    "fouls": Target(18.0, 25.0, False, "estimate"),
    "yellows": Target(3.0, 5.0, False, "estimate"),
    "reds": Target(0.03, 0.25, False, "estimate"),
    "offsides": Target(2.0, 5.0, False, "estimate"),
    "penalties": Target(0.15, 0.45, False, "estimate"),
}


def aggregates(match: ev.Match) -> dict[str, float]:
    events = match.events
    passes = [e for e in events if e.type == ev.PASS]
    return {
        "goals": sum(e.result == ev.GOAL for e in events),
        "shots": sum(e.type == ev.SHOT for e in events),
        "passes": len(passes),
        "pass_accuracy": sum(e.result == ev.SUCCESS for e in passes) / max(1, len(passes)),
        "corners": sum(e.type == ev.CORNER for e in events),
        "fouls": sum(e.type == ev.FOUL for e in events),
        "yellows": sum(e.type == ev.CARD and e.result in (ev.YELLOW, ev.SECOND_YELLOW) for e in events),
        "reds": sum(e.type == ev.CARD and e.result in (ev.RED, ev.SECOND_YELLOW) for e in events),
        "offsides": sum(e.type == ev.OFFSIDE for e in events),
        "penalties": sum(e.type == ev.PENALTY for e in events),
    }


def fixtures(seeds: range | list[int]) -> list[tuple[str, str, int]]:
    """A deterministic home/away pairing for each seed."""
    codes = sorted(league())
    out = []
    for seed in seeds:
        home, away = random.Random(f"fixture:{seed}").sample(codes, 2)
        out.append((home, away, seed))
    return out


def run(seeds: range | list[int], params: Params = DEFAULT_PARAMS) -> dict[str, float]:
    clubs = league()
    rows = [aggregates(simulate(clubs[h], clubs[a], s, params)) for h, a, s in fixtures(seeds)]
    return {key: mean(row[key] for row in rows) for key in TARGETS}


def misses(means: dict[str, float]) -> dict[str, float]:
    """Aggregates whose mean falls outside its target range."""
    return {k: v for k, v in means.items() if not TARGETS[k].low <= v <= TARGETS[k].high}
