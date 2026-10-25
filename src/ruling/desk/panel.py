"""A Key Match Incidents panel after the match: five independent reviewers vote on each VAR check.

Modelled on the independent panels leagues use to review key decisions after each round: former
players and coaches, a league representative and a referees' representative vote on whether each
decision was right and whether the VAR was right to step in. Every member reads the same decision
record the checker uses (measured facts, the Law, the VAR protocol, precedent) and never sees the
others' votes. Microsoft Agent Framework runs the five concurrently (ConcurrentBuilder: fan-out,
fan-in, aggregate) and code tallies the votes. The panel is an opinion on the decision, not the
decision: the measured verdict stands, and a split vote is reported as a split vote.
"""

from __future__ import annotations

from agent_framework.orchestrations import ConcurrentBuilder
from pydantic import BaseModel, Field

from . import llm
from .checker import _figures, _record
from .packet import CheckPacket
from .assessor import Evidence, Verdict

SEATS = {
    "former_striker": ("Former striker", "You played as a striker for many seasons. Judge as an attacker would: "
                       "did the decision treat the attacking side fairly, given what was measured?"),
    "former_defender": ("Former defender", "You played as a centre-back for many seasons. Judge as a defender "
                        "would: was the defending side treated fairly, given what was measured?"),
    "former_coach": ("Former coach", "You managed teams for many seasons. Judge as a coach would: is this the "
                     "decision a fair-minded coach would accept, given what was measured?"),
    "league": ("League representative", "You represent the league. Judge consistency: does the decision match "
               "how the Law and the precedent are applied across the league?"),
    "referees": ("Referees' representative", "You represent the referees. Judge strictly by the Law and the "
                 "VAR protocol: the VAR intervenes only for a clear and obvious error or a factual matter."),
}

INSTRUCTIONS = (
    "You sit on an independent panel that reviews key match incidents after the match. Read the decision record "
    "and vote on two questions on your own judgement: was the final decision correct, and was the VAR right to "
    "intervene (or right not to)? Then give one sentence of reasoning that uses only facts in the record, with any "
    "figures written exactly as the record writes them, and players named by name or role, never he or she. "
    "Fictional clubs and players; no outside knowledge."
)


class Vote(BaseModel):
    decision_correct: bool = Field(description="The final decision was the correct one.")
    var_right: bool = Field(description="The VAR was right to intervene, or right not to.")
    reason: str = Field(description="One sentence, from the record's facts only.")


def _tally(votes: list[bool]) -> str:
    yes = sum(votes)
    return f"{yes}-{len(votes) - yes}"


def summarise(votes: dict[str, Vote], facts: list[str]) -> dict:
    """The panel's verdict from the members' votes: tallies, dissent, and each member's reason.
    A reason that cites a figure the record does not contain is withheld, not shown."""
    known = _figures(" ".join(facts))
    members = []
    for seat, vote in votes.items():
        cited = _figures(vote.reason)
        grounded = all(any(abs(f - k) <= max(0.006, 0.02 * k) for k in known) for f in cited)
        members.append({"seat": SEATS[seat][0], "decision_correct": vote.decision_correct, "var_right": vote.var_right,
                        "reason": vote.reason if grounded else None})
    correct = [m["decision_correct"] for m in members]
    var_right = [m["var_right"] for m in members]
    majority = sum(correct) * 2 > len(correct)
    return {
        "members": members,
        "decision_correct": _tally(correct),
        "var_right": _tally(var_right),
        "verdict": "decision upheld" if majority else "decision questioned",
        "unanimous": len(set(correct)) == 1 and len(set(var_right)) == 1,
        "dissent": [m["seat"] for m in members if m["decision_correct"] != majority],
    }


def build():
    """The five seats as one Agent Framework workflow: the record fans out, the votes fan in."""
    agents = [llm.client().as_agent(name=seat, instructions=f"{INSTRUCTIONS} {lens}",
                                    default_options={"reasoning": {"effort": "low"}, "response_format": Vote})
              for seat, (_, lens) in SEATS.items()]

    def collect(results) -> dict[str, Vote]:
        votes = {}
        for r in results:
            response = r.agent_response
            value = getattr(response, "value", None)
            votes[r.executor_id] = value if isinstance(value, Vote) else Vote.model_validate_json(response.text)
        return votes

    return ConcurrentBuilder(participants=agents).with_aggregator(collect).build()


async def convene(packet: CheckPacket, evidence: Evidence, verdict: Verdict, precedent_line: str | None) -> dict:
    record = _record(packet, evidence, verdict, precedent_line)

    async def run():
        result = await build().run(record)
        return result.get_outputs()[-1]

    votes = await llm.with_retry(run, attempts=2, timeout=60.0)
    return summarise(votes, list(evidence.facts))
