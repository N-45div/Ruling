import pytest

from ruling.sim import events as ev
from ruling.sim import pitch
from ruling.sim.clubs import league
from ruling.sim.engine import simulate
from ruling.sim.shape import frame_at, lineups_at


@pytest.fixture(scope="module")
def match():
    clubs = league()
    return simulate(clubs["DMU"], clubs["EHA"], 5003)


def test_a_frame_has_both_teams_and_is_deterministic(match):
    frame = frame_at(match, 200)
    assert len(frame.team(match.home)) + len(frame.team(match.away)) >= 20
    assert frame == frame_at(match, 200)


def test_the_player_on_the_ball_stands_at_the_ball(match):
    index = next(i for i, e in enumerate(match.events) if e.type == ev.PASS and i > 50)
    event = match.events[index]
    frame = frame_at(match, index)
    spot = next(p for p in frame.players if p.player == event.player)
    assert (spot.x, spot.y) == (event.start_x, event.start_y)


def test_every_player_is_on_the_pitch(match):
    for index in range(0, len(match.events), 37):
        for p in frame_at(match, index).players:
            assert 0 <= p.x <= pitch.LENGTH and 0 <= p.y <= pitch.WIDTH


def test_ordinary_passes_show_no_false_offside(match):
    for index, event in enumerate(match.events):
        if event.type != ev.PASS or event.detail == "offside":
            continue
        frame = frame_at(match, index)
        right = match.attacks_right(frame.possession, event.period)
        to_frame = (lambda x: x) if right else (lambda x: pitch.LENGTH - x)
        defenders = sorted((to_frame(p.x) for p in frame.players if p.team != frame.possession), reverse=True)
        line = max(defenders[1], to_frame(event.start_x))
        attackers = [to_frame(p.x) for p in frame.players if p.team == frame.possession and p.player != event.player]
        assert all(x <= line + 1e-6 for x in attackers)


def test_substitutes_take_the_replaced_players_place():
    clubs = league()
    for seed in range(5001, 5011):
        m = simulate(clubs["AGA"], clubs["BRC"], seed)
        subs = [i for i, e in enumerate(m.events) if e.type == "substitution"]
        if subs:
            i = subs[0]
            sub = m.events[i]
            on = lineups_at(m, i + 1)[sub.team]
            assert sub.player in on and sub.detail[4:] not in on
            return
    pytest.fail("no substitution in ten matches")
