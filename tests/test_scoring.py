import pytest

from ruling.desk.assessor import Verdict
from ruling.eval.scoring import ArmResult, expected, paired_bootstrap, score, summarize
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
    assert summary["difference"]["all"]["comparison"] == "b - a"
