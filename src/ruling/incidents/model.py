"""Data model for incidents: player bodies at a key moment and the situations built from them."""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ..sim import pitch

# Parts that count for offside: head, body and feet. Arms (from the bottom of the armpit) never count.
COUNTING_PARTS = (
    "head", "torso", "left_shoulder", "right_shoulder", "left_knee", "right_knee", "left_foot", "right_foot",
)
ARM_PARTS = ("left_arm", "right_arm")

# Kick types at the moment a team-mate plays the ball.
OPEN_PLAY, THROW_IN, CORNER, GOAL_KICK = "open_play", "throw_in", "corner", "goal_kick"
# How the assessed attacker became involved.
PLAYED_BALL = "played_ball"
LINE_OF_VISION = "line_of_vision"
CHALLENGE = "challenge"
CLOSE_BALL = "close_ball"
OBVIOUS_ACTION = "obvious_action"
NOT_INVOLVED = "none"
INTERFERING_WITH_OPPONENT = frozenset({LINE_OF_VISION, CHALLENGE, CLOSE_BALL, OBVIOUS_ACTION})
# What touched the ball between the team-mate's play and the attacker's involvement.
DELIBERATE_PLAY, DELIBERATE_SAVE, DEFLECTION, WOODWORK = "deliberate_play", "deliberate_save", "deflection", "woodwork"


@dataclass(frozen=True, slots=True)
class Body:
    """One player at a key moment. Part positions are absolute coordinates in metres."""

    player: str
    team: str
    shirt: int
    role: str
    parts: dict[str, tuple[float, float]]

    def depth(self, attacks_right: bool, parts: tuple[str, ...] = COUNTING_PARTS) -> tuple[str, float]:
        """The part furthest towards the goal attacked by a team attacking right (or left),
        with its x in that team's attacking frame."""
        best_part, best_x = "", float("-inf")
        for name in parts:
            if name in self.parts:
                x = self.parts[name][0] if attacks_right else pitch.LENGTH - self.parts[name][0]
                if x > best_x:
                    best_part, best_x = name, x
        return best_part, best_x

    @property
    def torso(self) -> tuple[float, float]:
        return self.parts["torso"]


@dataclass(frozen=True, slots=True)
class OffsideSituation:
    attacking_team: str
    attacks_right: bool
    ball: tuple[float, float]  # absolute, at the moment the team-mate plays the ball
    kick: str
    passer: str
    attacker: str  # the player being assessed
    involvement: str
    intervening: str | None
    bodies: tuple[Body, ...]  # every player on the pitch at that moment

    def body(self, player: str) -> Body:
        return next(b for b in self.bodies if b.player == player)

    def opponents(self) -> list[Body]:
        return [b for b in self.bodies if b.team != self.attacking_team]


@dataclass(frozen=True, slots=True)
class Incident:
    """A VAR-reviewable moment with its known correct outcome.

    `scenario`, `law_decision`, `ruling` and the review outcome are ground truth: the
    evaluation hides them from the desk, which sees only the match up to the check, the
    situation and the on-field decision.
    """

    id: str
    match_id: str
    category: str
    scenario: str
    period: int
    second: float
    team: str  # the team whose goal is under review
    shot_index: int  # the event under review
    key_index: int  # the moment the decision turns on, e.g. the team-mate's pass
    subjective: bool
    clear_and_obvious: bool
    on_field: str
    law_decision: str
    var_review: str
    final: str
    announced: bool
    situation: OffsideSituation
    ruling: dict  # the category's ruling, e.g. an OffsideRuling as a dict


def incident_to_dict(incident: Incident) -> dict:
    data = asdict(incident)
    data["situation"]["bodies"] = [
        {**b, "parts": {k: list(v) for k, v in b["parts"].items()}} for b in data["situation"]["bodies"]
    ]
    return data


def incident_from_dict(data: dict) -> Incident:
    s = dict(data["situation"])
    s["ball"] = tuple(s["ball"])
    s["bodies"] = tuple(
        Body(b["player"], b["team"], b["shirt"], b["role"], {k: tuple(v) for k, v in b["parts"].items()})
        for b in s["bodies"]
    )
    return Incident(**{**data, "situation": OffsideSituation(**s)})
