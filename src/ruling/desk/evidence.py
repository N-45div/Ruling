"""Evidence: rebuild the situation from a check packet and compute what the decision turns on.

Every number here comes from code: offside margins from body-part geometry, the contact
point's distance from the area line, force cues, the DOGSO considerations. The
borderline flag marks subjective calls close to a threshold, where an on-field decision
is not a clear and obvious error even if the evidence leans the other way.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from ..incidents import model as m
from ..laws import fouls, offside
from ..sim import pitch
from .packet import CheckPacket

# Offside rulings that turn on whether the player interfered with the goalkeeper.
_INVOLVEMENT = frozenset({"interfering_with_an_opponent", "not_involved"})


@dataclass(frozen=True, slots=True)
class Evidence:
    category: str
    law_decision: str
    clause: str
    reason: str
    card: str  # the sanction that follows a foul, or the card itself for a red-card check
    facts: tuple[str, ...]  # measured facts in plain words, each one checkable against `numbers`
    numbers: dict = field(default_factory=dict)
    borderline: bool = False
    borderline_reason: str | None = None


def situation_from_facts(category: str, facts: dict) -> m.OffsideSituation | m.FoulSituation:
    data = dict(facts)
    data["bodies"] = tuple(
        m.Body(b["player"], b["team"], b["shirt"], b["role"], {k: tuple(v) for k, v in b["parts"].items()})
        for b in data["bodies"]
    )
    if category == m.OFFSIDE:
        data["ball"] = tuple(data["ball"])
        return m.OffsideSituation(**data)
    data["point"] = tuple(data["point"])
    for key, cls in (("challenge", m.Challenge), ("handball", m.HandballFacts), ("dogso", m.DogsoFacts)):
        data[key] = cls(**data[key]) if data[key] else None
    return m.FoulSituation(**data)


def gather(packet: CheckPacket) -> Evidence:
    situation = situation_from_facts(packet.category, packet.facts)
    if packet.category == m.OFFSIDE:
        return _offside(packet, situation)
    return _foul(packet, situation)


def _name(packet: CheckPacket, pid: str | None) -> str:
    if not pid:
        return "unknown player"
    p = packet.players.get(pid)
    return f"{p['team']} No.{p['shirt']} {p['name']}" if p else pid


def _sight_distance(packet: CheckPacket, s: m.OffsideSituation) -> float | None:
    """Distance of the assessed attacker from the line between the shot and the goal (attacking frame)."""
    if packet.event["type"] != "shot":
        return None
    sx, sy = pitch.to_absolute(*packet.event["start"], s.attacks_right)
    ax, ay = pitch.to_absolute(*s.body(s.attacker).torso, s.attacks_right)
    gx, gy = pitch.LENGTH, pitch.CENTRE_Y
    dx, dy = gx - sx, gy - sy
    length = math.hypot(dx, dy) or 1.0
    return round(abs(dy * (ax - sx) - dx * (ay - sy)) / length, 2)


def distance_words(metres: float) -> str:
    """A distance in words: centimetres when small, metres otherwise."""
    cm = round(abs(metres) * 100)
    return f"{cm} cm" if cm < 100 else f"{abs(metres):.1f} m"


def _position_fact(packet: CheckPacket, s: m.OffsideSituation, r) -> str:
    who = _name(packet, s.attacker)
    if round(r.margin_m * 100) == 0:
        return f"At the moment of the pass, {who} was level with the offside line."
    where = "beyond" if r.margin_m > 0 else "behind"
    part = r.attacker_part.replace("_", " ")
    return f"At the moment of the pass, {who}'s {part} was {distance_words(r.margin_m)} {where} the offside line."


def _offside(packet: CheckPacket, s: m.OffsideSituation) -> Evidence:
    r = offside.judge(s)
    numbers = {"margin_m": r.margin_m, "line_x": r.line_x, "arm_beyond": r.arm_beyond}
    if r.reason == "restart_exempt":
        facts = [f"The ball came to {_name(packet, s.attacker)} directly from a {s.kick.replace('_', ' ')}."]
    else:
        line_setter = (f"{_name(packet, r.second_last)}, the second-last opponent" if r.second_last else "the ball")
        facts = [_position_fact(packet, s, r), f"The offside line was set by {line_setter}."]
        if r.arm_beyond:
            facts.append("Only an arm was beyond the line; arms are not counted for offside.")
        if s.involvement != m.PLAYED_BALL:
            facts.append(f"Involvement observed: {s.involvement.replace('_', ' ')}.")
        if s.intervening:
            facts.append(f"Between the pass and the goal the ball touched an opponent: {s.intervening.replace('_', ' ')}.")
    sight = _sight_distance(packet, s)
    numbers["sight_line_distance_m"] = sight
    borderline, why = False, None
    if s.involvement in (m.LINE_OF_VISION, m.NOT_INVOLVED) and r.reason in _INVOLVEMENT and sight is not None:
        facts.append(f"{_name(packet, s.attacker)} stood {sight} m from the goalkeeper's line of sight to the shot.")
        if 1.2 <= sight <= 3.6:
            borderline, why = True, "impact on the goalkeeper is debatable at this distance from the line of sight"
    decision = fouls.NO_GOAL if r.offside else fouls.GOAL
    return Evidence(m.OFFSIDE, decision, r.clause, r.reason, fouls.NO_CARD, tuple(facts), numbers, borderline, why)


def _area_fact(margin: float) -> str:
    if round(margin * 100) == 0:
        return "The point of contact was on the penalty-area line, which counts as inside."
    side = "inside" if margin > 0 else "outside"
    return f"The point of contact was {distance_words(margin)} {side} the penalty area."


def _challenge_facts(ch: m.Challenge, offender: str, victim: str) -> list[str]:
    if not ch.contact:
        return [f"There was no contact between {offender} and {victim}."]
    facts = [f"{offender} made contact with {victim} ({ch.action}, at the {ch.contact_height.replace('_', ' ')})."]
    cues = [c for c, on in (("studs showing", ch.studs_up), ("lunging", ch.lunge), ("off the ground", ch.off_ground)) if on]
    if ch.late_s:
        cues.append(f"{ch.late_s:.1f} s after the ball had gone")
    if cues:
        facts.append("Force cues: " + ", ".join(cues) + f"; speed {ch.speed_mps:.1f} m/s.")
    if ch.played_ball_first:
        facts.append(f"{offender} played the ball before the contact.")
    if ch.attacker_initiated:
        facts.append(f"{victim} moved into the contact.")
    return facts


def _handball_facts(hb: m.HandballFacts, who: str) -> list[str]:
    if hb.by_attacker:
        when = "immediately before they scored." if hb.immediately_before_goal else "earlier in the move; a team-mate scored."
        return [f"The ball touched {who}'s arm {when}"]
    shoulder = ", above the shoulder" if hb.above_shoulder else ""
    facts = [f"The ball struck {who}'s arm, held {hb.arm_away_m:.2f} m from the body{shoulder}."]
    cues = (("The arm moved towards the ball.", hb.moved_towards_ball),
            ("The arm was supporting a fall.", hb.supporting_arm),
            (f"The ball came off the player's own body from {hb.distance_m:.1f} m.", hb.off_own_body),
            ("The arm position follows from the body's movement.", hb.justified_by_movement))
    return facts + [cue for cue, on in cues if on]


def _dogso_fact(dg: m.DogsoFacts) -> str:
    direction = "towards" if dg.towards_goal else "away from"
    return (f"DOGSO considerations: {dg.distance_m:.1f} m from goal; movement {direction} goal "
            f"({dg.angle_deg:.0f} degrees off line); control {dg.control}; {dg.defenders_able} other defender(s) "
            f"able to intervene; {dg.attackers_support} supporting attacker(s).")


def _foul(packet: CheckPacket, s: m.FoulSituation) -> Evidence:
    r = fouls.judge(s)
    facts, numbers = [], {"area_margin_m": r.area_margin_m, "force": r.force}
    if r.area_margin_m is not None and s.kind != m.RED_CARD:
        facts.append(_area_fact(r.area_margin_m))
    if s.challenge:
        facts += _challenge_facts(s.challenge, _name(packet, s.offender), _name(packet, s.victim))
        numbers.update(speed_mps=s.challenge.speed_mps, late_s=s.challenge.late_s)
    if s.handball:
        facts += _handball_facts(s.handball, _name(packet, s.offender))
        numbers.update(arm_away_m=s.handball.arm_away_m, ball_distance_m=s.handball.distance_m)
    if s.dogso:
        facts.append(_dogso_fact(s.dogso))
        numbers.update(dogso_distance_m=s.dogso.distance_m, defenders_able=s.dogso.defenders_able)
    borderline, why = _foul_borderline(s)
    return Evidence(s.kind, r.decision, r.clause, r.reason, r.card, tuple(facts), numbers, borderline, why)


def _foul_borderline(s: m.FoulSituation) -> tuple[bool, str | None]:
    ch, hb = s.challenge, s.handball
    if s.kind == m.PENALTY_CLAIM and ch and ch.contact and not ch.attacker_initiated and ch.contact_height == "foot":
        return True, "light contact on the foot: a foul either way is defensible"
    if (s.kind == m.HANDBALL and hb and not (hb.moved_towards_ball or hb.supporting_arm or hb.off_own_body
                                             or hb.above_shoulder) and 0.28 <= hb.arm_away_m <= 0.42):
        return True, "the arm is close to the body: whether it made the body bigger is debatable"
    if (s.kind == m.RED_CARD and ch and ch.studs_up and ch.contact_height == "shin" and not ch.lunge
            and not ch.off_ground and 5.0 <= ch.speed_mps <= 7.0):
        return True, "studs on the shin at moderate speed: reckless or excessive is debatable"
    return False, None
