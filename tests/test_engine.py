import pytest

from ruling.sim import events as ev
from ruling.sim import pitch
from ruling.sim.clubs import league
from ruling.sim.engine import SUBSTITUTION, expected_goals, simulate


@pytest.fixture(scope="module")
def matches():
    clubs = league()
    return [simulate(clubs["AGA"], clubs["FVT"], seed) for seed in range(5001, 5021)]


def test_same_seed_gives_the_same_match():
    clubs = league()
    first = simulate(clubs["BRC"], clubs["CWR"], 5001)
    second = simulate(clubs["BRC"], clubs["CWR"], 5001)
    assert first.events == second.events


def test_different_seeds_give_different_matches(matches):
    assert matches[0].events != matches[1].events


def test_events_are_indexed_and_chronological_within_each_period(matches):
    for match in matches:
        assert [e.index for e in match.events] == list(range(len(match.events)))
        for period in (1, 2):
            seconds = [e.second for e in match.events if e.period == period]
            assert seconds == sorted(seconds)
            assert seconds[-1] >= ev.PERIOD_SECONDS


def test_every_event_is_on_the_pitch(matches):
    for match in matches:
        for e in match.events:
            assert 0 <= e.start_x <= pitch.LENGTH and 0 <= e.end_x <= pitch.LENGTH
            assert 0 <= e.start_y <= pitch.WIDTH and 0 <= e.end_y <= pitch.WIDTH


def test_each_period_opens_and_closes(matches):
    for match in matches:
        kinds = [e.type for e in match.events]
        assert kinds[0] == ev.PERIOD_START and kinds[-1] == ev.PERIOD_END
        assert kinds.count(ev.PERIOD_START) == kinds.count(ev.PERIOD_END) == 2


def test_the_conceding_team_kicks_off_after_a_goal(matches):
    checked = 0
    for match in matches:
        for i, e in enumerate(match.events):
            if e.result != ev.GOAL:
                continue
            # A goal in stoppage time can be the last action of the half.
            restart = next((n for n in match.events[i + 1:]
                            if n.type == ev.KICKOFF and n.period == e.period), None)
            if restart is not None:
                assert restart.team != e.team
                checked += 1
    assert checked > 0


def test_penalties_are_taken_from_the_spot(matches):
    spots = {pitch.PENALTY_SPOT_DISTANCE, pitch.LENGTH - pitch.PENALTY_SPOT_DISTANCE}
    for match in matches:
        for e in match.events:
            if e.type == ev.PENALTY:
                assert e.start_x in spots and e.start_y == pitch.CENTRE_Y


def test_a_sent_off_player_takes_no_further_part(matches):
    for match in matches:
        for i, e in enumerate(match.events):
            if e.type == ev.CARD and e.result in (ev.RED, ev.SECOND_YELLOW):
                later = match.events[i + 1:]
                assert not any(n.player == e.player for n in later)


def test_at_most_five_substitutions_per_team(matches):
    for match in matches:
        for team in (match.home, match.away):
            subs = [e for e in match.events if e.type == SUBSTITUTION and e.team == team]
            assert len(subs) <= 5


def test_expected_goals_falls_with_distance_and_for_headers():
    spot = pitch.LENGTH - pitch.PENALTY_SPOT_DISTANCE
    close = expected_goals(pitch.LENGTH - 6, pitch.CENTRE_Y)
    assert close > expected_goals(spot, pitch.CENTRE_Y) > expected_goals(80, pitch.CENTRE_Y)
    assert expected_goals(spot, pitch.CENTRE_Y, header=True) < expected_goals(spot, pitch.CENTRE_Y)
