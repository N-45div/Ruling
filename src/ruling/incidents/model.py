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


# Incident categories
OFFSIDE = "offside"
PENALTY_CLAIM = "penalty_claim"  # a challenge in or near the penalty area
HANDBALL = "handball"  # the ball touches a defender's arm in their penalty area
HANDBALL_GOAL = "handball_goal"  # the ball touches an attacker's arm before a goal
RED_CARD = "red_card"  # a challenge that may deserve a sending-off


@dataclass(frozen=True, slots=True)
class Challenge:
    """What a referee weighs in a challenge, as read from tracking and contact data."""

    action: str  # tackle | trip | push | holding | charge | kick | strike
    contact: bool
    played_ball_first: bool
    attempt_to_play_ball: bool
    attacker_initiated: bool  # the attacker sought or created the contact
    studs_up: bool
    lunge: bool
    off_ground: bool  # one or both feet off the ground into the challenge
    late_s: float  # seconds after the ball had gone (0 if on time)
    speed_mps: float
    contact_height: str  # none | foot | ankle | shin | knee | thigh | upper_body | head


@dataclass(frozen=True, slots=True)
class HandballFacts:
    arm_away_m: float  # distance of the hand from the side of the body
    above_shoulder: bool
    moved_towards_ball: bool
    justified_by_movement: bool  # the arm position follows from the body's movement for that situation
    supporting_arm: bool  # the arm is on the ground supporting a fall
    off_own_body: bool  # the ball came off the player's own body or head first
    distance_m: float  # how far the ball travelled to the arm
    by_attacker: bool
    scorer: bool  # the attacker scored
    immediately_before_goal: bool
    goal_bound: bool  # the ball was heading into the goal


@dataclass(frozen=True, slots=True)
class DogsoFacts:
    distance_m: float  # from the offence to the centre of the goal
    towards_goal: bool  # the attacker's overall movement is towards the goal
    angle_deg: float  # between the attacker's direction and the line to goal
    control: str  # likely | unlikely: keeping or gaining control of the ball
    defenders_able: int  # defenders, besides the offender, able to intervene
    attackers_support: int  # other attackers in a position to continue the attack


@dataclass(frozen=True, slots=True)
class FoulSituation:
    kind: str  # the incident category
    attacking_team: str  # the team in possession
    attacks_right: bool
    offender: str
    victim: str | None
    point: tuple[float, float]  # absolute: the contact point, or where the ball touched the arm
    challenge: Challenge | None
    handball: HandballFacts | None
    dogso: DogsoFacts | None
    bodies: tuple[Body, ...]

    def body(self, player: str) -> Body:
        return next(b for b in self.bodies if b.player == player)


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
    team: str  # the team in possession whose goal or claim is under review
    event_index: int  # the event under review (the goal, the challenge, the handball)
    key_index: int  # the moment the decision turns on, e.g. the team-mate's pass
    subjective: bool
    clear_and_obvious: bool
    on_field: str
    law_decision: str
    var_review: str
    final: str
    announced: bool
    situation: OffsideSituation | FoulSituation
    ruling: dict  # the category's ruling as a dict


def incident_to_dict(incident: Incident) -> dict:
    data = asdict(incident)
    data["situation"]["bodies"] = [
        {**b, "parts": {k: list(v) for k, v in b["parts"].items()}} for b in data["situation"]["bodies"]
    ]
    return data


def incident_from_dict(data: dict) -> Incident:
    s = dict(data["situation"])
    s["bodies"] = tuple(
        Body(b["player"], b["team"], b["shirt"], b["role"], {k: tuple(v) for k, v in b["parts"].items()})
        for b in s["bodies"]
    )
    if data["category"] == OFFSIDE:
        s["ball"] = tuple(s["ball"])
        situation = OffsideSituation(**s)
    else:
        s["point"] = tuple(s["point"])
        for key, cls in (("challenge", Challenge), ("handball", HandballFacts), ("dogso", DogsoFacts)):
            s[key] = cls(**s[key]) if s[key] else None
        situation = FoulSituation(**s)
    return Incident(**{**data, "situation": situation})
