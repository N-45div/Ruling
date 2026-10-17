"""Player bodies at a key moment, built from a freeze-frame.

Poses are worked on in the attacking frame of the team in possession (as mutable lists)
and frozen into absolute-coordinate `Body` records once placed.
"""

from __future__ import annotations

import random

from ..sim import pitch
from ..sim.shape import Frame, PlayerSpot
from . import model as m

Pose = dict[str, list[float]]


def pose(x: float, y: float, facing: float, rng: random.Random) -> Pose:
    """Body parts around a torso at (x, y), attacking frame. facing is +1 or -1 along x."""
    lean = rng.uniform(-0.05, 0.15) * facing
    front, back = rng.uniform(0.1, 0.55) * facing, -rng.uniform(0.1, 0.45) * facing
    side = 1 if rng.random() < 0.5 else -1
    return {
        "torso": [x, y],
        "head": [x + lean, y],
        "left_shoulder": [x + lean * 0.8, y + 0.22],
        "right_shoulder": [x + lean * 0.8, y - 0.22],
        "left_knee": [x + (front if side > 0 else back) * 0.5, y + 0.12],
        "right_knee": [x + (back if side > 0 else front) * 0.5, y - 0.12],
        "left_foot": [x + (front if side > 0 else back), y + 0.15],
        "right_foot": [x + (back if side > 0 else front), y - 0.15],
        "left_arm": [x + rng.uniform(-0.3, 0.55) * facing, y + 0.35],
        "right_arm": [x + rng.uniform(-0.3, 0.55) * facing, y - 0.35],
    }


def front(parts: Pose, names: tuple[str, ...] = m.COUNTING_PARTS) -> float:
    return max(parts[n][0] for n in names)


def shift(parts: Pose, dx: float, dy: float = 0.0) -> None:
    for p in parts.values():
        p[0] += dx
        p[1] += dy


def place_front(parts: Pose, target: float) -> None:
    shift(parts, target - front(parts))


def move_torso(parts: Pose, x: float, y: float) -> None:
    shift(parts, x - parts["torso"][0], y - parts["torso"][1])


def capture(frame: Frame, team: str, attacks_right: bool, rng: random.Random) -> tuple[dict[str, Pose], dict[str, PlayerSpot]]:
    """Poses for every player in a frame, in `team`'s attacking frame."""
    poses, info = {}, {}
    for spot in frame.players:
        ax, ay = pitch.to_absolute(spot.x, spot.y, attacks_right)  # absolute -> attacking frame
        poses[spot.player] = pose(ax, ay, 1.0 if spot.team == team else -1.0, rng)
        info[spot.player] = spot
    return poses, info


def freeze(poses: dict[str, Pose], info: dict[str, PlayerSpot], attacks_right: bool) -> tuple[m.Body, ...]:
    return tuple(
        m.Body(pid, s.team, s.shirt, s.role,
               {k: tuple(round(c, 3) for c in pitch.to_absolute(v[0], v[1], attacks_right)) for k, v in poses[pid].items()})
        for pid, s in info.items()
    )
