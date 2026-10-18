"""The VAR protocol, encoded: what happens to an on-field decision after review.

- Factual decisions (e.g. offside position) are corrected by the VAR alone.
- Subjective decisions (e.g. whether an offside player interfered with an opponent) go
  to an on-field review, and only when the on-field call was a clear and obvious error.
- The referee announces the outcome of every review in the stadium, except a factual
  offside or onside decision (Premier League practice since 2025/26).
"""

from __future__ import annotations

from dataclasses import dataclass

GOAL, NO_GOAL = "goal", "no_goal"
CHECK_COMPLETE = "check_complete"  # no intervention: the on-field decision stands
VAR_OVERTURN = "var_overturn"  # factual correction by the VAR alone
ON_FIELD_REVIEW = "on_field_review"  # the referee reviews at the monitor and changes the decision


PENALTY, FREE_KICK, RED = "penalty", "free_kick", "red"
# Offside rulings that turn on a judgement of involvement rather than on position.
SUBJECTIVE_OFFSIDE = frozenset({"interfering_with_an_opponent", "not_involved", "deliberate_play_reset",
                                "gaining_an_advantage"})


@dataclass(frozen=True, slots=True)
class Classification:
    subjective: bool  # needs the referee's judgement at the monitor
    reviewable: bool  # at least one of the two calls falls in the VAR's scope
    factual_offside: bool  # a factual offside or onside decision (no stadium announcement)


def classify(category: str, on_field: str, law_decision: str, reason: str) -> Classification:
    """How the protocol treats a disagreement between the on-field call and the Law."""
    if category == "offside":
        subjective = reason in SUBJECTIVE_OFFSIDE
        return Classification(subjective, True, not subjective)
    if category == "handball":
        return Classification(True, PENALTY in (on_field, law_decision), False)
    if category == "penalty_claim":
        location_only = {on_field, law_decision} == {PENALTY, FREE_KICK}  # inside or outside the area
        return Classification(not location_only, PENALTY in (on_field, law_decision), False)
    if category == "handball_goal":
        return Classification(False, True, False)  # an accidental touch by the scorer is a factual matter
    if category == "red_card":
        return Classification(True, RED in (on_field, law_decision), False)
    raise ValueError(f"unknown category: {category}")


@dataclass(frozen=True, slots=True)
class VarOutcome:
    review: str
    final: str
    changed: bool
    announced: bool


def review(on_field: str, law_decision: str, subjective: bool, clear_and_obvious: bool = True,
           factual_offside: bool = False, reviewable: bool = True) -> VarOutcome:
    """The correct VAR outcome for an on-field call, given what the Law says.

    `clear_and_obvious` matters only for subjective calls: if the on-field call was
    wrong but not clearly so, the VAR does not intervene and the call stands.
    `reviewable` is False when neither call falls in the VAR's scope, e.g. a caution
    given instead of no card, or a free kick outside the area instead of no foul.
    """
    if on_field == law_decision or not reviewable or (subjective and not clear_and_obvious):
        return VarOutcome(CHECK_COMPLETE, on_field, changed=False, announced=False)
    if subjective:
        return VarOutcome(ON_FIELD_REVIEW, law_decision, changed=True, announced=True)
    return VarOutcome(VAR_OVERTURN, law_decision, changed=True, announced=not factual_offside)
