"""A fictional league: 20 invented clubs with styles, formations and squads.

Every club and player name is made up. Club codes are chosen not to collide with real
top-flight club abbreviations, and player surnames are built from syllables so that a
full name is very unlikely to match a real professional.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from functools import cache

ROLE_GK, ROLE_DEF, ROLE_MID, ROLE_FWD = "GK", "DEF", "MID", "FWD"

# Base positions per slot in the attacking frame (attacking towards x = 105) for a
# mid-block with the ball near the centre circle. Facing +x, a team's right is low y.
FORMATIONS: dict[str, tuple[tuple[str, float, float], ...]] = {
    "4-3-3": (
        ("GK", 4, 34), ("RB", 30, 9), ("RCB", 24, 25), ("LCB", 24, 43), ("LB", 30, 59),
        ("RCM", 45, 22), ("CM", 40, 34), ("LCM", 45, 46),
        ("RW", 62, 10), ("ST", 66, 34), ("LW", 62, 58),
    ),
    "4-2-3-1": (
        ("GK", 4, 34), ("RB", 30, 9), ("RCB", 24, 25), ("LCB", 24, 43), ("LB", 30, 59),
        ("RDM", 40, 27), ("LDM", 40, 41),
        ("RAM", 58, 13), ("CAM", 55, 34), ("LAM", 58, 55), ("ST", 68, 34),
    ),
    "3-5-2": (
        ("GK", 4, 34), ("RCB", 24, 20), ("CB", 22, 34), ("LCB", 24, 48),
        ("RWB", 44, 7), ("RCM", 44, 24), ("CM", 40, 34), ("LCM", 44, 44), ("LWB", 44, 61),
        ("RST", 65, 28), ("LST", 65, 40),
    ),
    "4-4-2": (
        ("GK", 4, 34), ("RB", 30, 9), ("RCB", 24, 25), ("LCB", 24, 43), ("LB", 30, 59),
        ("RM", 50, 10), ("RCM", 44, 27), ("LCM", 44, 41), ("LM", 50, 58),
        ("RST", 64, 28), ("LST", 64, 40),
    ),
}

_ROLES = {
    "GK": ROLE_GK,
    **dict.fromkeys(("RB", "LB", "RCB", "LCB", "CB", "RWB", "LWB"), ROLE_DEF),
    **dict.fromkeys(("RCM", "CM", "LCM", "RDM", "LDM", "RAM", "CAM", "LAM", "RM", "LM"), ROLE_MID),
    **dict.fromkeys(("RW", "LW", "ST", "RST", "LST"), ROLE_FWD),
}

_BENCH = (("GK", ROLE_GK), ("DEF", ROLE_DEF), ("DEF", ROLE_DEF), ("MID", ROLE_MID),
          ("MID", ROLE_MID), ("FWD", ROLE_FWD), ("FWD", ROLE_FWD))


def role(position: str) -> str:
    return _ROLES.get(position, position)


@dataclass(frozen=True, slots=True)
class Style:
    possession: float  # preference for short, patient passing
    directness: float  # preference for long, forward passes
    pressing: float  # intensity of pressure out of possession
    line_height: float  # how high the defensive line holds
    strength: float  # overall quality


@dataclass(frozen=True, slots=True)
class Player:
    id: str
    name: str
    shirt: int
    position: str
    passing: float
    finishing: float
    aggression: float  # tendency to commit fouls
    pace: float

    @property
    def role(self) -> str:
        return role(self.position)


@dataclass(frozen=True, slots=True)
class Club:
    code: str
    name: str
    colour: str
    formation: str
    style: Style
    players: tuple[Player, ...]  # the 11 starters in formation order, then the bench

    @property
    def starters(self) -> tuple[Player, ...]:
        return self.players[:11]

    @property
    def bench(self) -> tuple[Player, ...]:
        return self.players[11:]

    def player(self, player_id: str) -> Player:
        for p in self.players:
            if p.id == player_id:
                return p
        raise KeyError(player_id)


# code, name, colour, formation, (possession, directness, pressing, line_height, strength)
_LEAGUE = (
    ("AGA", "Ashgrove Athletic", "#1f6feb", "4-3-3", (0.80, 0.25, 0.80, 0.80, 0.85)),
    ("BRC", "Brackenridge City", "#d1242f", "4-2-3-1", (0.70, 0.35, 0.70, 0.70, 0.80)),
    ("CWR", "Calderwick Rovers", "#1a7f37", "4-4-2", (0.40, 0.70, 0.50, 0.40, 0.55)),
    ("DMU", "Dunmere United", "#8250df", "4-3-3", (0.65, 0.40, 0.65, 0.65, 0.75)),
    ("EHA", "Eastholm Albion", "#bf8700", "3-5-2", (0.55, 0.50, 0.60, 0.55, 0.60)),
    ("FVT", "Fernvale Town", "#0a7ea4", "4-4-2", (0.35, 0.75, 0.45, 0.35, 0.45)),
    ("GLH", "Glenhallow", "#cf222e", "4-2-3-1", (0.60, 0.45, 0.55, 0.60, 0.65)),
    ("HFW", "Hollinsfield Wanderers", "#6e7781", "4-4-2", (0.45, 0.60, 0.50, 0.45, 0.50)),
    ("IVC", "Ivorstone City", "#57606a", "4-3-3", (0.75, 0.30, 0.75, 0.75, 0.80)),
    ("KBF", "Kestrel Bay", "#0969da", "3-5-2", (0.50, 0.55, 0.55, 0.50, 0.55)),
    ("LKU", "Larkspur United", "#953800", "4-2-3-1", (0.55, 0.50, 0.60, 0.55, 0.60)),
    ("MLA", "Marlowe Athletic", "#116329", "4-3-3", (0.60, 0.45, 0.70, 0.65, 0.70)),
    ("NBR", "Norbeck Rovers", "#a40e26", "4-4-2", (0.40, 0.70, 0.55, 0.40, 0.45)),
    ("OHT", "Oakhaven Town", "#4d2d00", "4-2-3-1", (0.50, 0.55, 0.50, 0.50, 0.50)),
    ("PLC", "Pellingham City", "#0550ae", "4-3-3", (0.70, 0.35, 0.65, 0.70, 0.75)),
    ("QMF", "Quarrymoor", "#6639ba", "3-5-2", (0.45, 0.60, 0.65, 0.50, 0.50)),
    ("RHU", "Ravensholt United", "#24292f", "4-4-2", (0.40, 0.65, 0.45, 0.40, 0.40)),
    ("SMA", "Saltmere Albion", "#d4a72c", "4-2-3-1", (0.55, 0.45, 0.55, 0.55, 0.55)),
    ("TDA", "Thistledown Athletic", "#8c959f", "4-3-3", (0.60, 0.40, 0.60, 0.60, 0.65)),
    ("WVF", "Westerly Vale", "#2da44e", "4-4-2", (0.35, 0.75, 0.40, 0.35, 0.40)),
)

_FIRST_NAMES = (
    "Adem", "Bastian", "Callum", "Dario", "Emre", "Felix", "Goran", "Hugo", "Idris", "Jonah",
    "Kofi", "Lucas", "Mateo", "Nils", "Oscar", "Pavel", "Rafael", "Sami", "Tomas", "Umar",
    "Viktor", "Wes", "Yusuf", "Zeno", "Arlo", "Bram", "Cian", "Dmitri", "Eli", "Florin",
)
_SURNAME_HEADS = (
    "Ald", "Bren", "Cor", "Dal", "Ev", "Fal", "Gor", "Hal", "Ist", "Jor", "Kal", "Lun",
    "Mor", "Nev", "Ost", "Pra", "Quin", "Rud", "Sev", "Tor", "Ul", "Vas", "Wen", "Yor", "Zan",
)
_SURNAME_TAILS = (
    "anek", "berik", "dello", "ezar", "fordt", "holme", "ivic", "inni", "kova", "leigh",
    "mannis", "ovar", "sendt", "tano", "urza", "vanek", "wellby",
)


def _clip(value: float) -> float:
    return round(max(0.05, min(0.98, value)), 3)


def _attributes(rng: random.Random, player_role: str, strength: float) -> tuple[float, ...]:
    base = 0.35 + 0.5 * strength
    passing = base + {ROLE_GK: -0.15, ROLE_DEF: -0.05, ROLE_MID: 0.08, ROLE_FWD: 0.0}[player_role]
    finishing = base + {ROLE_GK: -0.4, ROLE_DEF: -0.25, ROLE_MID: -0.05, ROLE_FWD: 0.15}[player_role]
    aggression = 0.35 + {ROLE_GK: -0.2, ROLE_DEF: 0.15, ROLE_MID: 0.05, ROLE_FWD: -0.05}[player_role]
    pace = base + {ROLE_GK: -0.3, ROLE_DEF: -0.05, ROLE_MID: 0.0, ROLE_FWD: 0.1}[player_role]
    return tuple(_clip(v + rng.gauss(0, 0.07)) for v in (passing, finishing, aggression, pace))


def _make_club(code: str, name: str, colour: str, formation: str, style: tuple,
               used_names: set[str]) -> Club:
    rng = random.Random(f"club:{code}")
    style_obj = Style(*style)
    # Goalkeepers wear 1 and 13; outfield players draw from the rest.
    shirts = iter(rng.sample([n for n in range(2, 40) if n != 13], 16))
    slots = [(pos, role(pos)) for pos, _, _ in FORMATIONS[formation]] + list(_BENCH)
    players = []
    for i, (position, player_role) in enumerate(slots):
        if player_role == ROLE_GK:
            shirt = 1 if i == 0 else 13
        else:
            shirt = next(shirts)
        while True:
            full = f"{rng.choice(_FIRST_NAMES)} {rng.choice(_SURNAME_HEADS)}{rng.choice(_SURNAME_TAILS)}"
            if full not in used_names:
                used_names.add(full)
                break
        passing, finishing, aggression, pace = _attributes(rng, player_role, style_obj.strength)
        players.append(Player(f"{code}-{shirt}", full, shirt, position, passing, finishing, aggression, pace))
    return Club(code, name, colour, formation, style_obj, tuple(players))


@cache
def league() -> dict[str, Club]:
    """All 20 clubs, keyed by code. Deterministic: the same squads on every run."""
    used_names: set[str] = set()  # player names are unique across the whole league
    return {row[0]: _make_club(*row, used_names) for row in _LEAGUE}
