import pytest

from ruling.desk.assessor import Verdict
from ruling.eval.scoring import (ArmResult, Score, cost_per_incident, expected, paired_bootstrap,
                                 paired_claim_bootstrap, planted_errors, score, summarize)
from ruling.eval.stale import stale_citations
from ruling.sim.cli import match_for_seed


@pytest.fixture(scope="module")
def incidents():
    return [i for seed in range(5001, 5004) for i in match_for_seed(seed).incidents]


def test_a_verdict_matching_the_truth_scores_on_every_metric(incidents):
    incident = incidents[0]
    final, card = expected(incident)
    verdict = Verdict(final, card, incident.var_review, incident.ruling["clause"], "The goal stands.")
    s = score("arm", incident, ArmResult(verdict))
    assert s.verdict_ok and s.review_ok and s.law_ok and s.clause_ok and not s.stale


def test_a_missing_verdict_scores_nothing(incidents):
    s = score("arm", incidents[0], ArmResult(None, error="timeout"))
    assert not s.verdict_ok and s.error == "timeout"


def test_clause_matching_ignores_formatting_and_suffixes(incidents):
    foul = next(i for i in incidents if i.ruling["clause"].startswith("12.1"))
    final, card = expected(foul)
    s = score("arm", foul, ArmResult(Verdict(final, card, foul.var_review, "Law 12.1 (handling)")))
    assert s.law_ok and s.clause_ok


def test_stale_law_detector():
    assert stale_citations("The arm was above the shoulder, so it is handball.", "handball") == ["handball_above_shoulder"]
    assert stale_citations("An arm above the shoulder is not automatically an offence.", "handball") == []
    assert stale_citations("It created a goal-scoring opportunity with the hand.", "handball") == ["handball_creates_chance"]
    assert "dogso_without_attackers" in stale_citations(
        "It denied an obvious goal-scoring opportunity: no defenders could cover.", "red_card")
    assert stale_citations(
        "It denied an obvious goal-scoring opportunity: no defenders could cover and two attackers were free.",
        "red_card") == []


def test_paired_bootstrap_brackets_the_mean_difference():
    a = [True] * 50 + [False] * 50
    b = [True] * 90 + [False] * 10
    diff, low, high = paired_bootstrap(a, b, resamples=2000)
    assert diff == 0.4 and low < diff < high and low > 0


def test_summary_reports_both_arms_and_their_difference(incidents):
    rows = []
    for incident in incidents:
        final, card = expected(incident)
        rows.append(score("a", incident, ArmResult(Verdict("no_goal", "no_card", "check_complete", "11"))))
        rows.append(score("b", incident, ArmResult(Verdict(final, card, incident.var_review, incident.ruling["clause"]))))
    summary = summarize(rows)
    assert summary["arms"]["b"]["verdict_ok"] == 1.0
    assert summary["difference"]["b"]["all"]["comparison"] == "b - a"
    b = summary["arms"]["b"]
    assert b["planted_errors"]["recall"] == 1.0 and b["planted_errors"]["precision"] in (1.0, None)
    assert set(b["by_category"]) == {i.category for i in incidents}
    assert all("clause_ok" in m and "planted_errors" in m for m in b["by_category"].values())
    assert b["contested"]["incidents"] == sum(r.contested for r in rows if r.arm == "b")


def _row(arm, n, planted=False, flagged=False, scored=0, unsupported=0, tokens=(0, 0)):
    return Score(arm, f"i{n}", "offside", False, True, True, True, True, True, True, planted=planted,
                 flagged=flagged, claims_scored=scored, claims_unsupported=unsupported,
                 input_tokens=tokens[0], output_tokens=tokens[1])


def test_planted_error_detection_counts_flags_against_wrong_on_field_calls():
    rows = [_row("a", 0, planted=True, flagged=True), _row("a", 1, planted=True), _row("a", 2, flagged=True),
            _row("a", 3)]
    assert planted_errors(rows) == {"planted": 2, "flagged": 2, "caught": 1, "precision": 0.5, "recall": 0.5}


def test_cost_uses_the_list_price_per_million_tokens():
    assert cost_per_incident([_row("a", 0, tokens=(1_000_000, 0)), _row("a", 1, tokens=(0, 1_000_000))]) == 1.125


def test_the_claim_rate_difference_has_an_interval():
    pairs = [(_row("a", n, scored=4, unsupported=1), _row("b", n, scored=4, unsupported=0)) for n in range(60)]
    diff, low, high = paired_claim_bootstrap(pairs, resamples=500)
    assert diff == -0.25 and low <= diff <= high
    assert paired_claim_bootstrap([(_row("a", 0), _row("b", 0))]) is None


def test_above_the_shoulder_counts_as_stale_only_when_it_explains_an_offence():
    text = "The arm was above the shoulder, but its position follows from the body's movement."
    assert stale_citations(text, "handball", "no_foul") == []
    assert stale_citations("The arm was above the shoulder, so a penalty.", "handball", "penalty") == [
        "handball_above_shoulder"]


def test_raw_data_in_fan_text_is_detected():
    from ruling.eval.readability import raw_artifacts
    assert raw_artifacts("The ball struck MLA-11's arm (above_shoulder: false) at [93.5, 19.9].") == [
        "raw_player_id", "field_name", "coordinates", "boolean"]
    assert raw_artifacts("The ball struck Goran Zanivic's arm, held 0.60 m from the body.") == []
