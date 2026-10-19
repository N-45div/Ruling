"""The checker: nothing is published unless every claim is backed by the evidence or the Law.

Two layers. Rules in code catch what must never appear (video claims, gendered
pronouns, removed Law wording, figures not in the evidence, a missing decision, an
announcement that is not due). A separate model review then lists each factual claim
and marks it supported, unsupported or contradicted against the evidence record.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from ..eval.stale import stale_citations
from ..laws.clauses import clause
from . import llm
from .assessor import Verdict
from .communicator import Drafts
from .evidence import Evidence
from .packet import CheckPacket

_VIDEO = re.compile(r"\b(video|replays?|footage|cameras?|camera angles?)\b", re.I)
_PRONOUN = re.compile(r"\b(he|him|his|she|her|hers)\b", re.I)
_FIGURE = re.compile(r"(\d+(?:\.\d+)?)\s?(cm|m)\b(?!/)")
_DECISION = {
    "goal": r"\b(stands?|stood|given|allowed|confirmed|counts?|awarded)\b",
    "no_goal": r"\b(disallowed|ruled out|no goal|not stand|does not count|cancelled|chalked off)\b",
    "penalty": r"\bpenalt(y|ies)\b",
    "free_kick": r"\bfree[- ]kick\b",
    "no_foul": r"\b(no foul|no penalty|not a foul|no offence|stands)\b",
    "red": r"\b(red card|sent off|sending[- ]off)\b",
    "yellow": r"\b(yellow|caution)",
    "no_card": r"\b(no card|not a (red|sending)|stands|yellow|caution)\b",
}

CHECK_INSTRUCTIONS = (
    "You check messages about a VAR decision before they are published. List every factual claim in the messages: "
    "positions, distances, contact, actions, involvement, rules of the game, the decision and any precedent. "
    "Mark each claim supported if the facts, the Law summary or the decision record state it or directly imply it; "
    "unsupported if they do not; contradicted if it conflicts with them. A restatement of the Law that matches the "
    "Law summary is supported. A claim about video, replays or anyone's intentions is unsupported."
)


class Claim(BaseModel):
    text: str
    status: Literal["supported", "unsupported", "contradicted"]
    why: str


class ClaimReview(BaseModel):
    claims: list[Claim]


@dataclass(frozen=True, slots=True)
class CheckReport:
    passed: bool
    issues: tuple[str, ...]
    claims: tuple[dict, ...] = ()


def _metres(value: str, unit: str) -> float:
    return float(value) / 100 if unit == "cm" else float(value)


def _figures(text: str) -> list[float]:
    return [_metres(v, u) for v, u in _FIGURE.findall(text)]


def rule_issues(drafts: Drafts, packet: CheckPacket, evidence: Evidence, verdict: Verdict) -> list[str]:
    known = _figures(" ".join(evidence.facts))
    channels = {"match_centre": drafts.match_centre, "stadium": drafts.stadium,
                "broadcaster": " ".join(drafts.broadcaster), "fan": drafts.fan}
    issues = []
    for name, text in channels.items():
        if _VIDEO.search(text):
            issues.append(f"{name}: mentions video or replays, but the facts come from tracking data")
        if _PRONOUN.search(text):
            issues.append(f"{name}: uses a gendered pronoun; refer to players by name or role")
        issues += [f"{name}: relies on removed Law wording ({s})"
                   for s in stale_citations(text, packet.category, verdict.final_decision)]
        for figure in _figures(text):
            if not any(abs(figure - k) <= max(0.006, 0.02 * k) for k in known):
                issues.append(f"{name}: the figure {figure:g} m is not in the evidence")
    if len(drafts.match_centre) > 280:
        issues.append("match_centre: longer than 280 characters")
    if len(drafts.fan.split()) > 60:
        issues.append("fan: longer than 60 words")
    if len(drafts.broadcaster) != 3:
        issues.append("broadcaster: must be exactly three bullets")
    if verdict.announced and not drafts.stadium.strip().startswith("REF:"):
        issues.append('stadium: an announcement is due and must read REF: "..."')
    if not verdict.announced and drafts.stadium.strip():
        issues.append("stadium: no announcement is due, so leave it empty")
    if not re.search(_DECISION[verdict.final_decision], drafts.fan, re.I):
        issues.append(f"fan: does not state the final decision ({verdict.final_decision.replace('_', ' ')})")
    return issues


def _record(packet: CheckPacket, evidence: Evidence, verdict: Verdict, precedent_line: str | None) -> str:
    law = clause(verdict.clause)
    lines = [f"Decision record: on-field {packet.on_field}; review {verdict.review}; final {verdict.final_decision};"
             f" card {verdict.card}.", "Facts:", *[f"- {f}" for f in evidence.facts],
             f"Law {law.id} ({law.title}): {law.summary}", *[f"- {c}" for c in law.criteria]]
    if precedent_line:
        lines.append(f"Precedent: {precedent_line}")
    return "\n".join(lines)


async def check(drafts: Drafts, packet: CheckPacket, evidence: Evidence, verdict: Verdict,
                precedent_line: str | None = None) -> tuple[CheckReport, llm.Usage | None]:
    issues = rule_issues(drafts, packet, evidence, verdict)
    messages = "\n".join([f"Match Centre: {drafts.match_centre}", f"Stadium: {drafts.stadium or '(none)'}",
                          *[f"Broadcaster: {b}" for b in drafts.broadcaster], f"Fan: {drafts.fan}"])
    prompt = f"{_record(packet, evidence, verdict, precedent_line)}\n\nMessages to check:\n{messages}"
    review, usage = await llm.structured("checker", CHECK_INSTRUCTIONS, prompt, ClaimReview, effort="low")
    for claim in review.claims:
        if claim.status != "supported":
            issues.append(f"{claim.status} claim {claim.text!r}: {claim.why}")
    return CheckReport(not issues, tuple(issues), tuple(c.model_dump() for c in review.claims)), usage
