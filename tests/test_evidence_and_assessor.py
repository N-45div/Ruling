import pytest

from ruling.desk.assessor import assess, card_after
from ruling.desk.evidence import gather
from ruling.desk.packet import packet_for
from ruling.sim.cli import match_for_seed


@pytest.fixture(scope="module")
def cases():
    out = []
    for seed in range(5001, 5021):  # development seeds only
        match = match_for_seed(seed)
        for incident in match.incidents:
            packet = packet_for(match, incident)
            evidence = gather(packet)
            out.append((incident, packet, evidence, assess(packet, evidence)))
    return out


def test_evidence_reaches_the_same_law_decision_as_the_ground_truth(cases):
    for incident, _, evidence, _ in cases:
        assert evidence.law_decision == incident.law_decision
        assert evidence.clause == incident.ruling["clause"]


def test_the_assessor_is_right_whenever_borderline_detection_agrees(cases):
    agreed = [(i, v) for i, _, e, v in cases if e.borderline == (not i.clear_and_obvious)]
    assert len(agreed) / len(cases) > 0.95
    for incident, verdict in agreed:
        assert verdict.final_decision == incident.final
        assert verdict.review == incident.var_review


def test_cards_follow_the_final_decision(cases):
    for incident, _, evidence, verdict in cases:
        assert verdict.card == card_after(incident.category, verdict.final_decision, evidence.card)


def test_every_fact_is_a_plain_sentence(cases):
    for _, _, evidence, _ in cases:
        assert evidence.facts
        assert all(f.endswith(".") for f in evidence.facts)


@pytest.mark.parametrize("incident_id, attempt", [("TDA-GLH-31:333:red_card", "tried to play the ball."),
                                                   ("WVF-FVT-1:539:red_card", "made no attempt to play the ball.")])
def test_dogso_in_the_area_states_what_decides_red_or_yellow(incident_id, attempt):
    # Inside the area, a genuine attempt to play the ball makes DOGSO a caution: both facts must be stated.
    match = match_for_seed(int(incident_id.split(":")[0].split("-")[-1]))
    incident = next(i for i in match.incidents if i.id == incident_id)
    facts = gather(packet_for(match, incident)).facts
    assert any("inside the penalty area" in f for f in facts) and facts[-1].endswith(attempt)
