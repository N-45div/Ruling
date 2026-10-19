"""Unsupported-claim rate (docs/eval-plan.md): an independent audit of each fan explanation.

The judge is separate from the desk's checker (different prompt, no shared state). It
splits an explanation into atomic claims and labels each against the raw check data,
the measured facts and our summary of the relevant Laws. Statements that only announce
the decision are not scored here: whether the decision is right is the verdict metric.
Claims about rules not in our summary count as unsupported, for every arm alike.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel

from ..desk import llm
from ..desk.evidence import gather
from ..desk.packet import CheckPacket, packet_dict
from ..laws.clauses import CLAUSES

JUDGE_INSTRUCTIONS = (
    "You audit explanations of VAR decisions for an evaluation. You receive the raw check data as JSON, measured "
    "facts computed from it, a summary of the relevant Laws of the Game, and one explanation written for fans. Split "
    "the explanation into atomic claims. kind is 'decision' for a statement that only announces what was decided, "
    "'law' for a statement of a rule, and 'fact' for anything about the incident. Label each claim: supported if the "
    "data, the facts or the Law summary support it; unsupported if nothing given supports it; contradicted if it "
    "conflicts with them. Statements about the VAR process (the VAR checked, the decision stands, the VAR corrected "
    "a factual decision, the referee reviewed it at the monitor) are 'decision' claims. Saying that tracking data "
    "shows a fact in the data is a claim about that fact. Claims about what video or replays show, or about "
    "anyone's intentions or feelings, are unsupported. Do not judge whether the decision itself is right."
)
_LAWS = {"offside": ("11", "VAR"), "penalty_claim": ("12", "14", "VAR"), "handball": ("12", "14", "VAR"),
         "handball_goal": ("12", "VAR"), "red_card": ("12", "VAR")}


class AuditedClaim(BaseModel):
    text: str
    kind: Literal["decision", "law", "fact"]
    status: Literal["supported", "unsupported", "contradicted"]


class Audit(BaseModel):
    claims: list[AuditedClaim]


@dataclass(frozen=True, slots=True)
class ClaimScore:
    scored: int  # fact and law claims
    unsupported: int  # unsupported or contradicted fact and law claims
    claims: tuple[dict, ...]


def _law_summary(category: str) -> str:
    prefixes = _LAWS[category]
    lines = []
    for c in CLAUSES.values():
        if c.id.split(".")[0].split("-")[0] in prefixes:
            lines.append(f"Law {c.id} {c.title}: {c.summary} " + " ".join(c.criteria))
    return "\n".join(lines)


async def audit(packet: CheckPacket, explanation: str) -> tuple[ClaimScore, llm.Usage]:
    facts = gather(packet).facts
    prompt = "\n\n".join([
        f"Raw check data:\n{json.dumps(packet_dict(packet), separators=(',', ':'))}",
        "Measured facts:\n" + "\n".join(f"- {f}" for f in facts),
        f"Laws of the Game summary:\n{_law_summary(packet.category)}",
        f"Explanation to audit:\n{explanation}",
    ])
    result, usage = await llm.with_retry(lambda: llm.structured("claim-judge", JUDGE_INSTRUCTIONS, prompt, Audit,
                                                                effort="low"))
    scored = [c for c in result.claims if c.kind != "decision"]
    unsupported = sum(c.status != "supported" for c in scored)
    return ClaimScore(len(scored), unsupported, tuple(c.model_dump() for c in result.claims)), usage
