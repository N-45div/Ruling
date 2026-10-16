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


@dataclass(frozen=True, slots=True)
class VarOutcome:
    review: str
    final: str
    changed: bool
    announced: bool


def review(on_field: str, law_decision: str, subjective: bool, clear_and_obvious: bool = True,
           factual_offside: bool = False) -> VarOutcome:
    """The correct VAR outcome for an on-field call, given what the Law says.

    `clear_and_obvious` matters only for subjective calls: if the on-field call was
    wrong but not clearly so, the VAR does not intervene and the call stands.
    """
    if on_field == law_decision or (subjective and not clear_and_obvious):
        return VarOutcome(CHECK_COMPLETE, on_field, changed=False, announced=False)
    if subjective:
        return VarOutcome(ON_FIELD_REVIEW, law_decision, changed=True, announced=True)
    return VarOutcome(VAR_OVERTURN, law_decision, changed=True, announced=not factual_offside)
