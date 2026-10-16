"""Law 11, encoded: is the assessed attacker offside, under which clause, and by how much.

Works in the attacking team's frame (attacking towards x = 105), where a larger x is
nearer the opponents' goal line. Clause ids refer to `ruling.laws.clauses`.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..incidents import model as m
from ..sim import pitch

EXEMPT_RESTARTS = frozenset({m.THROW_IN, m.CORNER, m.GOAL_KICK})


@dataclass(frozen=True, slots=True)
class OffsideRuling:
    offside: bool
    clause: str
    reason: str
    margin_m: float | None = None  # attacker's furthest counting part beyond the line (negative = behind)
    attacker_part: str | None = None
    second_last: str | None = None  # player id of the second-last opponent
    line_x: float | None = None  # the offside line in the attacking frame: max(ball, second-last opponent)
    arm_beyond: bool = False  # an arm, which the Law ignores, was beyond the line


def second_last_opponent(situation: m.OffsideSituation) -> tuple[str, float]:
    """The second-last opponent and the attacking-frame x of their part nearest their own goal line."""
    depths = sorted(((b.depth(situation.attacks_right)[1], b.player) for b in situation.opponents()), reverse=True)
    if len(depths) < 2:
        return "", pitch.HALFWAY_X
    x, player = depths[1]
    return player, x


def judge(situation: m.OffsideSituation) -> OffsideRuling:
    if situation.kick in EXEMPT_RESTARTS:
        return OffsideRuling(False, "11.3", "restart_exempt")

    right = situation.attacks_right
    attacker = situation.body(situation.attacker)
    part, front = attacker.depth(right)
    _, arm_front = attacker.depth(right, m.ARM_PARTS)
    ball_x = situation.ball[0] if right else pitch.LENGTH - situation.ball[0]
    second_last, defender_x = second_last_opponent(situation)
    line = max(ball_x, defender_x)
    margin = round(front - line, 3)
    arm_beyond = arm_front > line >= front
    common = dict(margin_m=margin, attacker_part=part, second_last=second_last, line_x=round(line, 3),
                  arm_beyond=arm_beyond)

    if front <= pitch.HALFWAY_X:
        return OffsideRuling(False, "11.1", "own_half", **common)
    if front <= ball_x:
        return OffsideRuling(False, "11.1", "behind_ball", **common)
    if front <= defender_x:
        reason = "arms_ignored" if arm_beyond else "level_or_behind"
        return OffsideRuling(False, "11.1", reason, **common)

    # In an offside position: an offence only on becoming involved.
    if situation.intervening == m.DELIBERATE_PLAY:
        return OffsideRuling(False, "11.2", "deliberate_play_reset", **common)
    if situation.involvement == m.NOT_INVOLVED:
        return OffsideRuling(False, "11.2", "not_involved", **common)
    if situation.intervening in (m.DELIBERATE_SAVE, m.DEFLECTION, m.WOODWORK):
        return OffsideRuling(True, "11.2", "gaining_an_advantage", **common)
    if situation.involvement in m.INTERFERING_WITH_OPPONENT:
        return OffsideRuling(True, "11.2", "interfering_with_an_opponent", **common)
    return OffsideRuling(True, "11.2", "interfering_with_play", **common)
