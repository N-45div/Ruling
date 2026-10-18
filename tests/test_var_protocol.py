from ruling.laws.var import CHECK_COMPLETE, GOAL, NO_GOAL, ON_FIELD_REVIEW, VAR_OVERTURN, review


def test_a_correct_call_is_a_silent_check():
    outcome = review(GOAL, GOAL, subjective=False)
    assert outcome.review == CHECK_COMPLETE and outcome.final == GOAL and not outcome.announced


def test_a_wrong_factual_offside_call_is_corrected_by_the_var_without_an_announcement():
    outcome = review(GOAL, NO_GOAL, subjective=False, factual_offside=True)
    assert outcome.review == VAR_OVERTURN and outcome.final == NO_GOAL
    assert outcome.changed and not outcome.announced


def test_a_wrong_subjective_call_goes_to_an_announced_on_field_review():
    outcome = review(GOAL, NO_GOAL, subjective=True)
    assert outcome.review == ON_FIELD_REVIEW and outcome.final == NO_GOAL and outcome.announced


def test_classify_separates_factual_from_subjective_and_out_of_scope_calls():
    from ruling.laws.var import classify
    position = classify("offside", GOAL, NO_GOAL, "interfering_with_play")
    assert not position.subjective and position.factual_offside
    assert classify("offside", GOAL, NO_GOAL, "interfering_with_an_opponent").subjective
    assert not classify("penalty_claim", "penalty", "free_kick", "trip").subjective  # location only
    assert classify("penalty_claim", "no_foul", "penalty", "trip").subjective
    assert not classify("penalty_claim", "free_kick", "no_foul", "trip").reviewable  # no penalty involved
    assert not classify("red_card", "yellow", "no_card", "trip").reviewable  # cautions are not reviewed
    assert not classify("handball_goal", GOAL, NO_GOAL, "scorer_touched_immediately_before_goal").subjective


def test_a_call_outside_the_var_scope_stands_even_if_wrong():
    outcome = review("yellow", "no_card", subjective=True, reviewable=False)
    assert outcome.review == CHECK_COMPLETE and outcome.final == "yellow"


def test_a_subjective_call_that_is_wrong_but_not_clearly_wrong_stands():
    outcome = review(GOAL, NO_GOAL, subjective=True, clear_and_obvious=False)
    assert outcome.review == CHECK_COMPLETE and outcome.final == GOAL and not outcome.changed
