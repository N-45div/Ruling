from collections import Counter

import pytest

from ruling.incidents import model as m
from ruling.laws import var
from ruling.sim import events as ev
from ruling.sim.calibration import fixtures
from ruling.sim.clubs import league
from ruling.sim.engine import simulate

GOAL_CATEGORIES = (m.OFFSIDE, m.HANDBALL_GOAL)


@pytest.fixture(scope="module")
def matches():
    clubs = league()
    return [simulate(clubs[h], clubs[a], s) for h, a, s in fixtures(range(5001, 5061))]


def _decision(match, incident):
    return next(e for e in match.events[incident.event_index:] if e.type == ev.VAR_DECISION)


def test_every_incident_is_followed_by_a_check_and_the_decision_it_records(matches):
    for match in matches:
        for incident in match.incidents:
            after = [e.type for e in match.events[incident.event_index + 1:incident.event_index + 4]]
            assert ev.VAR_CHECK in after and ev.VAR_DECISION in after
            assert _decision(match, incident).result == incident.final


def test_goal_checks_point_at_a_goal_and_decide_whether_it_stands(matches):
    for match in matches:
        for incident in match.incidents:
            if incident.category not in GOAL_CATEGORIES:
                continue
            shot = match.events[incident.event_index]
            assert shot.type == ev.SHOT and shot.result == ev.GOAL
            assert _decision(match, incident).detail == f"{incident.var_review}|shot:{incident.event_index}"
            assert (incident.event_index not in match.disallowed()) == (incident.final == var.GOAL)


def test_the_flag_goes_up_only_when_the_on_field_call_was_offside(matches):
    for match in matches:
        for incident in match.incidents:
            if incident.category != m.OFFSIDE:
                continue
            next_event = match.events[incident.event_index + 1]
            flagged = next_event.type == ev.OFFSIDE and next_event.detail == "flag"
            assert flagged == (incident.on_field == var.NO_GOAL)


def test_a_disallowed_goal_restarts_with_a_free_kick_to_the_defending_team(matches):
    checked = 0
    for match in matches:
        for index in match.disallowed():
            shot = match.events[index]
            # A goal ruled out in stoppage time can be the last action of the half.
            restart = next((e for e in match.events[index + 1:]
                            if e.type in ev.RESTARTS and e.period == shot.period), None)
            if restart is None:
                continue
            assert restart.type == ev.FREE_KICK and restart.team != shot.team
            checked += 1
    assert checked > 0


def test_every_penalty_follows_a_var_decision_to_award_one(matches):
    for match in matches:
        for i, e in enumerate(match.events):
            if e.type == ev.PENALTY:
                decision = next(d for d in reversed(match.events[:i]) if d.type == ev.VAR_DECISION)
                assert decision.result == "penalty"


def test_every_straight_red_card_follows_a_var_decision(matches):
    for match in matches:
        for i, e in enumerate(match.events):
            if e.type == ev.CARD and e.result == ev.RED:
                assert any(d.type == ev.VAR_DECISION for d in match.events[max(0, i - 3):i])


def test_a_dropped_ball_follows_only_a_rescinded_foul(matches):
    for match in matches:
        rescinded = {i.event_index for i in match.incidents
                     if i.on_field in ("penalty", "free_kick") and i.final == "no_foul"}
        for i, e in enumerate(match.events):
            if e.type == ev.DROPPED_BALL:
                decision = next(d for d in reversed(match.events[:i]) if d.type == ev.VAR_DECISION)
                assert int(decision.detail.split("event:")[1]) in rescinded


def test_every_category_appears_and_matches_carry_several_checks(matches):
    counts = Counter(i.category for match in matches for i in match.incidents)
    assert set(counts) == {m.OFFSIDE, m.PENALTY_CLAIM, m.HANDBALL, m.HANDBALL_GOAL, m.RED_CARD}
    assert sum(counts.values()) / len(matches) > 3.5


def test_incidents_can_be_switched_off_for_engine_only_runs():
    clubs = league()
    match = simulate(clubs["AGA"], clubs["BRC"], 5001, incidents=False)
    assert match.incidents == [] and not any(e.type == ev.VAR_CHECK for e in match.events)
