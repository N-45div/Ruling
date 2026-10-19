"""Plan the offside question behind a goal: scenario, body geometry, on-field call, VAR outcome.

For each goal the planner finds the team-mate's pass the decision turns on, rebuilds
every player's body at that instant, and places the relevant attacker to plant one of
the scenarios below. The truth always comes from `laws.offside.judge` applied to the
geometry, never from the scenario label. The on-field call carries planted errors at
fixed rates per scenario (see docs/eval-plan.md).
"""

from __future__ import annotations

import math
import random
from dataclasses import asdict, dataclass

from ..laws import var
from ..laws.offside import OffsideRuling, judge
from ..sim import events as ev
from ..sim import pitch
from ..sim.clubs import ROLE_FWD, ROLE_GK, ROLE_MID
from ..sim.shape import frame_at
from . import model as m
from .bodies import capture, freeze, front, place_front, shift

# scenario: (weight, chance the on-field call matches the Law)
SCENARIOS: dict[str, tuple[float, float]] = {
    "clear_onside": (0.62, 0.99),
    "tight_onside": (0.10, 0.70),
    "tight_offside": (0.035, 0.40),
    "clear_offside": (0.01, 0.95),
    "arm_beyond": (0.05, 0.75),
    "teammate_blocks_view": (0.015, 0.55),
    "teammate_marginal_view": (0.02, 0.50),
    "teammate_not_involved": (0.05, 0.85),
    "deliberate_play_reset": (0.03, 0.70),
    "deflection_offside": (0.01, 0.50),
}
RESTART_EXEMPT_CORRECT = 0.97
_KICKS = {ev.THROW_IN: m.THROW_IN, ev.CORNER: m.CORNER, ev.GOAL_KICK: m.GOAL_KICK}


@dataclass(frozen=True, slots=True)
class GoalPlan:
    scenario: str
    key_index: int
    situation: m.OffsideSituation
    ruling: OffsideRuling
    subjective: bool
    clear_and_obvious: bool
    on_field: str
    outcome: var.VarOutcome
    pre_touch: tuple[str, str, tuple[float, float]] | None  # (defender id, detail, absolute position)
    offence_point: tuple[float, float]  # absolute; where an indirect free kick would be taken


def key_pass_index(events: list[ev.Event], team: str, shooter: str) -> int | None:
    """The team-mate's pass or cross the shooter received in this possession, if any."""
    for i in range(len(events) - 1, -1, -1):
        e = events[i]
        if e.team != team or e.type in ev.RESTARTS:
            return None
        if e.type in (ev.PASS, ev.CROSS) and e.result == ev.SUCCESS and e.receiver == shooter:
            return i
    return None


class OffsidePlanner:
    def __init__(self, seed: int):
        self.seed = seed

    def plan(self, match: ev.Match, team: str, shooter: str, shot_xy: tuple[float, float]) -> GoalPlan | None:
        """shot_xy is the shot location in the attacking frame. Returns None if no team-mate's pass is involved."""
        key = key_pass_index(match.events, team, shooter)
        if key is None:
            return None
        rng = random.Random(f"offside:{self.seed}:{key}")
        key_event = match.events[key]
        right = match.attacks_right(team, key_event.period)
        prev = match.events[key - 1] if key else None
        kick = _KICKS.get(prev.type, m.OPEN_PLAY) if prev and prev.player == key_event.player else m.OPEN_PLAY

        poses, info = capture(frame_at(match, key), team, right, rng)
        ball_x = pitch.to_absolute(key_event.start_x, key_event.start_y, right)[0]
        defenders = [p for p, s in info.items() if s.team != team]
        line_d = sorted((front(poses[p]) for p in defenders), reverse=True)[1]
        line = max(line_d, ball_x)

        scenario = self._choose(rng, kick, ball_x, line_d)
        if scenario.startswith("teammate") and shot_xy[0] > line + 5:
            # Interference with the goalkeeper only makes sense when the shot comes from near the line.
            scenario = "clear_onside"
        assessed, involvement, intervening = shooter, m.PLAYED_BALL, None
        # Keep everyone else in the attacking team onside so only the planted question is open.
        for pid, s in info.items():
            if s.team == team and pid not in (shooter, key_event.player) and front(poses[pid]) > line - 0.1:
                place_front(poses[pid], line - rng.uniform(0.3, 3.0))

        scorer = poses[shooter]
        if scenario == "clear_onside":
            place_front(scorer, min(front(scorer), line - rng.uniform(1.0, 6.0)))
        elif scenario == "tight_onside":
            place_front(scorer, line - rng.choice((0.0, rng.uniform(0.01, 0.25))))
        elif scenario == "tight_offside":
            place_front(scorer, line + rng.uniform(0.02, 0.25))
        elif scenario in ("clear_offside", "deliberate_play_reset", "deflection_offside", "restart_exempt"):
            place_front(scorer, line + rng.uniform(0.6, 2.5))
            if scenario == "deliberate_play_reset":
                intervening = m.DELIBERATE_PLAY
            elif scenario == "deflection_offside":
                intervening = m.DEFLECTION
        elif scenario == "arm_beyond":
            place_front(scorer, line - rng.uniform(0.02, 0.15))
            arm = max(("left_arm", "right_arm"), key=lambda n: scorer[n][0])
            scorer[arm][0] = line + rng.uniform(0.05, 0.35)
        else:  # a team-mate in an offside position near or away from the goalkeeper's line of vision
            place_front(scorer, line - rng.uniform(0.3, 2.0))
            assessed = self._teammate(info, team, (shooter, key_event.player), rng)
            mate = poses[assessed]
            # Beyond the offside line at the pass, and between the shot and the goal when it is struck.
            target = max(line + rng.uniform(0.6, 2.0), shot_xy[0] + rng.uniform(1.0, 3.0))
            place_front(mate, min(target, pitch.LENGTH - 0.5))
            sight_y, cos_angle = _sight_line(shot_xy, mate["torso"][0])
            # Distance from the line of sight, measured perpendicular to it.
            offset = {"teammate_blocks_view": rng.uniform(-0.5, 0.5),
                      "teammate_marginal_view": rng.choice((-1, 1)) * rng.uniform(1.8, 3.0),
                      "teammate_not_involved": rng.choice((-1, 1)) * rng.uniform(10.0, 16.0)}[scenario]
            shift(mate, 0.0, pitch.clamp(sight_y + offset / cos_angle, 1.0, pitch.WIDTH - 1.0) - mate["torso"][1])
            involvement = {"teammate_blocks_view": m.LINE_OF_VISION,
                           "teammate_marginal_view": rng.choice((m.LINE_OF_VISION, m.NOT_INVOLVED)),
                           "teammate_not_involved": m.NOT_INVOLVED}[scenario]

        bodies = freeze(poses, info, right)
        ball_abs = (key_event.start_x, key_event.start_y)
        situation = m.OffsideSituation(team, right, ball_abs, kick, key_event.player, assessed,
                                       involvement, intervening, bodies)
        ruling = judge(situation)
        law_decision = var.NO_GOAL if ruling.offside else var.GOAL
        clear = scenario != "teammate_marginal_view"
        correct_rate = RESTART_EXEMPT_CORRECT if scenario == "restart_exempt" else SCENARIOS[scenario][1]
        if not clear:
            on_field = rng.choice((var.GOAL, var.NO_GOAL))
        elif rng.random() < correct_rate:
            on_field = law_decision
        else:
            on_field = var.GOAL if law_decision == var.NO_GOAL else var.NO_GOAL
        kind = var.classify(m.OFFSIDE, on_field, law_decision, ruling.reason)
        subjective = kind.subjective
        outcome = var.review(on_field, law_decision, subjective, clear, factual_offside=kind.factual_offside)

        pre_touch = None
        if intervening:
            toucher = min(defenders, key=lambda p: _distance(poses[p]["torso"], scorer["torso"]))
            touch_xy = pitch.to_absolute(*poses[toucher]["torso"], right)
            pre_touch = (toucher, intervening, touch_xy)
        offence = situation.body(assessed).torso
        return GoalPlan(scenario, key, situation, ruling, subjective, clear, on_field, outcome, pre_touch, offence)

    @staticmethod
    def _choose(rng: random.Random, kick: str, ball_x: float, line_d: float) -> str:
        if kick != m.OPEN_PLAY:
            return "restart_exempt" if rng.random() < 0.5 else "clear_onside"
        if ball_x >= line_d - 0.5:  # a pass from level with or beyond the line: nobody can be offside
            return "clear_onside"
        names = list(SCENARIOS)
        return rng.choices(names, weights=[SCENARIOS[n][0] for n in names])[0]

    @staticmethod
    def _teammate(info: dict, team: str, exclude: tuple[str, ...], rng: random.Random) -> str:
        pool = [p for p, s in info.items() if s.team == team and p not in exclude and s.role in (ROLE_FWD, ROLE_MID)]
        pool = pool or [p for p, s in info.items() if s.team == team and p not in exclude and s.role != ROLE_GK]
        return rng.choice(pool)


def _sight_line(shot_xy: tuple[float, float], x: float) -> tuple[float, float]:
    """y of the line from the shot to the centre of the goal at x (attacking frame), and the
    cosine of that line's angle to the goal line's normal (to turn perpendicular offsets into y)."""
    sx, sy = shot_xy
    dx, dy = pitch.LENGTH - sx, pitch.CENTRE_Y - sy
    if dx < 1e-6:
        return pitch.CENTRE_Y, 1.0
    t = pitch.clamp((x - sx) / dx, 0.0, 1.0)
    return sy + dy * t, max(0.2, dx / math.hypot(dx, dy))


def _distance(a, b) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def make_incident(match: ev.Match, plan: GoalPlan, shot_index: int) -> m.Incident:
    shot = match.events[shot_index]
    return m.Incident(
        id=f"{match.id}:{shot_index}:offside", match_id=match.id, category="offside", scenario=plan.scenario,
        period=shot.period, second=shot.second, team=plan.situation.attacking_team, event_index=shot_index,
        key_index=plan.key_index, subjective=plan.subjective, clear_and_obvious=plan.clear_and_obvious,
        on_field=plan.on_field, law_decision=var.NO_GOAL if plan.ruling.offside else var.GOAL,
        var_review=plan.outcome.review, final=plan.outcome.final, announced=plan.outcome.announced,
        situation=plan.situation, ruling=asdict(plan.ruling),
    )
