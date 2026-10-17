"""VAR checks run during a match. Mixed into `MatchEngine`.

Each review records the check and the decision as events, files the incident with its
ground truth, and returns the restart that follows the final decision.
"""

from __future__ import annotations

from ..incidents.offside import GoalPlan, make_incident
from ..laws import var
from . import events as ev
from . import pitch
from .flow import DEAD_TIME, Restart

# Seconds a check takes, by outcome.
REVIEW_TIME = {var.CHECK_COMPLETE: (5, 25), var.VAR_OVERTURN: (60, 150), var.ON_FIELD_REVIEW: (90, 200)}


class VarReviews:
    """Needs the engine's `match`, `sides`, `period`, `_emit` and `_tick`."""

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
