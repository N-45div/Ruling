from ruling.api.limits import Limiter


def test_a_window_allows_its_limit_then_says_how_long_to_wait():
    now = [0.0]
    limiter = Limiter(clock=lambda: now[0])
    assert [limiter.allow("k", 3, 60) for _ in range(3)] == [0.0, 0.0, 0.0]
    assert limiter.allow("k", 3, 60) == 60.0
    now[0] = 30.0
    assert limiter.allow("k", 3, 60) == 30.0
    now[0] = 60.0  # the first hits have left the window
    assert limiter.allow("k", 3, 60) == 0.0
    assert limiter.allow("other", 3, 60) == 0.0  # keys are independent
