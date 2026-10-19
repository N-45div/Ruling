"""The desk as a Microsoft Agent Framework workflow.

    intake -> evidence -> laws -> assessor -> precedent -> communicator <-> checker -> approval
       \\_________ any failure ____________________________________________/
                                       v
                                   fail-safe

A case file travels through the graph and every agent adds its part. Numbers come from
code (evidence, assessor); the model writes and checks the words (communicator,
checker). A draft that fails the checker goes back to the communicator with the
issues, at most twice. Anything that breaks routes to the fail-safe, which publishes
only a holding line. Nothing is published until a person approves it.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from agent_framework import Case, Default, Executor, WorkflowBuilder, WorkflowContext, handler, response_handler

from ..laws.clauses import Clause, clause
from ..sim.clubs import league
from . import checker as checking
from . import communicator, llm, precedent
from .assessor import Verdict, assess
from .checker import CheckReport
from .communicator import Drafts
from .evidence import Evidence, gather
from .packet import CheckPacket
from .precedent import Precedent

MAX_REVISIONS = 2
# Reasoning effort for the model calls; the verdict itself never depends on them.
WRITE_EFFORT = "minimal"  # measured: minimal halves the time and needs fewer rewrites
CHECK_EFFORT = "low"
APPROVE = "approve"
_WORDS = {"goal": "the goal stands", "no_goal": "the goal is disallowed", "penalty": "a penalty is awarded",
          "free_kick": "a free kick is awarded outside the area", "no_foul": "no foul", "red": "a red card",
          "yellow": "a yellow card", "no_card": "no card"}


@dataclass
class Step:
    agent: str
    seconds: float
    note: str = ""


@dataclass
class CaseFile:
    packet: CheckPacket
    evidence: Evidence | None = None
    law: Clause | None = None
    verdict: Verdict | None = None
    precedent: Precedent | None = None
    drafts: Drafts | None = None
    check: CheckReport | None = None
    revisions: int = 0
    feedback: list[str] = field(default_factory=list)
    status: str = "open"  # open | failed | revise | checked | published | held
    failure: str | None = None
    holding: str | None = None  # the only message the fail-safe publishes
    consistency_flag: str | None = None  # internal: the recommendation goes against precedent
    steps: list[Step] = field(default_factory=list)
    check_history: list[list[str]] = field(default_factory=list)  # the checker's findings on each draft
    tokens_in: int = 0
    tokens_out: int = 0

    def log(self, agent: str, started: float, note: str = "") -> None:
        self.steps.append(Step(agent, round(time.perf_counter() - started, 3), note))

    def spend(self, usage: llm.Usage | None) -> None:
        if usage:
            self.tokens_in += usage.input_tokens
            self.tokens_out += usage.output_tokens


@dataclass
class PublishRequest:
    case_id: str
    summary: str
    drafts: Drafts


def precedent_line(p: Precedent | None, final: str) -> str | None:
    if not p or not p.finals:
        return None
    total = sum(p.finals.values())
    return f"{p.agreeing} of the {total} most similar past checks ended the same way ({_WORDS[final]})."


class Intake(Executor):
    @handler
    async def run(self, case: CaseFile, ctx: WorkflowContext[CaseFile]) -> None:
        started = time.perf_counter()
        facts = case.packet.facts
        if not facts or not facts.get("bodies") and case.packet.category == "offside":
            case.status, case.failure = "failed", "the packet has no positions to measure"
        case.log("intake", started, case.failure or "packet complete")
        await ctx.send_message(case)


class EvidenceAgent(Executor):
    @handler
    async def run(self, case: CaseFile, ctx: WorkflowContext[CaseFile]) -> None:
        started = time.perf_counter()
        try:
            case.evidence = gather(case.packet)
            note = f"{len(case.evidence.facts)} facts" + (", borderline" if case.evidence.borderline else "")
        except Exception as exc:  # malformed facts must never produce a guess
            case.status, case.failure, note = "failed", f"evidence could not be computed: {exc}", "failed"
        case.log("evidence", started, note)
        await ctx.send_message(case)


class LawsAgent(Executor):
    @handler
    async def run(self, case: CaseFile, ctx: WorkflowContext[CaseFile]) -> None:
        started = time.perf_counter()
        case.law = clause(case.evidence.clause)
        case.log("laws", started, f"Law {case.law.id}")
        await ctx.send_message(case)


class AssessorAgent(Executor):
    @handler
    async def run(self, case: CaseFile, ctx: WorkflowContext[CaseFile]) -> None:
        started = time.perf_counter()
        case.verdict = assess(case.packet, case.evidence)
        case.log("assessor", started, f"{case.verdict.review}: {case.verdict.final_decision}")
        await ctx.send_message(case)


class PrecedentAgent(Executor):
    def __init__(self, id: str, enabled: bool = True):
        super().__init__(id=id)
        self.enabled = enabled

    @handler
    async def run(self, case: CaseFile, ctx: WorkflowContext[CaseFile]) -> None:
        started = time.perf_counter()
        note = "off"
        if self.enabled:
            try:
                case.precedent = await precedent.find(case.packet, case.evidence, case.verdict.final_decision)
                note = f"{case.precedent.agreeing} of {sum(case.precedent.finals.values())} agree"
                if not case.precedent.consistent:
                    case.consistency_flag = "the recommendation differs from the most common past outcome"
            except Exception as exc:  # precedent is advisory: carry on without it
                note = f"unavailable: {type(exc).__name__}"
        case.log("precedent", started, note)
        await ctx.send_message(case)


class CommunicatorAgent(Executor):
    @handler
    async def run(self, case: CaseFile, ctx: WorkflowContext[CaseFile]) -> None:
        started = time.perf_counter()
        clubs = {code: club.name for code, club in league().items()}
        line = precedent_line(case.precedent, case.verdict.final_decision)
        try:
            case.drafts, usage = await llm.with_retry(lambda: communicator.draft(
                case.packet, case.evidence, case.verdict, clubs, line, case.feedback, effort=WRITE_EFFORT))
            case.spend(usage)
            note = f"draft {case.revisions + 1}"
        except Exception as exc:
            case.status, case.failure, note = "failed", f"drafting failed: {type(exc).__name__}", "failed"
        case.log("communicator", started, note)
        await ctx.send_message(case)


class CheckerAgent(Executor):
    def __init__(self, id: str, enabled: bool = True):
        super().__init__(id=id)
        self.enabled = enabled

    @handler
    async def run(self, case: CaseFile, ctx: WorkflowContext[CaseFile]) -> None:
        started = time.perf_counter()
        if not self.enabled:
            case.status = "checked"
            case.log("checker", started, "off")
            await ctx.send_message(case)
            return
        line = precedent_line(case.precedent, case.verdict.final_decision)
        try:
            case.check, usage = await llm.with_retry(lambda: checking.check(
                case.drafts, case.packet, case.evidence, case.verdict, line, effort=CHECK_EFFORT))
            case.spend(usage)
        except Exception as exc:
            case.status, case.failure = "failed", f"checking failed: {type(exc).__name__}"
            case.log("checker", started, "failed")
            await ctx.send_message(case)
            return
        if case.check.passed and case.check.style and case.revisions == 0:
            # Style issues get one rewrite, but never hold a decision back.
            case.status, case.feedback, case.revisions = "revise", list(case.check.style), 1
        elif case.check.passed:
            case.status = "checked"
        elif case.revisions < MAX_REVISIONS:
            feedback = list(case.check.issues) + list(case.check.style)
            case.status, case.feedback, case.revisions = "revise", feedback, case.revisions + 1
        else:
            case.status, case.failure = "failed", f"drafts still failed {len(case.check.issues)} checks"
        case.check_history.append(list(case.check.issues) + [f"style: {x}" for x in case.check.style])
        case.log("checker", started, f"{case.status}: {len(case.check.issues)} issue(s)")
        await ctx.send_message(case)


class Approval(Executor):
    @handler
    async def run(self, case: CaseFile, ctx: WorkflowContext[CaseFile, CaseFile]) -> None:
        summary = (f"{case.packet.category.replace('_', ' ')} at {case.packet.clock}: "
                   f"{case.verdict.review.replace('_', ' ')}, {_WORDS[case.verdict.final_decision]}")
        ctx.set_state("case", case)
        await ctx.request_info(PublishRequest(case.packet.incident_id, summary, case.drafts), str)

    @response_handler
    async def decide(self, request: PublishRequest, answer: str, ctx: WorkflowContext[CaseFile, CaseFile]) -> None:
        case: CaseFile = ctx.get_state("case")
        if answer == APPROVE:
            case.status = "published"
        else:
            case.status, case.holding = "held", "VAR check in progress."
        case.steps.append(Step("approval", 0.0, answer))
        await ctx.yield_output(case)


class FailSafe(Executor):
    @handler
    async def run(self, case: CaseFile, ctx: WorkflowContext[CaseFile, CaseFile]) -> None:
        # Only a holding line: the decision if it is known, never an explanation that was not checked.
        if case.verdict:
            case.holding = f"VAR check complete: {_WORDS[case.verdict.final_decision]}."
        else:
            case.holding = f"VAR check in progress: possible {case.packet.category.replace('_', ' ')}."
        case.status = "held"
        case.steps.append(Step("fail-safe", 0.0, case.failure or ""))
        await ctx.yield_output(case)


def _failed(case: CaseFile) -> bool:
    return case.status == "failed"


def build(use_precedent: bool = True, use_checker: bool = True):
    intake, evidence, laws = Intake(id="intake"), EvidenceAgent(id="evidence"), LawsAgent(id="laws")
    assessor, prior = AssessorAgent(id="assessor"), PrecedentAgent(id="precedent", enabled=use_precedent)
    writer, check = CommunicatorAgent(id="communicator"), CheckerAgent(id="checker", enabled=use_checker)
    approval, failsafe = Approval(id="approval"), FailSafe(id="fail-safe")
    return (
        WorkflowBuilder(name="ruling-desk", start_executor=intake, max_iterations=40)
        .add_switch_case_edge_group(intake, [Case(condition=_failed, target=failsafe), Default(target=evidence)])
        .add_switch_case_edge_group(evidence, [Case(condition=_failed, target=failsafe), Default(target=laws)])
        .add_edge(laws, assessor)
        .add_edge(assessor, prior)
        .add_edge(prior, writer)
        .add_switch_case_edge_group(writer, [Case(condition=_failed, target=failsafe), Default(target=check)])
        .add_switch_case_edge_group(check, [Case(condition=lambda c: c.status == "checked", target=approval),
                                            Case(condition=lambda c: c.status == "revise", target=writer),
                                            Default(target=failsafe)])
        .build()
    )


async def run_check(packet: CheckPacket, approve=None, use_precedent: bool = True,
                    use_checker: bool = True) -> CaseFile:
    """Run one VAR check through the desk. `approve` receives the PublishRequest and returns
    "approve" or anything else to hold; by default every checked case is approved."""
    workflow = build(use_precedent, use_checker)
    result = await workflow.run(CaseFile(packet))
    outputs = result.get_outputs()
    if outputs:
        return outputs[-1]
    request = result.get_request_info_events()[0]
    answer = approve(request.data) if approve else APPROVE
    result = await workflow.run(responses={request.request_id: answer})
    return result.get_outputs()[-1]
