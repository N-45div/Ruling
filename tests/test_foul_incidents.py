from collections import Counter

import pytest

from ruling.incidents import model as m
from ruling.incidents.fouls import FoulPlanner, make_foul_incident
from ruling.laws import fouls as law
from ruling.laws import var
from ruling.sim import events as ev
from ruling.sim.clubs import league
from ruling.sim.engine import simulate

EXPECTED = {
    "clear_foul_inside": {law.PENALTY}, "line_contact_inside": {law.PENALTY}, "holding": {law.PENALTY},
    "clear_foul_outside": {law.FREE_KICK}, "line_contact_outside": {law.FREE_KICK},
    "played_ball_first": {law.NO_FOUL}, "attacker_initiated": {law.NO_FOUL}, "no_contact_dive": {law.NO_FOUL},
    "arm_extended_unjustified": {law.PENALTY}, "deliberate_reach": {law.PENALTY},
    "arm_natural_close": {law.NO_FOUL}, "off_own_body": {law.NO_FOUL}, "supporting_arm": {law.NO_FOUL},
    "above_shoulder_justified": {law.NO_FOUL},
    "scorer_arm_before_goal": {law.NO_GOAL}, "team_mate_accidental": {law.GOAL},
    "sfp_excessive": {law.RED}, "violent_conduct_missed": {law.RED}, "dogso_clear": {law.RED},
    "dogso_in_area_holding": {law.RED}, "reckless_not_red": {law.YELLOW}, "dogso_in_area_attempt": {law.YELLOW},
    "dogso_covering_defender": {law.YELLOW, law.NO_CARD}, "dogso_wide_angle": {law.YELLOW, law.NO_CARD},
}


@pytest.fixture(scope="module")
def plans():
    clubs = league()
    match = simulate(clubs["AGA"], clubs["CWR"], 5001, incidents=False)
    victim, offender = match.home_lineup[-1], match.away_lineup[2]
    planner = FoulPlanner(5001)
    out = []
    for n in range(60, 1600, 4):
        prefix = ev.Match(match.id, match.seed, match.home, match.away, match.events[:n],
                          match.home_lineup, match.away_lineup)
        team = match.home
        out.append((prefix, planner.penalty_claim(prefix, team, victim, offender, (95.0, 30.0))))
        out.append((prefix, planner.handball(prefix, team, offender, (97.0, 36.0))))
        out.append((prefix, planner.handball_goal(prefix, team, victim, (96.0, 33.0))))
        far = (55.0, 20.0) if n % 8 else (84.0, 34.0)
        out.append((prefix, planner.red_card(prefix, team, victim, offender, far)))
    return out


def test_every_plan_is_judged_from_its_facts_and_matches_its_scenario(plans):
    for _, plan in plans:
        assert law.judge(plan.situation) == plan.ruling
        if plan.scenario in EXPECTED:
            assert plan.ruling.decision in EXPECTED[plan.scenario], plan.scenario


def test_line_scenarios_are_decided_by_centimetres(plans):
    for _, plan in plans:
        if plan.scenario == "line_contact_inside":
            assert 0.0 <= plan.ruling.area_margin_m <= 0.3
        if plan.scenario == "line_contact_outside":
            assert -0.4 <= plan.ruling.area_margin_m <= -0.05


def test_every_scenario_is_planted(plans):
    seen = {plan.scenario for _, plan in plans}
    assert seen >= set(EXPECTED) - {"violent_conduct_missed"}


def test_dogso_scenarios_only_happen_near_goal(plans):
    for _, plan in plans:
        if plan.scenario.startswith("dogso"):
            assert plan.situation.dogso is not None and plan.situation.dogso.distance_m <= 32


def test_the_var_outcome_follows_the_protocol(plans):
    for _, plan in plans:
        truth = plan.ruling.decision
        if plan.category in (m.PENALTY_CLAIM, m.HANDBALL):
            reviewable = law.PENALTY in (plan.on_field, truth)
        elif plan.category == m.RED_CARD:
            reviewable = law.RED in (plan.on_field, truth)
        else:
            reviewable = True
        expected = var.review(plan.on_field, truth, plan.subjective, plan.clear_and_obvious, reviewable=reviewable)
        assert plan.outcome == expected
        if not plan.clear_and_obvious:
            assert plan.outcome.final == plan.on_field


def test_a_location_only_disagreement_is_factual(plans):
    for _, plan in plans:
        if plan.category == m.PENALTY_CLAIM and {plan.on_field, plan.ruling.decision} == {law.PENALTY, law.FREE_KICK}:
            assert not plan.subjective and plan.outcome.review == var.VAR_OVERTURN


def test_on_field_calls_carry_errors_but_are_mostly_right(plans):
    by_category = Counter()
    right = Counter()
    for _, plan in plans:
        by_category[plan.category] += 1
        right[plan.category] += plan.on_field == plan.ruling.decision
    for category, total in by_category.items():
        assert 0.55 < right[category] / total < 0.95, category


def test_the_handball_arm_is_at_the_touch_point(plans):
    for _, plan in plans:
        if plan.category == m.HANDBALL and plan.situation.bodies:
            parts = plan.situation.body(plan.situation.offender).parts
            assert any(parts[a] == plan.situation.point for a in m.ARM_PARTS)
            return
    pytest.fail("no handball plan with bodies")


def test_foul_incidents_round_trip_through_dicts(plans):
    for prefix, plan in plans[:8]:
        incident = make_foul_incident(prefix, plan, len(prefix.events) - 1)
        assert m.incident_from_dict(m.incident_to_dict(incident)) == incident
