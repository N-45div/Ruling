from dataclasses import replace

from ruling.incidents import model as m
from ruling.laws import fouls as f
from ruling.laws.clauses import CLAUSES
from ruling.sim import pitch

AREA_X = pitch.LENGTH - pitch.PENALTY_AREA_DEPTH  # 88.5
AREA_EDGE_Y = pitch.CENTRE_Y + pitch.PENALTY_AREA_WIDTH / 2  # 54.16

CLEAN_TRIP = m.Challenge(action="trip", contact=True, played_ball_first=False, attempt_to_play_ball=True,
                         attacker_initiated=False, studs_up=False, lunge=False, off_ground=False, late_s=0.0,
                         speed_mps=4.0, contact_height="ankle")


def situation(kind=m.PENALTY_CLAIM, point=(95.0, 34.0), challenge=CLEAN_TRIP, handball=None, dogso=None):
    return m.FoulSituation(kind, "A", True, "D-5", "A-9", point, challenge, handball, dogso, ())


def handball(**kw):
    base = dict(arm_away_m=0.1, above_shoulder=False, moved_towards_ball=False, justified_by_movement=True,
                supporting_arm=False, off_own_body=False, distance_m=6.0, by_attacker=False, scorer=False,
                immediately_before_goal=False, goal_bound=False)
    base.update(kw)
    return m.HandballFacts(**base)


THROUGH_ON_GOAL = m.DogsoFacts(distance_m=18.0, towards_goal=True, angle_deg=10.0, control="likely",
                               defenders_able=0, attackers_support=1)


def test_area_margin_counts_the_line_as_inside():
    assert f.area_margin(AREA_X, 34.0) == 0.0
    assert f.area_margin(AREA_X - 0.1, 34.0) == -0.1
    assert f.area_margin(95.0, AREA_EDGE_Y + 0.3) == -0.3
    assert f.area_margin(AREA_X + 2, 34.0) == 2.0


def test_a_careless_trip_inside_the_area_is_a_penalty_without_a_card():
    r = f.judge(situation())
    assert (r.decision, r.clause, r.card, r.force) == (f.PENALTY, "14", f.NO_CARD, f.CARELESS)


def test_contact_on_the_line_is_a_penalty_and_just_outside_is_a_free_kick():
    assert f.judge(situation(point=(AREA_X, 34.0))).decision == f.PENALTY
    outside = f.judge(situation(point=(AREA_X - 0.05, 34.0)))
    assert outside.decision == f.FREE_KICK and outside.clause == "12.1" and outside.area_margin_m == -0.05


def test_playing_the_ball_first_excuses_only_careless_contact():
    assert f.judge(situation(challenge=replace(CLEAN_TRIP, played_ball_first=True))).decision == f.NO_FOUL
    reckless = f.judge(situation(challenge=replace(CLEAN_TRIP, played_ball_first=True, studs_up=True)))
    assert reckless.decision == f.PENALTY and reckless.card == f.YELLOW


def test_holding_is_a_foul_even_when_the_ball_was_played():
    held = replace(CLEAN_TRIP, action="holding", played_ball_first=True)
    assert f.judge(situation(challenge=held)).decision == f.PENALTY


def test_no_contact_or_contact_the_attacker_created_is_no_foul():
    assert f.judge(situation(challenge=replace(CLEAN_TRIP, contact=False))).reason == "no_contact"
    assert f.judge(situation(challenge=replace(CLEAN_TRIP, attacker_initiated=True))).decision == f.NO_FOUL


def test_force_levels_from_tracking_cues():
    assert f.force(replace(CLEAN_TRIP, studs_up=True, contact_height="shin", lunge=True)) == f.EXCESSIVE
    assert f.force(replace(CLEAN_TRIP, studs_up=True, contact_height="ankle")) == f.RECKLESS
    assert f.force(replace(CLEAN_TRIP, late_s=0.6)) == f.RECKLESS
    assert f.force(CLEAN_TRIP) == f.CARELESS


def test_serious_foul_play_and_violent_conduct_are_red():
    sfp = f.judge(situation(m.RED_CARD, (60.0, 30.0), replace(CLEAN_TRIP, studs_up=True, contact_height="shin", speed_mps=7.0)))
    assert (sfp.decision, sfp.clause) == (f.RED, "12.3-sfp")
    strike = f.judge(situation(m.RED_CARD, (60.0, 30.0), replace(CLEAN_TRIP, action="strike", contact_height="head")))
    assert (strike.decision, strike.clause) == (f.RED, "12.3-vc")


def test_dogso_outside_the_area_is_red_and_a_covering_defender_makes_it_a_yellow_at_most():
    point = (AREA_X - 3, 34.0)
    assert f.judge(situation(m.RED_CARD, point, dogso=THROUGH_ON_GOAL)).decision == f.RED
    covered = replace(THROUGH_ON_GOAL, defenders_able=1)
    ruling = f.judge(situation(m.RED_CARD, point, replace(CLEAN_TRIP, late_s=0.5), dogso=covered))
    assert ruling.decision == f.YELLOW and ruling.dogso is False


def test_dogso_in_the_area_is_downgraded_for_an_attempt_to_play_the_ball_but_not_for_holding():
    attempt = f.judge(situation(m.RED_CARD, (97.0, 34.0), dogso=THROUGH_ON_GOAL))
    assert attempt.decision == f.YELLOW and attempt.card_reason == "dogso_downgraded_attempt_to_play_ball"
    holding = replace(CLEAN_TRIP, action="holding", attempt_to_play_ball=False)
    assert f.judge(situation(m.RED_CARD, (97.0, 34.0), holding, dogso=THROUGH_ON_GOAL)).decision == f.RED


def test_handball_with_an_arm_away_from_the_body_without_justification_is_a_penalty():
    r = f.judge(situation(m.HANDBALL, handball=handball(arm_away_m=0.5, justified_by_movement=False)))
    assert r.decision == f.PENALTY and r.reason == "arm_made_body_unnaturally_bigger"


def test_an_arm_above_the_shoulder_is_not_automatically_handball():
    jump = handball(arm_away_m=0.4, above_shoulder=True, justified_by_movement=True)
    assert f.judge(situation(m.HANDBALL, handball=jump)).decision == f.NO_FOUL


def test_handball_exceptions_from_league_guidance():
    assert f.judge(situation(m.HANDBALL, handball=handball(arm_away_m=0.5, justified_by_movement=False,
                                                           supporting_arm=True))).reason == "supporting_arm"
    own_body = handball(arm_away_m=0.5, justified_by_movement=False, off_own_body=True, distance_m=0.8)
    assert f.judge(situation(m.HANDBALL, handball=own_body)).decision == f.NO_FOUL


def test_handball_stopping_a_goal_bound_ball_is_red_if_deliberate_and_yellow_if_not():
    deliberate = f.judge(situation(m.HANDBALL, handball=handball(moved_towards_ball=True, goal_bound=True)))
    assert deliberate.card == f.RED
    accidental = handball(arm_away_m=0.5, justified_by_movement=False, goal_bound=True)
    assert f.judge(situation(m.HANDBALL, handball=accidental)).card == f.YELLOW


def test_attacker_handball_counts_only_for_the_scorer_immediately_before_the_goal():
    scorer = handball(by_attacker=True, scorer=True, immediately_before_goal=True)
    assert f.judge(situation(m.HANDBALL_GOAL, handball=scorer)).decision == f.NO_GOAL
    team_mate = handball(by_attacker=True, scorer=False)
    assert f.judge(situation(m.HANDBALL_GOAL, handball=team_mate)).decision == f.GOAL


def test_every_clause_cited_is_in_the_catalogue():
    rulings = [f.judge(situation()), f.judge(situation(point=(AREA_X - 2, 34))),
               f.judge(situation(m.HANDBALL, handball=handball(moved_towards_ball=True))),
               f.judge(situation(m.RED_CARD, (97.0, 34.0), dogso=THROUGH_ON_GOAL))]
    assert all(r.clause in CLAUSES for r in rulings)
