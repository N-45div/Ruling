from ruling.sim.clubs import FORMATIONS, ROLE_GK, league

# Abbreviations used by real top-flight English clubs, past and present. Ours must differ.
REAL_CODES = {
    "ARS", "AVL", "BOU", "BRE", "BHA", "BUR", "CHE", "CRY", "EVE", "FUL", "IPS", "LEE",
    "LEI", "LIV", "LUT", "MCI", "MUN", "NEW", "NFO", "SHU", "SOU", "SUN", "TOT", "WHU",
    "WOL", "WAT", "NOR", "WBA", "MID", "STK", "SWA", "HUL", "CAR", "QPR", "BLA", "BOL",
}


def test_league_has_20_clubs_with_unique_fictional_codes():
    clubs = league()
    assert len(clubs) == 20
    assert not set(clubs) & REAL_CODES


def test_every_squad_has_18_players_unique_shirts_and_a_goalkeeper_first():
    for club in league().values():
        assert len(club.players) == 18
        assert len({p.shirt for p in club.players}) == 18
        assert club.starters[0].role == ROLE_GK and club.starters[0].shirt == 1
        assert [p.position for p in club.starters] == [slot for slot, _, _ in FORMATIONS[club.formation]]


def test_player_names_are_unique_across_the_league():
    names = [p.name for club in league().values() for p in club.players]
    assert len(names) == len(set(names))


def test_squads_are_deterministic():
    first = league()["AGA"]
    league.cache_clear()
    assert league()["AGA"] == first


def test_attributes_stay_in_range():
    for club in league().values():
        for p in club.players:
            for value in (p.passing, p.finishing, p.aggression, p.pace):
                assert 0.0 < value < 1.0
