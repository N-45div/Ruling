"""Plan foul, handball and sending-off checks: scenario, facts, on-field call, VAR outcome.

Each planner method takes a moment from the engine (a challenge, a ball striking a
defender's arm, a goal, a foul that may deserve a red card), plants one of the
scenarios below, and returns a `FoulPlan`. The truth always comes from
`laws.fouls.judge` applied to the planted facts. On-field calls carry planted errors at
fixed rates per scenario; borderline scenarios are not clear and obvious, so the
correct VAR outcome is to let the on-field call stand (see docs/eval-plan.md).
"""

from __future__ import annotations

import random
from dataclasses import asdict, dataclass

from ..laws import fouls as law
from ..laws import var
from ..sim import events as ev
from ..sim import pitch
from ..sim.shape import frame_at
from . import model as m
from .bodies import capture, freeze, move_torso

# scenario: (weight, chance the on-field call matches the Law, clear and obvious if wrong)
PENALTY_CLAIMS = {
    "clear_foul_inside": (0.14, 0.85, True),
    "clear_foul_outside": (0.10, 0.90, True),
    "line_contact_inside": (0.07, 0.55, True),
    "line_contact_outside": (0.07, 0.55, True),
    "played_ball_first": (0.16, 0.75, True),
    "attacker_initiated": (0.10, 0.70, True),
    "no_contact_dive": (0.08, 0.85, True),
    "holding": (0.12, 0.55, True),
    "marginal_contact": (0.16, 0.50, False),
}
HANDBALL_CLAIMS = {
    "arm_extended_unjustified": (0.20, 0.60, True),
    "arm_natural_close": (0.20, 0.85, True),
    "off_own_body": (0.12, 0.70, True),
    "supporting_arm": (0.10, 0.75, True),
    "deliberate_reach": (0.08, 0.80, True),
    "above_shoulder_justified": (0.12, 0.60, True),
    "marginal_arm": (0.18, 0.50, False),
}
HANDBALL_GOALS = {
    "scorer_arm_before_goal": (0.45, 0.50, True),
    "team_mate_accidental": (0.55, 0.85, True),
}
RED_CARDS = {
    "sfp_excessive": (0.12, 0.55, True),
    "reckless_not_red": (0.18, 0.85, True),
    "borderline_sfp": (0.10, 0.50, False),
    "violent_conduct_missed": (0.06, 0.30, True),
    "dogso_clear": (0.12, 0.70, True),
    "dogso_covering_defender": (0.14, 0.65, True),
    "dogso_wide_angle": (0.10, 0.75, True),
    "dogso_in_area_attempt": (0.10, 0.60, True),
    "dogso_in_area_holding": (0.08, 0.55, True),
}
_DOGSO = frozenset(s for s in RED_CARDS if s.startswith("dogso"))
_AREA_X = pitch.LENGTH - pitch.PENALTY_AREA_DEPTH
_HALF_AREA = pitch.PENALTY_AREA_WIDTH / 2


@dataclass(frozen=True, slots=True)
class FoulPlan:
    category: str
    scenario: str
    situation: m.FoulSituation
    ruling: law.FoulRuling
    subjective: bool
    clear_and_obvious: bool
    on_field: str
    outcome: var.VarOutcome
    final_card: str  # the card that follows the final decision

    @property
    def point(self) -> tuple[float, float]:
        return self.situation.point


def _challenge(action="trip", contact=True, played_ball_first=False, attempt=True, initiated=False,
               studs=False, lunge=False, off_ground=False, late=0.0, speed=4.0, height="ankle") -> m.Challenge:
    return m.Challenge(action, contact, played_ball_first, attempt, initiated, studs, lunge, off_ground,
                       round(late, 2), round(speed, 2), height if contact else "none")


def _handball(rng, arm=0.1, above=False, moved=False, justified=True, supporting=False, own_body=False,
              distance=None, by_attacker=False, scorer=False, immediately=False, goal_bound=False) -> m.HandballFacts:
    return m.HandballFacts(round(arm, 2), above, moved, justified, supporting, own_body,
                           round(distance if distance is not None else rng.uniform(3, 15), 2),
                           by_attacker, scorer, immediately, goal_bound)


class FoulPlanner:
    def __init__(self, seed: int):
        self.seed = seed

    # ---- public planners -----------------------------------------------------------------

    def penalty_claim(self, match: ev.Match, team: str, victim: str, offender: str,
                      xy: tuple[float, float]) -> FoulPlan:
        rng = self._rng(match, "penalty")
        scenario = _pick(rng, PENALTY_CLAIMS)
        x, y = xy
        if scenario == "clear_foul_outside":
            point = (x if x < _AREA_X - 1 else rng.uniform(_AREA_X - 5.5, _AREA_X - 1.1), _within(y, _HALF_AREA - 1))
        elif scenario == "line_contact_inside":
            point = (_AREA_X + rng.uniform(0.0, 0.3), _within(y, _HALF_AREA - 2))
        elif scenario == "line_contact_outside":
            point = (_AREA_X - rng.uniform(0.05, 0.4), _within(y, _HALF_AREA - 2))
        else:
            point = (pitch.clamp(x, _AREA_X + 1.0, pitch.LENGTH - 2), _within(y, _HALF_AREA - 1))
        late = rng.uniform(0.45, 0.8) if rng.random() < 0.25 else 0.0
        challenge = {
            "played_ball_first": _challenge("tackle", played_ball_first=True),
            "attacker_initiated": _challenge(initiated=True),
            "no_contact_dive": _challenge(contact=False),
            "holding": _challenge("holding", attempt=False, height="upper_body"),
            "marginal_contact": _challenge(played_ball_first=rng.random() < 0.5, height="foot"),
        }.get(scenario, _challenge(rng.choice(("trip", "tackle")), late=late))
        return self._finish(match, m.PENALTY_CLAIM, scenario, PENALTY_CLAIMS[scenario], team, offender, victim,
                            point, challenge, None, None, rng)

    def handball(self, match: ev.Match, team: str, offender: str, xy: tuple[float, float]) -> FoulPlan:
        rng = self._rng(match, "handball")
        scenario = _pick(rng, HANDBALL_CLAIMS)
        point = (pitch.clamp(xy[0], _AREA_X + 1.5, pitch.LENGTH - 2), _within(xy[1], _HALF_AREA - 2))
        facts = {
            "arm_extended_unjustified": lambda: _handball(rng, rng.uniform(0.4, 0.8), justified=False,
                                                          goal_bound=rng.random() < 0.15),
            "arm_natural_close": lambda: _handball(rng, rng.uniform(0.0, 0.2)),
            "off_own_body": lambda: _handball(rng, rng.uniform(0.35, 0.6), justified=False, own_body=True,
                                              distance=rng.uniform(0.3, 1.2)),
            "supporting_arm": lambda: _handball(rng, rng.uniform(0.35, 0.6), justified=False, supporting=True),
            "deliberate_reach": lambda: _handball(rng, rng.uniform(0.3, 0.7), moved=True, justified=False,
                                                  goal_bound=rng.random() < 0.4),
            "above_shoulder_justified": lambda: _handball(rng, rng.uniform(0.3, 0.5), above=True),
            "marginal_arm": lambda: _handball(rng, rng.uniform(0.3, 0.42), justified=rng.random() < 0.5),
        }[scenario]()
        return self._finish(match, m.HANDBALL, scenario, HANDBALL_CLAIMS[scenario], team, offender, None,
                            point, None, facts, None, rng)

    def handball_goal(self, match: ev.Match, team: str, scorer: str, xy: tuple[float, float]) -> FoulPlan:
        rng = self._rng(match, "handball_goal")
        scenario = _pick(rng, HANDBALL_GOALS)
        if scenario == "scorer_arm_before_goal":
            facts = _handball(rng, rng.uniform(0.1, 0.4), by_attacker=True, scorer=True, immediately=True,
                              distance=rng.uniform(0.3, 2.0))
        else:
            facts = _handball(rng, rng.uniform(0.1, 0.4), by_attacker=True)
        return self._finish(match, m.HANDBALL_GOAL, scenario, HANDBALL_GOALS[scenario], team, scorer, None,
                            xy, None, facts, None, rng)

    def red_card(self, match: ev.Match, team: str, victim: str, offender: str, xy: tuple[float, float]) -> FoulPlan:
        rng = self._rng(match, "red")
        near_goal = pitch.distance_to_goal(*xy) <= 32
        options = {k: v for k, v in RED_CARDS.items() if near_goal or k not in _DOGSO}
        scenario = _pick(rng, options)
        point, dogso = xy, None
        if scenario in _DOGSO:
            inside = scenario.startswith("dogso_in_area")
            # Close enough to goal that distance alone never decides it (at most ~24 m).
            px = rng.uniform(_AREA_X + 2, pitch.LENGTH - 5) if inside else rng.uniform(_AREA_X - 6, _AREA_X - 1)
            point = (px, rng.uniform(pitch.CENTRE_Y - 7, pitch.CENTRE_Y + 7))
            wide = scenario == "dogso_wide_angle" and rng.random() < 0.5
            dogso = m.DogsoFacts(
                distance_m=round(pitch.distance_to_goal(*point), 2),
                towards_goal=not wide,
                angle_deg=round(rng.uniform(60, 85) if wide else rng.uniform(0, 30), 1),
                control="unlikely" if scenario == "dogso_wide_angle" and not wide else "likely",
                defenders_able=rng.choice((1, 2)) if scenario == "dogso_covering_defender" else 0,
                attackers_support=rng.choice((0, 1, 2)),
            )
        reckless_late = rng.uniform(0.45, 0.8) if rng.random() < 0.4 else 0.0
        challenge = {
            "sfp_excessive": _challenge("tackle", studs=True, lunge=True, off_ground=rng.random() < 0.4,
                                        speed=rng.uniform(6.5, 9.0), height=rng.choice(("shin", "knee"))),
            "reckless_not_red": _challenge("tackle", late=rng.uniform(0.5, 0.9), speed=rng.uniform(4.0, 6.0)),
            "borderline_sfp": _challenge("tackle", studs=True, speed=rng.uniform(5.0, 7.0), height="shin"),
            "violent_conduct_missed": _challenge("strike", attempt=False, height="head"),
            "dogso_in_area_holding": _challenge("holding", attempt=False, height="upper_body"),
            "dogso_covering_defender": _challenge(late=reckless_late),
            "dogso_wide_angle": _challenge(late=reckless_late),
        }.get(scenario, _challenge())
        return self._finish(match, m.RED_CARD, scenario, RED_CARDS[scenario], team, offender, victim,
                            point, challenge, None, dogso, rng)

    # ---- shared ----------------------------------------------------------------------------

    def _rng(self, match: ev.Match, kind: str) -> random.Random:
        return random.Random(f"{kind}:{self.seed}:{len(match.events)}")

    def _finish(self, match, category, scenario, spec, team, offender, victim, point, challenge, handball,
                dogso, rng) -> FoulPlan:
        _, correct_rate, clear = spec
        right = match.attacks_right(team, match.events[-1].period if match.events else 1)
        situation = m.FoulSituation(
            category, team, right, offender, victim,
            tuple(round(c, 3) for c in pitch.to_absolute(*point, right)),
            challenge, handball, dogso, self._bodies(match, team, right, offender, victim, point, handball, rng),
        )
        ruling = law.judge(situation)
        truth = ruling.decision
        if not clear:
            on_field = rng.choice(_plausible(category))
        elif rng.random() < correct_rate:
            on_field = truth
        else:
            on_field = _wrong(category, scenario, truth, rng)
        reviewable = _reviewable(category, on_field, truth)
        subjective = _subjective(category, scenario, on_field, truth)
        outcome = var.review(on_field, truth, subjective, clear, reviewable=reviewable)
        final_card = ruling.card if outcome.final in (law.PENALTY, law.FREE_KICK) else law.NO_CARD
        if category == m.RED_CARD:
            final_card = outcome.final
        return FoulPlan(category, scenario, situation, ruling, subjective, clear, on_field, outcome, final_card)

    @staticmethod
    def _bodies(match, team, right, offender, victim, point, handball, rng) -> tuple[m.Body, ...]:
        if not match.events:
            return ()
        poses, info = capture(frame_at(match, len(match.events) - 1), team, right, rng)
        x, y = point
        if victim in poses:
            move_torso(poses[victim], x + 0.3, y)
        if offender in poses:
            if handball:  # the touching arm is at the point, the torso an arm's length away
                side = 1 if y < pitch.CENTRE_Y else -1
                arm = "left_arm" if side > 0 else "right_arm"
                move_torso(poses[offender], x + 0.2, y - side * (0.25 + handball.arm_away_m))
                poses[offender][arm] = [x, y]
            else:
                move_torso(poses[offender], x - 0.45, y + rng.uniform(-0.3, 0.3))
        return freeze(poses, info, right)


def make_foul_incident(match: ev.Match, plan: FoulPlan, event_index: int) -> m.Incident:
    event = match.events[event_index]
    return m.Incident(
        id=f"{match.id}:{event_index}:{plan.category}", match_id=match.id, category=plan.category,
        scenario=plan.scenario, period=event.period, second=event.second, team=plan.situation.attacking_team,
        event_index=event_index, key_index=event_index, subjective=plan.subjective,
        clear_and_obvious=plan.clear_and_obvious, on_field=plan.on_field, law_decision=plan.ruling.decision,
        var_review=plan.outcome.review, final=plan.outcome.final, announced=plan.outcome.announced,
        situation=plan.situation, ruling=asdict(plan.ruling),
    )


def _pick(rng: random.Random, table: dict) -> str:
    names = list(table)
    return rng.choices(names, weights=[table[n][0] for n in names])[0]


def _within(y: float, half_width: float) -> float:
    return pitch.clamp(y, pitch.CENTRE_Y - half_width, pitch.CENTRE_Y + half_width)


def _plausible(category: str) -> tuple[str, ...]:
    return {
        m.PENALTY_CLAIM: (law.PENALTY, law.NO_FOUL),
        m.HANDBALL: (law.PENALTY, law.NO_FOUL),
        m.HANDBALL_GOAL: (law.GOAL, law.NO_GOAL),
        m.RED_CARD: (law.RED, law.YELLOW),
    }[category]


def _wrong(category: str, scenario: str, truth: str, rng: random.Random) -> str:
    if category == m.PENALTY_CLAIM:
        if truth == law.PENALTY:
            return law.FREE_KICK if scenario == "line_contact_inside" else law.NO_FOUL
        if truth == law.FREE_KICK:
            return law.PENALTY if scenario == "line_contact_outside" or rng.random() < 0.5 else law.NO_FOUL
        return law.PENALTY
    if category == m.HANDBALL:
        return law.NO_FOUL if truth == law.PENALTY else law.PENALTY
    if category == m.HANDBALL_GOAL:
        return law.GOAL if truth == law.NO_GOAL else law.NO_GOAL
    if truth == law.RED:
        return law.NO_CARD if scenario == "violent_conduct_missed" else law.YELLOW
    return law.RED


def _reviewable(category: str, on_field: str, truth: str) -> bool:
    if category in (m.PENALTY_CLAIM, m.HANDBALL):
        return law.PENALTY in (on_field, truth)
    if category == m.RED_CARD:
        return law.RED in (on_field, truth)
    return True


def _subjective(category: str, scenario: str, on_field: str, truth: str) -> bool:
    if category == m.HANDBALL_GOAL:
        return False  # an accidental touch by the scorer is a factual matter
    if category == m.PENALTY_CLAIM:
        if {on_field, truth} == {law.PENALTY, law.FREE_KICK}:
            return False  # only the location is in question: inside or outside the area
        return not scenario.startswith("line_contact")
    return True

