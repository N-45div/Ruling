"""Clause catalogue: our paraphrase of the 2026/27 Laws, keyed by clause id.

Each entry is written in our own words and links to the official IFAB page. The
criteria lists are what the evidence tools and the checker test against.
"""

from __future__ import annotations

from dataclasses import dataclass

EDITION = "2026/27"
_IFAB = "https://www.theifab.com/laws/latest"


@dataclass(frozen=True, slots=True)
class Clause:
    id: str
    law: str
    title: str
    summary: str  # our paraphrase, never the official wording
    criteria: tuple[str, ...]
    url: str


CLAUSES: dict[str, Clause] = {c.id: c for c in (
    Clause(
        "11.1", "Law 11 Offside", "Offside position",
        "A player is in an offside position when a part of the head, body or feet is in the "
        "opponents' half and nearer to the opponents' goal line than both the ball and the "
        "second-last opponent. Being in that position is not an offence by itself.",
        (
            "Hands and arms are ignored for every player, goalkeepers included; the arm starts at the bottom of the armpit.",
            "The halfway line counts as the player's own half.",
            "Level with the second-last opponent, or with the last two, is not an offside position.",
            "The position is judged at the moment a team-mate plays or touches the ball (first point of contact).",
        ),
        f"{_IFAB}/offside/",
    ),
    Clause(
        "11.2", "Law 11 Offside", "Offside offence",
        "A player in an offside position when a team-mate plays or touches the ball is "
        "penalised only on becoming involved in active play.",
        (
            "(a) Interfering with play: playing or touching a ball passed or touched by a team-mate.",
            "(b) Interfering with an opponent: clearly obstructing their line of vision, challenging them for the ball, "
            "clearly attempting to play a close ball when this impacts them, or an obvious action that clearly impacts "
            "their ability to play the ball.",
            "(c) Gaining an advantage: playing the ball or interfering after it rebounds or is deflected off the "
            "goalpost, crossbar, a match official or an opponent, or after a deliberate save by an opponent.",
            "Receiving the ball from an opponent who deliberately played it (other than a deliberate save) does not "
            "gain an advantage.",
        ),
        f"{_IFAB}/offside/",
    ),
    Clause(
        "11.3", "Law 11 Offside", "No offside offence",
        "There is no offside offence if the player receives the ball directly from a goal kick, "
        "a throw-in or a corner kick.",
        ("Applies only to receiving the ball directly from one of these restarts.",),
        f"{_IFAB}/offside/",
    ),
    Clause(
        "11.4", "Law 11 Offside", "Offences and sanctions",
        "When an offside offence occurs, the referee awards an indirect free kick where the offence occurred.",
        ("The free kick goes to the defending team.",),
        f"{_IFAB}/offside/",
    ),
    Clause(
        "12.1", "Law 12 Fouls and misconduct", "Direct free kick offences",
        "A direct free kick is awarded when a player charges, jumps at, kicks, pushes, strikes, "
        "tackles or trips an opponent (or attempts to) in a way the referee considers careless, "
        "reckless or using excessive force, or holds or impedes an opponent with contact.",
        (
            "Careless: a lack of attention or consideration, or acting without precaution. No card.",
            "Reckless: acting with disregard for the danger to, or consequences for, the opponent. A caution.",
            "Using excessive force: far exceeding the necessary force and endangering the opponent. A sending-off.",
            "Contact offences are penalised where the contact happens.",
        ),
        f"{_IFAB}/fouls-and-misconduct/",
    ),
    Clause(
        "12.1-handball", "Law 12 Fouls and misconduct", "Handling the ball",
        "It is an offence if a player deliberately touches the ball with the hand or arm, touches it "
        "with a hand or arm that has made the body unnaturally bigger, or scores in the opponents' goal "
        "directly from the hand or arm or immediately after the ball touched it, even accidentally.",
        (
            "The arm starts at the bottom of the armpit.",
            "Unnaturally bigger: the arm's position is not a consequence of, or justifiable by, the body's movement in that situation.",
            "There is no automatic offence for an arm above the shoulder; that wording was removed in 2022/23.",
            "An accidental touch by an attacker that is followed by a team-mate scoring is not an offence.",
        ),
        f"{_IFAB}/fouls-and-misconduct/",
    ),
    Clause(
        "12.3-dogso", "Law 12 Fouls and misconduct", "Denying an obvious goal-scoring opportunity",
        "A player is sent off for denying an obvious goal-scoring opportunity to an opponent whose "
        "overall movement is towards the offender's goal, by an offence punishable by a free kick.",
        (
            "The referee considers the distance to goal, the general direction of play, the likelihood of keeping "
            "or gaining control of the ball, and the location and number of defenders and attackers (attackers added in 2026/27).",
            "Inside their own penalty area, when a penalty is awarded, the offender is cautioned instead if the offence "
            "was an attempt to play or challenge for the ball; holding, pulling, pushing or having no possibility to play "
            "the ball is still a sending-off.",
        ),
        f"{_IFAB}/fouls-and-misconduct/",
    ),
    Clause(
        "12.3-sfp", "Law 12 Fouls and misconduct", "Serious foul play",
        "A tackle or challenge that endangers the safety of an opponent or uses excessive force or "
        "brutality is serious foul play and is punished with a sending-off.",
        ("Lunging at an opponent from the front, side or behind with one or both legs, with excessive force or endangering safety, is serious foul play.",),
        f"{_IFAB}/fouls-and-misconduct/",
    ),
    Clause(
        "12.3-vc", "Law 12 Fouls and misconduct", "Violent conduct",
        "Using or attempting excessive force or brutality against an opponent when not challenging "
        "for the ball is violent conduct and is punished with a sending-off.",
        ("Deliberately striking an opponent on the head or face with the hand or arm is violent conduct unless the force was negligible.",),
        f"{_IFAB}/fouls-and-misconduct/",
    ),
    Clause(
        "14", "Law 14 The penalty kick", "When a penalty kick is awarded",
        "A penalty kick is awarded when a player commits a direct free kick offence inside their own "
        "penalty area.",
        ("The lines belong to the area they enclose: contact on the line is inside the penalty area.",),
        f"{_IFAB}/the-penalty-kick/",
    ),
    Clause(
        "VAR.scope", "VAR protocol", "Reviewable decisions",
        "The video assistant referee may only assist with a clear and obvious error or a serious "
        "missed incident in four match-changing situations: goal or no goal, penalty or no penalty, "
        "direct red card (including a clearly wrong second caution), and mistaken identity.",
        (
            "The referee always makes a decision first and always makes the final decision.",
            "For a goal, the attacking phase that led directly to it may be reviewed.",
        ),
        f"{_IFAB}/video-assistant-referee-var-protocol/",
    ),
    Clause(
        "VAR.review", "VAR protocol", "Factual and subjective decisions",
        "Factual decisions, such as offside position or whether an offence was inside the penalty "
        "area, are usually corrected by the video assistant referee alone. Subjective decisions, "
        "such as whether an offside player interfered with an opponent, normally lead to an "
        "on-field review by the referee at the monitor.",
        ("A subjective decision is changed only when the on-field call was a clear and obvious error.",),
        f"{_IFAB}/video-assistant-referee-var-protocol/",
    ),
)}


def clause(clause_id: str) -> Clause:
    return CLAUSES[clause_id]
