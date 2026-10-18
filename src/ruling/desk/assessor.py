"""The assessor: apply the VAR protocol to the evidence and recommend an outcome."""

from __future__ import annotations

from dataclasses import dataclass

from ..incidents import model as m
from ..laws import fouls, var
from .evidence import Evidence
from .packet import CheckPacket


@dataclass(frozen=True, slots=True)
class Verdict:
    final_decision: str
    card: str
    review: str  # check_complete | var_overturn | on_field_review
    clause: str
    explanation: str = ""


def card_after(category: str, final: str, law_card: str) -> str:
    """The card that goes with a final decision."""
    if category == m.RED_CARD:
        return final
    if category in (m.PENALTY_CLAIM, m.HANDBALL) and final in (fouls.PENALTY, fouls.FREE_KICK):
        return law_card
    return fouls.NO_CARD


def assess(packet: CheckPacket, evidence: Evidence) -> Verdict:
    kind = var.classify(packet.category, packet.on_field, evidence.law_decision, evidence.reason)
    outcome = var.review(packet.on_field, evidence.law_decision, kind.subjective,
                         clear_and_obvious=not evidence.borderline, factual_offside=kind.factual_offside,
                         reviewable=kind.reviewable)
    return Verdict(outcome.final, card_after(packet.category, outcome.final, evidence.card), outcome.review,
                   evidence.clause)
