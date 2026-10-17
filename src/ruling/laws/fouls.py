"""Law 12 and Law 14, encoded: was it a foul, where, how serious, and what follows.

Each judge returns a `FoulRuling` whose `decision` is the reviewable decision for its
incident category:
- penalty claim: penalty | free_kick (offence outside the area) | no_foul
- handball (defender): penalty | no_foul
- handball before a goal (attacker): goal | no_goal
- red card: red | yellow | no_card

Where the Laws leave room for judgement (force, an arm making the body unnaturally
bigger), the rules below turn tracking cues into a decision. The handball cues follow the
league's published guidance (justifiable position, supporting arm, ball off own body,
close proximity); they are heuristics on top of the Law, and reasons say so.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..incidents import model as m
from ..sim import pitch

CARELESS, RECKLESS, EXCESSIVE, NO_FORCE = "careless", "reckless", "excessive", "none"
PENALTY, FREE_KICK, NO_FOUL = "penalty", "free_kick", "no_foul"
GOAL, NO_GOAL = "goal", "no_goal"
RED, YELLOW, NO_CARD = "red", "yellow", "no_card"

_HIGH_CONTACT = frozenset({"shin", "knee", "thigh", "upper_body", "head"})


@dataclass(frozen=True, slots=True)
class FoulRuling:
    decision: str
    clause: str
    reason: str
    card: str = NO_CARD
    card_reason: str | None = None
    force: str | None = None
    inside_area: bool | None = None
    area_margin_m: float | None = None  # signed distance of the point from the area line: + inside, - outside
    dogso: bool | None = None


def area_margin(x: float, y: float) -> float:
    """Signed distance (attacking frame) from the penalty area being attacked: + inside, - outside.

    The line belongs to the area, so a point exactly on it has margin 0 and is inside.
    """
    dx = x - (pitch.LENGTH - pitch.PENALTY_AREA_DEPTH)
    dy = pitch.PENALTY_AREA_WIDTH / 2 - abs(y - pitch.CENTRE_Y)
    if dx >= 0 and dy >= 0:
        return round(min(dx, dy), 3)
    return round(-((max(0.0, -dx)) ** 2 + (max(0.0, -dy)) ** 2) ** 0.5, 3)


def force(ch: m.Challenge) -> str:
    if not ch.contact:
        return NO_FORCE
    if ch.action == "strike":
        return EXCESSIVE
    high = ch.contact_height in _HIGH_CONTACT
    if ch.studs_up and high and (ch.lunge or ch.off_ground or ch.speed_mps >= 6.0):
        return EXCESSIVE
    if ch.studs_up or ch.lunge or ch.off_ground or ch.late_s >= 0.4:
        return RECKLESS
    return CARELESS


def is_foul(ch: m.Challenge) -> tuple[bool, str]:
    if not ch.contact:
        return False, "no_contact"
    if ch.attacker_initiated:
        return False, "attacker_initiated_contact"
    if ch.action in ("holding", "push", "strike"):
        return True, ch.action
    if ch.played_ball_first and force(ch) == CARELESS:
        return False, "played_the_ball_first"
    return True, ch.action


def is_dogso(d: m.DogsoFacts) -> bool:
    return d.towards_goal and d.distance_m <= 25.0 and d.control == "likely" and d.defenders_able == 0


def _point(s: m.FoulSituation) -> tuple[float, float]:
    return pitch.to_absolute(*s.point, s.attacks_right)  # absolute -> attacking frame


def _sanction(s: m.FoulSituation, inside: bool) -> tuple[str, str | None, bool | None]:
    ch = s.challenge
    level = force(ch)
    if level == EXCESSIVE:
        return RED, ("violent_conduct" if ch.action == "strike" else "serious_foul_play"), None
    if s.dogso and is_dogso(s.dogso):
        if inside and ch.attempt_to_play_ball and ch.action not in ("holding", "push"):
            return YELLOW, "dogso_downgraded_attempt_to_play_ball", True
        return RED, "dogso", True
    if level == RECKLESS:
        return YELLOW, "reckless", False if s.dogso else None
    return NO_CARD, None, False if s.dogso else None


def judge_penalty_claim(s: m.FoulSituation) -> FoulRuling:
    margin = area_margin(*_point(s))
    inside = margin >= 0
    foul, reason = is_foul(s.challenge)
    if not foul:
        return FoulRuling(NO_FOUL, "12.1", reason, force=force(s.challenge), inside_area=inside, area_margin_m=margin)
    card, card_reason, dogso = _sanction(s, inside)
    decision, clause = (PENALTY, "14") if inside else (FREE_KICK, "12.1")
    return FoulRuling(decision, clause, reason, card, card_reason, force(s.challenge), inside, margin, dogso)


def handball_offence(h: m.HandballFacts) -> tuple[bool, str]:
    if h.by_attacker:
        if h.scorer and h.immediately_before_goal:
            return True, "scorer_touched_immediately_before_goal"
        if h.moved_towards_ball:
            return True, "deliberate"
        return False, "accidental_touch_then_team_mate_scored"
    if h.moved_towards_ball:
        return True, "deliberate"
    if h.supporting_arm:
        return False, "supporting_arm"
    if h.off_own_body and h.distance_m < 1.5:
        return False, "ball_off_own_body_at_close_range"
    if h.arm_away_m >= 0.35 and not h.justified_by_movement:
        return True, "arm_made_body_unnaturally_bigger"
    return False, "arm_in_a_justifiable_position"


def judge_handball(s: m.FoulSituation) -> FoulRuling:
    h = s.handball
    offence, reason = handball_offence(h)
    if h.by_attacker:
        return FoulRuling(NO_GOAL if offence else GOAL, "12.1-handball", reason)
    margin = area_margin(*_point(s))
    if not offence:
        return FoulRuling(NO_FOUL, "12.1-handball", reason, inside_area=margin >= 0, area_margin_m=margin)
    card, card_reason = NO_CARD, None
    if h.goal_bound:
        deliberate = reason == "deliberate"
        card = RED if deliberate else YELLOW
        card_reason = "dogso_deliberate_handball" if deliberate else "dogso_handball_penalty_awarded"
    decision = PENALTY if margin >= 0 else FREE_KICK
    return FoulRuling(decision, "12.1-handball", reason, card, card_reason, inside_area=margin >= 0, area_margin_m=margin)


def judge_red_card(s: m.FoulSituation) -> FoulRuling:
    margin = area_margin(*_point(s))
    inside = margin >= 0
    foul, reason = is_foul(s.challenge)
    if not foul:
        return FoulRuling(NO_CARD, "12.1", reason, force=force(s.challenge), inside_area=inside, area_margin_m=margin)
    card, card_reason, dogso = _sanction(s, inside)
    clause = {"serious_foul_play": "12.3-sfp", "violent_conduct": "12.3-vc", "dogso": "12.3-dogso",
              "dogso_downgraded_attempt_to_play_ball": "12.3-dogso"}.get(card_reason, "12.1")
    return FoulRuling(card, clause, reason, card, card_reason, force(s.challenge), inside, margin, dogso)


def judge(s: m.FoulSituation) -> FoulRuling:
    if s.kind == m.PENALTY_CLAIM:
        return judge_penalty_claim(s)
    if s.kind in (m.HANDBALL, m.HANDBALL_GOAL):
        return judge_handball(s)
    if s.kind == m.RED_CARD:
        return judge_red_card(s)
    raise ValueError(f"not a foul category: {s.kind}")
