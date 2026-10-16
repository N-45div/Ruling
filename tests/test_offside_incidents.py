from collections import Counter

import pytest

from ruling.incidents import model as m
from ruling.incidents.offside import OffsidePlanner, key_pass_index, make_incident
from ruling.laws import var
from ruling.laws.offside import judge
from ruling.sim import events as ev
from ruling.sim import pitch
from ruling.sim.calibration import fixtures
from ruling.sim.clubs import league
from ruling.sim.engine import simulate

GOAL_STANDS = {"clear_onside", "tight_onside", "arm_beyond", "teammate_not_involved",
               "deliberate_play_reset", "restart_exempt"}
NO_GOAL = {"tight_offside", "clear_offside", "teammate_blocks_view", "deflection_offside"}


def plans_for(seeds):
    """Plan the offside question for every goal in plain engine matches."""
    clubs = league()
    out = []
    for home, away, seed in fixtures(seeds):
        match = simulate(clubs[home], clubs[away], seed, incidents=False)
        for i, e in enumerate(match.events):
            if e.type != ev.SHOT or e.result != ev.GOAL or e.detail == "penalty":
                continue
            before = ev.Match(match.id, match.seed, match.home, match.away, match.events[:i],
                              match.home_lineup, match.away_lineup)
            right = match.attacks_right(e.team, e.period)
            shot_xy = pitch.to_absolute(e.start_x, e.start_y, right)
            plan = OffsidePlanner(seed).plan(before, e.team, e.player, shot_xy)
            if plan:
                out.append((before, plan))
    return out


@pytest.fixture(scope="module")
def plans():
    return plans_for(range(5001, 5151))


def test_most_goals_have_a_team_mates_pass_to_check(plans):
    assert len(plans) > 250


def test_the_truth_comes_from_the_geometry_and_matches_each_scenario(plans):
    for _, plan in plans:
        assert judge(plan.situation) == plan.ruling
        if plan.scenario in GOAL_STANDS:
            assert not plan.ruling.offside, plan.scenario
        if plan.scenario in NO_GOAL:
            assert plan.ruling.offside, plan.scenario


def test_tight_scenarios_are_decided_by_centimetres(plans):
    for _, plan in plans:
        if plan.scenario == "tight_offside":
            assert 0.0 < plan.ruling.margin_m <= 0.26
        if plan.scenario == "tight_onside":
            assert -0.26 <= plan.ruling.margin_m <= 0.0
        if plan.scenario == "arm_beyond":
            assert plan.ruling.reason == "arms_ignored" and plan.ruling.arm_beyond


def test_restarts_are_exempt_and_cut_backs_are_onside(plans):
    reasons = Counter(plan.ruling.reason for _, plan in plans)
    assert reasons["restart_exempt"] > 0
    assert reasons["behind_ball"] > 0


def test_every_scenario_appears_over_150_matches(plans):
    seen = {plan.scenario for _, plan in plans}
    assert seen >= {"clear_onside", "tight_onside", "tight_offside", "arm_beyond", "teammate_not_involved"}


def test_the_var_outcome_follows_the_protocol(plans):
    for _, plan in plans:
        expected = var.review(plan.on_field, var.NO_GOAL if plan.ruling.offside else var.GOAL,
                              plan.subjective, plan.clear_and_obvious, factual_offside=not plan.subjective)
        assert plan.outcome == expected
        if not plan.clear_and_obvious:
            assert plan.outcome.final == plan.on_field


def test_planted_on_field_errors_exist_but_most_calls_are_right(plans):
    right = sum(plan.on_field == (var.NO_GOAL if plan.ruling.offside else var.GOAL) for _, plan in plans)
    assert 0.80 < right / len(plans) < 0.99


def test_key_pass_is_none_after_a_regain():
    events = [ev.Event("m", 0, 1, 1.0, "B", "B-4", ev.INTERCEPTION, ev.SUCCESS, 50, 30, 50, 30)]
    assert key_pass_index(events, "A", "A-9") is None


def test_incidents_round_trip_through_dicts(plans):
    before, plan = plans[0]
    incident = make_incident(before, plan, len(before.events) - 1)
    assert m.incident_from_dict(m.incident_to_dict(incident)) == incident
