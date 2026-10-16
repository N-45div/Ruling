import pytest

from ruling.laws import var
from ruling.sim import events as ev
from ruling.sim.calibration import fixtures
from ruling.sim.clubs import league
from ruling.sim.engine import simulate


@pytest.fixture(scope="module")
def matches():
    clubs = league()
    return [simulate(clubs[h], clubs[a], s) for h, a, s in fixtures(range(5001, 5061))]


def test_each_incident_points_at_a_goal_and_is_followed_by_a_check_and_a_decision(matches):
    for match in matches:
        for incident in match.incidents:
            shot = match.events[incident.shot_index]
            assert shot.type == ev.SHOT and shot.result == ev.GOAL
            after = match.events[incident.shot_index + 1:incident.shot_index + 4]
            kinds = [e.type for e in after]
            assert ev.VAR_CHECK in kinds and ev.VAR_DECISION in kinds


def test_the_flag_goes_up_only_when_the_on_field_call_was_offside(matches):
    for match in matches:
        for incident in match.incidents:
            next_event = match.events[incident.shot_index + 1]
            flagged = next_event.type == ev.OFFSIDE and next_event.detail == "flag"
            assert flagged == (incident.on_field == var.NO_GOAL)


def test_the_recorded_decision_matches_the_incident_and_the_score(matches):
    for match in matches:
        for incident in match.incidents:
            decision = next(e for e in match.events[incident.shot_index:] if e.type == ev.VAR_DECISION)
            assert decision.result == (ev.GOAL if incident.final == var.GOAL else ev.NO_GOAL)
            assert decision.detail == f"{incident.var_review}|shot:{incident.shot_index}"
            stands = incident.shot_index not in match.disallowed()
            assert stands == (incident.final == var.GOAL)


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
            assert restart.type == ev.FREE_KICK and restart.team != shot.team and restart.detail == "offside"
            checked += 1
    assert checked > 0


def test_incidents_can_be_switched_off_for_engine_only_runs():
    clubs = league()
    match = simulate(clubs["AGA"], clubs["BRC"], 5001, incidents=False)
    assert match.incidents == [] and not any(e.type == ev.VAR_CHECK for e in match.events)
