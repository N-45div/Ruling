import math

from ruling.sim import pitch
from ruling.sim.events import GOAL, NO_GOAL, PASS, SHOT, VAR_DECISION, Event, Match, read_events, write_events


def make_event(**overrides) -> Event:
    fields = dict(
        match_id="m1", index=0, period=1, second=0.0, team="AGA", player="AGA-9",
        type=PASS, result="success", start_x=50.0, start_y=34.0, end_x=60.0, end_y=30.0,
    )
    fields.update(overrides)
    return Event(**fields)


def test_to_absolute_flips_for_the_team_attacking_left():
    assert pitch.to_absolute(10, 20, attacks_right=True) == (10, 20)
    assert pitch.to_absolute(10, 20, attacks_right=False) == (95, 48)


def test_goal_angle_is_widest_on_the_goal_line_centre_and_zero_behind_it():
    near = pitch.goal_angle(104.0, pitch.CENTRE_Y)
    far = pitch.goal_angle(80.0, pitch.CENTRE_Y)
    assert near > far > 0
    assert pitch.goal_angle(pitch.LENGTH, 10) == 0.0


def test_penalty_area_lines_belong_to_the_area():
    edge_x = pitch.LENGTH - pitch.PENALTY_AREA_DEPTH
    assert pitch.in_penalty_area(edge_x, pitch.CENTRE_Y)
    assert not pitch.in_penalty_area(edge_x - 0.01, pitch.CENTRE_Y)
    assert pitch.in_penalty_area(100, pitch.CENTRE_Y + pitch.PENALTY_AREA_WIDTH / 2)


def test_halfway_line_counts_as_own_half():
    assert pitch.in_own_half(pitch.HALFWAY_X)
    assert not pitch.in_own_half(pitch.HALFWAY_X + 0.01)


def test_distance_to_goal_from_the_penalty_spot():
    spot_x = pitch.LENGTH - pitch.PENALTY_SPOT_DISTANCE
    assert math.isclose(pitch.distance_to_goal(spot_x, pitch.CENTRE_Y), 11.0)


def test_clock_shows_stoppage_time():
    assert make_event(second=754.0).clock == "12:34"
    assert make_event(period=2, second=60.0).clock == "46:00"
    assert make_event(second=45 * 60 + 130).clock == "45+2:10"
    assert make_event(period=2, second=45 * 60 + 5).clock == "90+0:05"


def test_score_counts_goals_that_stand_after_var():
    match = Match(id="m1", seed=1, home="AGA", away="BRC", events=[
        make_event(index=0, type=SHOT, result=GOAL, team="AGA"),
        make_event(index=1, type=SHOT, result=GOAL, team="BRC"),
        make_event(index=2, type=SHOT, result=GOAL, team="AGA"),
        make_event(index=3, type=VAR_DECISION, result=NO_GOAL, team="AGA", detail="var_overturn|shot:2"),
    ])
    assert match.disallowed() == {2}
    assert match.score() == (1, 1)


def test_events_round_trip_through_json_lines(tmp_path):
    events = [make_event(index=i, xg=0.1 * i) for i in range(3)]
    path = tmp_path / "events.jsonl"
    write_events(path, events)
    assert list(read_events(path)) == events
