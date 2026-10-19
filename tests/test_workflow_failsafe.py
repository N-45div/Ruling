"""The fail-safe paths of the desk workflow. These run the real workflow: both cases stop
before any model call, so no service is involved."""

import asyncio
from dataclasses import replace

from ruling.desk.packet import packet_for
from ruling.desk.workflow import run_check
from ruling.sim.cli import match_for_seed


def _offside_packet():
    match = match_for_seed(5001)
    incident = next(i for i in match.incidents if i.category == "offside")
    return packet_for(match, incident)


def test_a_packet_without_positions_gets_only_a_holding_line():
    packet = _offside_packet()
    case = asyncio.run(run_check(replace(packet, facts={**packet.facts, "bodies": []})))
    assert case.status == "held"
    assert case.holding == "VAR check in progress: possible offside."
    assert case.verdict is None and case.drafts is None
    assert [s.agent for s in case.steps] == ["intake", "fail-safe"]


def test_facts_that_cannot_be_measured_never_produce_a_guess():
    packet = _offside_packet()
    broken = {**packet.facts, "attacker": "NOBODY-0"}  # the assessed player is not on the pitch
    case = asyncio.run(run_check(replace(packet, facts=broken)))
    assert case.status == "held" and case.verdict is None
    assert case.failure.startswith("evidence could not be computed")
    assert [s.agent for s in case.steps] == ["intake", "evidence", "fail-safe"]
