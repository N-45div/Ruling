from ruling.sim.calibration import TARGETS, fixtures, misses, run


def test_fixtures_are_deterministic_and_never_pair_a_club_with_itself():
    pairs = fixtures(range(1, 50))
    assert pairs == fixtures(range(1, 50))
    assert all(home != away for home, away, _ in pairs)


def test_engine_matches_public_aggregates_over_200_development_matches():
    # Development seeds only (see docs/eval-plan.md); 200 matches keep sampling noise
    # well inside the target ranges.
    means = run(range(5001, 5201))
    assert misses(means) == {}, {k: (round(v, 3), TARGETS[k]) for k, v in misses(means).items()}
