import json

import pytest

from ruling.desk.packet import HIDDEN, packet_dict, packet_for
from ruling.sim.cli import match_for_seed


@pytest.fixture(scope="module")
def packets():
    out = []
    for seed in range(5001, 5006):
        match = match_for_seed(seed)
        out += [(match, i, packet_for(match, i)) for i in match.incidents]
    return out


# Scenario names that are also ordinary fact vocabulary (a challenge type, a handball cue).
FACT_WORDS = {"holding", "supporting_arm"}


def test_no_ground_truth_reaches_the_packet(packets):
    for _, incident, packet in packets:
        text = json.dumps(packet_dict(packet))
        for field in HIDDEN:
            assert f'"{field}"' not in text
        if incident.scenario not in FACT_WORDS:
            assert incident.scenario not in text  # scenario labels never leak through the facts


def test_the_packet_carries_the_on_field_call_and_the_event_under_review(packets):
    for match, incident, packet in packets:
        assert packet.on_field == incident.on_field
        assert packet.event["clock"] == match.events[incident.event_index].clock
        assert len(packet.recent) <= 12


def test_the_score_counts_only_goals_before_the_event(packets):
    for match, incident, packet in packets:
        before = [g for g in match.goals() if g.index < incident.event_index]
        assert sum(packet.score) == len(before)


def test_foul_packets_keep_only_the_players_involved(packets):
    for _, incident, packet in packets:
        if incident.category != "offside":
            named = {packet.facts["offender"], packet.facts["victim"]}
            assert {b["player"] for b in packet.facts["bodies"]} <= named


def test_every_named_player_is_described(packets):
    for _, _, packet in packets:
        for key in ("attacker", "passer", "offender", "victim"):
            pid = packet.facts.get(key)
            if pid:
                assert packet.players[pid]["name"]
