from ruling.desk.panel import SEATS, Vote, summarise

FACTS = ["Fernvale Town No.19 was fouled 6 cm outside the penalty area."]


def votes(*correct, var_right=True, reason="The contact was 6 cm outside the penalty area."):
    return {seat: Vote(decision_correct=c, var_right=var_right, reason=reason) for seat, c in zip(SEATS, correct)}


def test_five_seats_like_a_key_match_incidents_panel():
    assert len(SEATS) == 5
    assert {label for label, _ in SEATS.values()} >= {"Former striker", "Former defender", "Referees' representative"}


def test_a_unanimous_panel_upholds_the_decision():
    result = summarise(votes(True, True, True, True, True), FACTS)
    assert result["decision_correct"] == "5-0" and result["var_right"] == "5-0"
    assert result["verdict"] == "decision upheld" and result["unanimous"] and result["dissent"] == []


def test_a_split_panel_names_its_dissenters():
    result = summarise(votes(True, True, False, True, False), FACTS)
    assert result["decision_correct"] == "3-2" and result["verdict"] == "decision upheld"
    assert result["dissent"] == ["Former coach", "Referees' representative"] and not result["unanimous"]
    assert summarise(votes(False, False, False, True, True), FACTS)["verdict"] == "decision questioned"


def test_a_reason_with_a_figure_not_in_the_record_is_withheld():
    result = summarise(votes(True, True, True, True, True, reason="The contact was 40 cm outside the area."), FACTS)
    assert all(m["reason"] is None for m in result["members"])
    assert all(m["reason"] for m in summarise(votes(True, True, True, True, True), FACTS)["members"])
