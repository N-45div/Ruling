"""The fail-safe paths of the desk workflow. These run the real workflow: every case stops
before any model call, so no service is involved."""

import asyncio
from dataclasses import replace

from ruling.desk.evidence import situation_from_facts
from ruling.desk.packet import gaps, packet_for
from ruling.desk.workflow import run_check
from ruling.laws.offside import judge
from ruling.sim.cli import SETS, match_for_seed


def _packet(category="offside", seed=5001):
    match = match_for_seed(seed)
    incident = next(i for i in match.incidents if i.category == category)
    return packet_for(match, incident)


def test_every_demo_packet_is_complete():
    # The completeness check must never hold a real check.
    for seed in SETS["dev"]:
        match = match_for_seed(seed)
        for incident in match.incidents:
            packet = packet_for(match, incident)
            assert gaps(packet) is None, (incident.id, gaps(packet))
            assert sum(packet.on_pitch.values()) >= 14


def test_losing_the_line_setter_is_always_caught():
    # Without this check, 7 of the 39 demo offside goals would be wrongly disallowed.
    caught = 0
    for seed in SETS["dev"]:
        match = match_for_seed(seed)
        for incident in (i for i in match.incidents if i.category == "offside"):
            packet = packet_for(match, incident)
            setter = judge(situation_from_facts("offside", packet.facts)).second_last
            if setter:
                bodies = [b for b in packet.facts["bodies"] if b["player"] != setter]
                assert gaps(replace(packet, facts={**packet.facts, "bodies": bodies})), incident.id
                caught += 1
    assert caught >= 30


def test_a_packet_without_positions_gets_only_a_holding_line():
    packet = _packet()
    case = asyncio.run(run_check(replace(packet, facts={**packet.facts, "bodies": []})))
    assert case.status == "held"
    assert case.holding == "VAR check in progress: possible offside."
    assert case.verdict is None and case.drafts is None
    assert [s.agent for s in case.steps] == ["intake", "fail-safe"]


def test_a_defender_missing_from_tracking_never_moves_the_offside_line():
    # 64:51 in match 5004: the goal is disallowed by 15 cm against the line NBR No.7 sets.
    match = match_for_seed(5004)
    incident = next(i for i in match.incidents if i.category == "offside" and i.id.endswith(":1044:offside"))
    packet = packet_for(match, incident)
    line_setter = judge(situation_from_facts("offside", packet.facts)).second_last
    bodies = [b for b in packet.facts["bodies"] if b["player"] != line_setter]
    broken = replace(packet, facts={**packet.facts, "bodies": bodies})
    assert gaps(broken) == "tracking has 10 of 11 NBR players, so the offside line cannot be set"
    case = asyncio.run(run_check(broken))
    assert case.status == "held" and case.verdict is None
    assert [s.agent for s in case.steps] == ["intake", "fail-safe"]


def test_a_challenge_with_a_player_missing_is_not_measured():
    packet = _packet("penalty_claim")
    bodies = [b for b in packet.facts["bodies"] if b["player"] != packet.facts["victim"]]
    broken = replace(packet, facts={**packet.facts, "bodies": bodies})
    assert gaps(broken)  # never reaches a model
    case = asyncio.run(run_check(broken))
    assert case.status == "held" and case.holding == "VAR check in progress: possible penalty claim."
    assert case.failure == "tracking lost a player in the challenge"


def test_facts_that_cannot_be_measured_never_produce_a_guess():
    packet = _packet()
    attacker = packet.facts["attacker"]
    bodies = [{**b, "parts": {}} if b["player"] == attacker else b for b in packet.facts["bodies"]]
    case = asyncio.run(run_check(replace(packet, facts={**packet.facts, "bodies": bodies})))
    assert case.status == "held" and case.verdict is None
    assert case.failure.startswith("evidence could not be computed")
    assert [s.agent for s in case.steps] == ["intake", "evidence", "fail-safe"]
