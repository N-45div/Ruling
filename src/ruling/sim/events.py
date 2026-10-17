"""The match event record shared by the generator, the evidence tools and the UI.

The schema follows the spirit of SPADL (one row per on-ball action, start and end
coordinates, a result), extended with restarts, fouls, cards and VAR-relevant detail.
All coordinates are absolute (see `ruling.sim.pitch`).
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Iterable, Iterator

PERIOD_SECONDS = 45 * 60

# On-ball actions
PASS = "pass"
CROSS = "cross"
CARRY = "carry"
DRIBBLE = "dribble"
SHOT = "shot"
# Defensive actions
TACKLE = "tackle"
INTERCEPTION = "interception"
CLEARANCE = "clearance"
SAVE = "keeper_save"
CLAIM = "keeper_claim"
# Stoppages and restarts
FOUL = "foul"
CARD = "card"
OFFSIDE = "offside"
BALL_OUT = "ball_out"
KICKOFF = "kickoff"
THROW_IN = "throw_in"
GOAL_KICK = "goal_kick"
CORNER = "corner"
FREE_KICK = "free_kick"
PENALTY = "penalty"
DROPPED_BALL = "dropped_ball"
PERIOD_START = "period_start"
PERIOD_END = "period_end"
# Video review: a check on an event, then the decision ("<review>|shot:<index>" in detail)
VAR_CHECK = "var_check"
VAR_DECISION = "var_decision"

RESTARTS = frozenset({KICKOFF, THROW_IN, GOAL_KICK, CORNER, FREE_KICK, PENALTY, DROPPED_BALL})

# Results
SUCCESS = "success"
FAIL = "fail"
GOAL = "goal"  # for a shot: the ball crossed the line; VAR may still rule it out
NO_GOAL = "no_goal"
SAVED = "saved"
OFF_TARGET = "off_target"
BLOCKED = "blocked"
YELLOW = "yellow"
SECOND_YELLOW = "second_yellow"
RED = "red"


@dataclass(frozen=True, slots=True)
class Event:
    match_id: str
    index: int
    period: int
    second: float  # seconds since the start of the period
    team: str  # club code of the team performing the action
    player: str | None  # player id, None for team-level events
    type: str
    result: str
    start_x: float
    start_y: float
    end_x: float
    end_y: float
    body_part: str = "foot"
    receiver: str | None = None  # the intended receiver of a pass or cross, or the fouled player
    xg: float | None = None
    detail: str | None = None  # e.g. the reason for a restart or a card

    @property
    def clock(self) -> str:
        """Match clock as shown on a broadcast, with stoppage time as 45+m or 90+m."""
        base = 0 if self.period == 1 else 45
        whole = int(self.second)
        if whole < PERIOD_SECONDS:
            minute, sec = divmod(whole, 60)
            return f"{base + minute:02d}:{sec:02d}"
        extra, sec = divmod(whole - PERIOD_SECONDS, 60)
        return f"{base + 45}+{extra}:{sec:02d}"


@dataclass(slots=True)
class Match:
    id: str
    seed: int
    home: str
    away: str
    events: list[Event] = field(default_factory=list)
    home_lineup: list[str] = field(default_factory=list)
    away_lineup: list[str] = field(default_factory=list)
    incidents: list = field(default_factory=list)  # ruling.incidents.model.Incident

    def disallowed(self) -> set[int]:
        """Indices of shots that crossed the line but were ruled out after a VAR decision."""
        out = set()
        for e in self.events:
            if e.type == VAR_DECISION and e.result == NO_GOAL and e.detail:
                out.update(int(p[5:]) for p in e.detail.split("|") if p.startswith("shot:"))
        return out

    def attacks_right(self, team: str, period: int) -> bool:
        """The home team attacks towards x = 105 in the first half, the away team in the second."""
        return (team == self.home) == (period == 1)

    def goals(self) -> list[Event]:
        """Goals that stand."""
        ruled_out = self.disallowed()
        return [e for e in self.events if e.type == SHOT and e.result == GOAL and e.index not in ruled_out]

    def score(self) -> tuple[int, int]:
        goals = self.goals()
        return sum(e.team == self.home for e in goals), sum(e.team == self.away for e in goals)


def write_events(path: Path, events: Iterable[Event]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for event in events:
            fh.write(json.dumps(asdict(event), separators=(",", ":")) + "\n")


def read_events(path: Path) -> Iterator[Event]:
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield Event(**json.loads(line))
