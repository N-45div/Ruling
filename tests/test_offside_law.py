from ruling.incidents import model as m
from ruling.laws.clauses import CLAUSES
from ruling.laws.offside import judge, second_last_opponent


def body(player, team, x, y=34.0, **parts):
    """A player standing upright at x, with any part moved by keyword (absolute x only)."""
    base = {name: (x, y) for name in m.COUNTING_PARTS + m.ARM_PARTS}
    base.update({name: (px, y) for name, px in parts.items()})
    return m.Body(player, team, 9, "FWD", base)


def situation(attacker_x=90.0, attacker_parts=None, defenders=(100.0, 88.0, 80.0), ball_x=60.0,
              kick=m.OPEN_PLAY, involvement=m.PLAYED_BALL, intervening=None, attacks_right=True):
    bodies = [body("A-9", "A", attacker_x, **(attacker_parts or {})), body("A-8", "A", ball_x)]
    bodies += [body(f"D-{i}", "D", x) for i, x in enumerate(defenders)]
    return m.OffsideSituation("A", attacks_right, (ball_x, 34.0), kick, "A-8", "A-9",
                              involvement, intervening, tuple(bodies))


def test_beyond_the_second_last_defender_and_receiving_is_offside():
    ruling = judge(situation(attacker_x=90.0))
    assert ruling.offside and ruling.clause == "11.2" and ruling.reason == "interfering_with_play"
    assert ruling.margin_m == 2.0 and ruling.second_last == "D-1"


def test_level_with_the_second_last_defender_is_onside():
    ruling = judge(situation(attacker_x=88.0))
    assert not ruling.offside and ruling.reason == "level_or_behind" and ruling.margin_m == 0.0


def test_a_foot_a_few_centimetres_beyond_the_line_is_offside():
    ruling = judge(situation(attacker_x=87.9, attacker_parts={"right_foot": 88.04}))
    assert ruling.offside and ruling.attacker_part == "right_foot"
    assert abs(ruling.margin_m - 0.04) < 1e-9


def test_arms_are_ignored():
    ruling = judge(situation(attacker_x=87.8, attacker_parts={"left_arm": 88.3}))
    assert not ruling.offside and ruling.reason == "arms_ignored" and ruling.arm_beyond


def test_the_defenders_arm_does_not_set_the_line():
    s = situation(attacker_x=88.5, defenders=(100.0, 88.0, 80.0))
    defender = s.body("D-1")
    defender.parts["right_arm"] = (89.0, 34.0)
    assert judge(s).offside  # the line stays at 88.0, not the arm at 89.0


def test_behind_the_ball_is_onside():
    ruling = judge(situation(attacker_x=90.0, ball_x=92.0))
    assert not ruling.offside and ruling.reason == "behind_ball"


def test_the_halfway_line_is_the_players_own_half():
    ruling = judge(situation(attacker_x=52.5, defenders=(100.0, 50.0, 45.0), ball_x=40.0))
    assert not ruling.offside and ruling.reason == "own_half"


def test_no_offence_directly_from_a_throw_in_corner_or_goal_kick():
    for kick in (m.THROW_IN, m.CORNER, m.GOAL_KICK):
        ruling = judge(situation(kick=kick))
        assert not ruling.offside and ruling.clause == "11.3"


def test_offside_position_without_involvement_is_not_an_offence():
    ruling = judge(situation(involvement=m.NOT_INVOLVED))
    assert not ruling.offside and ruling.reason == "not_involved"


def test_blocking_the_goalkeepers_line_of_vision_is_an_offence():
    ruling = judge(situation(involvement=m.LINE_OF_VISION))
    assert ruling.offside and ruling.reason == "interfering_with_an_opponent"


def test_deliberate_play_by_a_defender_resets_but_a_save_or_deflection_does_not():
    assert not judge(situation(intervening=m.DELIBERATE_PLAY)).offside
    for touch in (m.DELIBERATE_SAVE, m.DEFLECTION, m.WOODWORK):
        ruling = judge(situation(intervening=touch))
        assert ruling.offside and ruling.reason == "gaining_an_advantage"


def test_works_for_a_team_attacking_left():
    # Mirror of the first test: attacking towards x = 0.
    s = situation(attacker_x=15.0, defenders=(5.0, 17.0, 25.0), ball_x=45.0, attacks_right=False)
    ruling = judge(s)
    assert ruling.offside and ruling.margin_m == 2.0


def test_second_last_opponent_counts_the_goalkeeper():
    s = situation(defenders=(103.0, 88.0, 80.0))
    assert second_last_opponent(s) == ("D-1", 88.0)


def test_every_clause_a_ruling_cites_is_in_the_catalogue():
    for s in (situation(), situation(attacker_x=80), situation(kick=m.CORNER)):
        assert judge(s).clause in CLAUSES
