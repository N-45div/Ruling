"""Pitch geometry.

Coordinates are metres on a 105 x 68 m pitch. Absolute coordinates use the broadcast
view: x runs from the left goal line (0) to the right goal line (105), y from the near
touchline (0) to the far touchline (68).

The engine also works in an *attacking frame*, where the team in possession always
attacks towards x = 105. `to_absolute` maps a point from a team's attacking frame to
absolute coordinates.
"""

from __future__ import annotations

import math

LENGTH = 105.0
WIDTH = 68.0
HALFWAY_X = LENGTH / 2
CENTRE_Y = WIDTH / 2

GOAL_WIDTH = 7.32
PENALTY_AREA_DEPTH = 16.5
PENALTY_AREA_WIDTH = 40.32
GOAL_AREA_DEPTH = 5.5
GOAL_AREA_WIDTH = 18.32
PENALTY_SPOT_DISTANCE = 11.0


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def clamp_to_pitch(x: float, y: float) -> tuple[float, float]:
    return clamp(x, 0.0, LENGTH), clamp(y, 0.0, WIDTH)


def to_absolute(x: float, y: float, attacks_right: bool) -> tuple[float, float]:
    """Map a point from a team's attacking frame to absolute coordinates."""
    if attacks_right:
        return x, y
    return LENGTH - x, WIDTH - y


def flip(x: float, y: float) -> tuple[float, float]:
    """Map a point from one team's attacking frame to the opponent's."""
    return LENGTH - x, WIDTH - y


def distance_to_goal(x: float, y: float) -> float:
    """Distance from a point (attacking frame) to the centre of the goal being attacked."""
    return math.hypot(LENGTH - x, CENTRE_Y - y)


def goal_angle(x: float, y: float) -> float:
    """Angle in radians subtended by the goal mouth from a point (attacking frame)."""
    left_post = CENTRE_Y - GOAL_WIDTH / 2
    right_post = CENTRE_Y + GOAL_WIDTH / 2
    dx = LENGTH - x
    if dx <= 0:
        return 0.0
    return abs(math.atan2(right_post - y, dx) - math.atan2(left_post - y, dx))


def in_penalty_area(x: float, y: float) -> bool:
    """True if a point (attacking frame) is in the penalty area being attacked.

    The lines belong to the area they enclose, so a point on the line is inside.
    """
    half_width = PENALTY_AREA_WIDTH / 2
    return x >= LENGTH - PENALTY_AREA_DEPTH and abs(y - CENTRE_Y) <= half_width


def in_own_half(x: float) -> bool:
    """True if a point (attacking frame) is in the attacking team's own half.

    The halfway line counts as the own half, as in Law 11.
    """
    return x <= HALFWAY_X


def third(x: float) -> int:
    """0 for the defensive third, 1 for the middle third, 2 for the attacking third."""
    return min(2, int(x // (LENGTH / 3)))
