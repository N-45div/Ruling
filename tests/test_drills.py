"""Failure drills. The packet drills must always stop at intake; the wrong-draft drill plants a
line that only the checker can catch. No model is called here."""

from ruling.desk.communicator import Drafts
from ruling.desk.drills import break_packet, caught, plant
from ruling.desk.packet import gaps, packet_for
from ruling.sim.cli import SETS, match_for_seed


def test_every_packet_drill_stops_at_intake():
    for seed in SETS["dev"]:
        match = match_for_seed(seed)
        for incident in match.incidents:
            packet = packet_for(match, incident)
            assert gaps(break_packet(packet, "tracking_dropout")) == "the packet has no tracked positions"
            assert gaps(break_packet(packet, "player_missing")), incident.id
            assert break_packet(packet, "wrong_draft") is packet


def test_losing_the_line_setter_names_the_shortfall():
    match = match_for_seed(5004)
    incident = next(i for i in match.incidents if i.id.endswith(":1044:offside"))
    broken = break_packet(packet_for(match, incident), "player_missing")
    assert gaps(broken) == "tracking has 10 of 11 NBR players, so the offside line cannot be set"


def test_the_planted_line_states_the_opposite_decision_in_one_channel():
    drafts = Drafts(match_centre="Goal disallowed for offside.", stadium="",
                    broadcaster=["Decision: the goal is disallowed.", "Line: 15 cm.", "Law 11.2."],
                    fan="VAR found the attacker 15 cm offside, so the goal is disallowed.")
    planted = plant(drafts, "no_goal")
    assert planted.broadcaster == ["Decision: the goal stands.", "Line: 15 cm.", "Law 11.2."]
    assert (planted.fan, planted.match_centre) == (drafts.fan, drafts.match_centre)


def test_the_drill_stops_planting_once_the_checker_flags_it():
    assert not caught([], "no_goal")
    assert not caught([["style: shorten the fan card", "fan: longer than 60 words"]], "no_goal")
    assert caught([["contradicted claim 'Decision: the goal stands.': the record says no goal"]], "no_goal")
