"""VAR checks run during a match. Mixed into `MatchEngine`.

Each review records the check and the decision as events, files the incident with its
ground truth, and returns the restart that follows the final decision.
"""

from __future__ import annotations

from ..incidents import model as m
from ..incidents.fouls import FoulPlan, make_foul_incident
from ..incidents.offside import GoalPlan, make_incident
from ..laws import fouls as law
from ..laws import var
from . import events as ev
from . import pitch
from .flow import DEAD_TIME, REGAIN, Restart

# Seconds a check takes, by outcome.
REVIEW_TIME = {var.CHECK_COMPLETE: (5, 25), var.VAR_OVERTURN: (60, 150), var.ON_FIELD_REVIEW: (90, 200)}


class VarReviews:
    """Needs the engine's `match`, `sides`, `period`, `fouls`, `_emit`, `_tick` and `_card`."""

    # ---- fouls -------------------------------------------------------------------------

    def _plan_point(self, team: int, plan: FoulPlan) -> tuple[float, float]:
        """The plan's point in `team`'s attacking frame."""
        return pitch.to_absolute(*plan.point, self.sides[team].attacks_right(self.period))

    def _penalty_claim(self, team: int, carrier, defender, x: float, y: float) -> Restart:
        plan = self.fouls.penalty_claim(self.match, self.sides[team].club.code, carrier.id, defender.id, (x, y))
        point = self._plan_point(team, plan)
        if plan.on_field in (law.PENALTY, law.FREE_KICK):
            self._emit(1 - team, defender, ev.FOUL, ev.FAIL, pitch.flip(*point),
                       detail=plan.situation.challenge.action, receiver=carrier.id)
        else:
            self._emit(1 - team, defender, ev.TACKLE, ev.SUCCESS, pitch.flip(*point), detail="penalty_claim")
        return self._review_foul(team, plan, defender, point)

    def _red_check(self, team: int, carrier, defender, x: float, y: float) -> Restart:
        plan = self.fouls.red_card(self.match, self.sides[team].club.code, carrier.id, defender.id, (x, y))
        point = self._plan_point(team, plan)
        self._emit(1 - team, defender, ev.FOUL, ev.FAIL, pitch.flip(*point),
                   detail=plan.situation.challenge.action, receiver=carrier.id)
        return self._review_foul(team, plan, defender, point)

    def _handball_claim(self, team: int, defender, x: float, y: float, otherwise: Restart) -> Restart:
        """The ball struck `defender` in their area; `otherwise` is the restart if there was no offence."""
        plan = self.fouls.handball(self.match, self.sides[team].club.code, defender.id, (x, y))
        point = self._plan_point(team, plan)
        if plan.on_field == law.PENALTY:
            self._emit(1 - team, defender, ev.FOUL, ev.FAIL, pitch.flip(*point), detail="handball")
        return self._review_foul(team, plan, defender, point, otherwise)

    def _review_foul(self, team: int, plan: FoulPlan, offender, point: tuple[float, float],
                     otherwise: Restart | None = None) -> Restart:
        index = len(self.match.events) - 1
        self._tick(*REVIEW_TIME[plan.outcome.review])
        self._emit(team, None, ev.VAR_CHECK, ev.SUCCESS, point, detail=plan.category)
        self._emit(team, None, ev.VAR_DECISION, plan.outcome.final, point,
                   detail=f"{plan.outcome.review}|event:{index}")
        self.match.incidents.append(make_foul_incident(self.match, plan, index))
        if plan.final_card in (law.RED, law.YELLOW) and offender in self.sides[1 - team].on_pitch:
            colour = ev.RED if plan.final_card == law.RED else ev.YELLOW
            self._card(1 - team, offender, colour, plan.ruling.card_reason or "reckless", *point)
        final = plan.outcome.final
        if plan.category == m.RED_CARD:  # the foul stands; only the card was in question
            final = law.PENALTY if plan.ruling.inside_area else law.FREE_KICK
        if final == law.PENALTY:
            self._tick(*DEAD_TIME[ev.PENALTY])
            spot = pitch.LENGTH - pitch.PENALTY_SPOT_DISTANCE
            return Restart(ev.PENALTY, team, spot, pitch.CENTRE_Y, detail=plan.category)
        if final == law.FREE_KICK:
            self._tick(*DEAD_TIME[ev.FREE_KICK])
            return Restart(ev.FREE_KICK, team, *point, detail=plan.category)
        if otherwise is not None:
            return otherwise
        if plan.on_field in (law.PENALTY, law.FREE_KICK):  # a foul given on the field was rescinded
            self._tick(*DEAD_TIME[ev.FREE_KICK])
            return Restart(ev.DROPPED_BALL, 1 - team, *pitch.flip(*point))
        return Restart(REGAIN, 1 - team, *pitch.flip(*point))

    def _review_handball_goal(self, team: int, scorer, plan: FoulPlan) -> Restart:
        """The goal just recorded may follow an attacker's handball."""
        shot_index = len(self.match.events) - 1
        point = self._plan_point(team, plan)
        if plan.on_field == law.NO_GOAL:
            self._emit(team, scorer, ev.FOUL, ev.FAIL, point, detail="handball")
        self._tick(*REVIEW_TIME[plan.outcome.review])
        self._emit(team, None, ev.VAR_CHECK, ev.SUCCESS, point, detail=plan.category)
        self._emit(team, None, ev.VAR_DECISION, plan.outcome.final, point,
                   detail=f"{plan.outcome.review}|shot:{shot_index}")
        self.match.incidents.append(make_foul_incident(self.match, plan, shot_index))
        if plan.outcome.final == law.GOAL:
            self._tick(*DEAD_TIME[ev.KICKOFF])
            return Restart(ev.KICKOFF, 1 - team, pitch.HALFWAY_X, pitch.CENTRE_Y)
        self._tick(*DEAD_TIME[ev.FREE_KICK])
        return Restart(ev.FREE_KICK, 1 - team, *pitch.flip(*point), detail="handball")

    # ---- goals -------------------------------------------------------------------------

    def _review_goal(self, team: int, plan: GoalPlan) -> Restart:
        """Flag (if given), VAR check and decision for the goal just recorded, then the right restart."""
        shot_index = len(self.match.events) - 1
        side = self.sides[team]
        assessed = side.club.player(plan.situation.attacker)
        offence = pitch.to_absolute(*plan.offence_point, side.attacks_right(self.period))  # into team's frame
        if plan.on_field == var.NO_GOAL:
            self._emit(team, assessed, ev.OFFSIDE, ev.FAIL, offence, detail="flag")
        self._tick(*REVIEW_TIME[plan.outcome.review])
        self._emit(team, assessed, ev.VAR_CHECK, ev.SUCCESS, offence, detail="offside")
        result = ev.GOAL if plan.outcome.final == var.GOAL else ev.NO_GOAL
        self._emit(team, None, ev.VAR_DECISION, result, offence, detail=f"{plan.outcome.review}|shot:{shot_index}")
        self.match.incidents.append(make_incident(self.match, plan, shot_index))
        if plan.outcome.final == var.GOAL:
            self._tick(*DEAD_TIME[ev.KICKOFF])
            return Restart(ev.KICKOFF, 1 - team, pitch.HALFWAY_X, pitch.CENTRE_Y)
        self._tick(*DEAD_TIME[ev.FREE_KICK])
        return Restart(ev.FREE_KICK, 1 - team, *pitch.flip(*offence), detail="offside")
