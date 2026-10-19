from ruling.desk.evidence import gather
from ruling.desk.packet import packet_for
from ruling.desk.precedent import PastCase, case_text, summarize
from ruling.sim.cli import match_for_seed


def past(final: str, i: int = 0) -> PastCase:
    return PastCase(f"m:{i}:offside", "m", "10:00", "offside", "goal", final, "interfering_with_play", "text")


def test_case_text_removes_player_names_so_only_the_situation_counts():
    match = match_for_seed(5001)
    incident = match.incidents[0]
    packet = packet_for(match, incident)
    text = case_text(packet, gather(packet))
    assert "No." not in text
    assert incident.category.replace("_", " ") in text


def test_summary_counts_outcomes_and_flags_inconsistency():
    neighbours = [(past("no_goal", i), 0.9 - i / 100) for i in range(7)] + [(past("goal", 9), 0.8)]
    agree = summarize(neighbours, "no_goal")
    assert agree.finals == {"no_goal": 7, "goal": 1} and agree.agreeing == 7 and agree.consistent
    against = summarize(neighbours, "goal")
    assert against.agreeing == 1 and not against.consistent
    assert len(agree.similar) == 3 and agree.similar[0]["similarity"] == 0.9


def test_no_neighbours_is_not_an_inconsistency():
    assert summarize([], "goal").consistent
