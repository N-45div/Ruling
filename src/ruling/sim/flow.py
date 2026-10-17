"""Match-flow records shared by the engine and its VAR reviews."""

from __future__ import annotations

from dataclasses import dataclass

from . import events as ev

REGAIN = "regain"  # an open-play turnover: no restart event


@dataclass(frozen=True)
class Restart:
    kind: str  # an events restart type, or REGAIN
    team: int  # 0 = home, 1 = away
    x: float  # attacking frame of `team`
    y: float
    detail: str | None = None


# Range of seconds the ball is dead before each restart.
DEAD_TIME = {
    ev.THROW_IN: (7, 16), ev.GOAL_KICK: (16, 30), ev.CORNER: (22, 40), ev.FREE_KICK: (16, 40),
    ev.KICKOFF: (50, 85), ev.PENALTY: (60, 110), ev.OFFSIDE: (14, 28),
}
