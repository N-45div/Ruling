"""The arms of the evaluation. Each takes a check packet and returns a verdict.

A. model_only: gpt-5-mini reads the raw packet and decides everything itself.
B. ruling_v0: computed evidence and the encoded VAR protocol decide; the model only writes
   the fan explanation from those facts. Later versions add precedent and a checker.
Both arms use the same model deployment and see the same packet.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import replace
from typing import Literal

from pydantic import BaseModel, Field

from ..desk import communicator, llm
from ..desk.assessor import Verdict, assess
from ..desk.evidence import gather
from ..desk.packet import CheckPacket, packet_dict
from ..laws.clauses import EDITION
from .scoring import ALLOWED, ArmResult

MODEL_ONLY_INSTRUCTIONS = (
    "You support the video assistant referee (VAR) at a professional football match played under the IFAB Laws of "
    f"the Game {EDITION} and the VAR protocol. You receive a check packet as JSON: the match so far, the event under "
    "review, the observed facts, and the referee's on-field decision. Coordinates are metres on a 105 x 68 pitch; x "
    "runs from the left goal line (0) to the right goal line (105). attacks_right says whether the team in possession "
    "attacks towards x = 105. Body parts give each player's head, torso, shoulders, knees, feet and arms at the moment "
    "shown. Decide the correct outcome of the VAR check. final_decision is the decision that should stand after the "
    "check; card is the card that goes with it; review is check_complete if the on-field decision stands, "
    "var_overturn if the VAR corrects a factual error alone, or on_field_review if the referee should change a "
    "subjective decision at the monitor; clause is the Law clause that governs the decision; explanation is for fans, "
    "at most 60 words, using only facts from the packet. Apply the VAR protocol: the VAR intervenes only for a clear "
    "and obvious error or a serious missed incident in a reviewable decision, and a subjective call that is wrong but "
    "not clearly wrong stands."
)


class ModelVerdict(BaseModel):
    final_decision: Literal["goal", "no_goal", "penalty", "free_kick", "no_foul", "red", "yellow", "no_card"]
    card: Literal["red", "yellow", "no_card"]
    review: Literal["check_complete", "var_overturn", "on_field_review"]
    clause: str = Field(description='The governing clause, e.g. "11.2", "12.1", "14".')
    explanation: str = Field(description="For fans, at most 60 words.")


async def _retry(call, attempts: int = 3):
    for attempt in range(attempts):
        try:
            return await call()
        except Exception:  # rate limits and transient service errors
            if attempt == attempts - 1:
                raise
            await asyncio.sleep(4 * (attempt + 1))


class ModelOnly:
    name = "model_only"
    effort = "medium"

    async def run(self, packet: CheckPacket) -> ArmResult:
        prompt = (f"Category: {packet.category}. Allowed final decisions: {', '.join(ALLOWED[packet.category])}.\n"
                  f"Check packet:\n{json.dumps(packet_dict(packet), separators=(',', ':'))}")
        try:
            value, usage = await _retry(lambda: llm.structured(self.name, MODEL_ONLY_INSTRUCTIONS, prompt,
                                                               ModelVerdict, effort=self.effort))
        except Exception as exc:
            return ArmResult(None, error=f"{type(exc).__name__}: {exc}"[:300])
        verdict = Verdict(value.final_decision, value.card, value.review, value.clause, value.explanation)
        return ArmResult(verdict, usage.seconds, usage.input_tokens, usage.output_tokens)


class RulingV0:
    name = "ruling_v0"
    effort = "low"  # the communicator's effort; the verdict itself needs no model call

    async def run(self, packet: CheckPacket) -> ArmResult:
        started = time.perf_counter()
        evidence = gather(packet)
        verdict = assess(packet, evidence)
        try:
            text, usage = await _retry(lambda: communicator.explain(packet, evidence, verdict))
        except Exception as exc:
            return ArmResult(verdict, round(time.perf_counter() - started, 2), error=f"{type(exc).__name__}: {exc}"[:300])
        return ArmResult(replace(verdict, explanation=text), round(time.perf_counter() - started, 2),
                         usage.input_tokens, usage.output_tokens)


ARMS = {arm.name: arm for arm in (ModelOnly(), RulingV0())}
