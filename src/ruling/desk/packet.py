"""What the desk sees when the VAR checks an incident.

A check packet holds the match up to the moment, the event under review, the observed
facts (freeze-frame bodies, challenge and handball cues) and the on-field decision.
Ground truth is never copied in: not the scenario, not the Law's decision, not the
ruling, not the correct outcome. Every arm of the evaluation receives the same packet.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

from ..incidents import model as m
from ..sim import events as ev
from ..sim.clubs import league
from ..sim.shape import lineups_at

# Incident fields that are ground truth and must never reach the desk.
HIDDEN = frozenset({"scenario", "law_decision", "ruling", "var_review", "final", "announced",
                    "subjective", "clear_and_obvious"})
RECENT_EVENTS = 12


@dataclass(frozen=True, slots=True)
class CheckPacket:
    incident_id: str
    category: str
    match_id: str
    home: str
    away: str
    score: tuple[int, int]  # goals that stood before the event under review
    period: int
    clock: str
    team: str  # the team in possession whose goal or claim is under review
    on_field: str
    event: dict  # the event under review
    recent: tuple[dict, ...]  # the events just before it, oldest first
    facts: dict  # the observed situation
    players: dict  # player id -> name, shirt, team, role
    on_pitch: dict = field(default_factory=dict)  # club code -> players on the pitch, from the match record


def _event(e: ev.Event) -> dict:
    return {"clock": e.clock, "team": e.team, "player": e.player, "type": e.type, "result": e.result,
            "start": [e.start_x, e.start_y], "end": [e.end_x, e.end_y], "detail": e.detail}


def _facts(situation: m.OffsideSituation | m.FoulSituation) -> dict:
    facts = asdict(situation)
    if isinstance(situation, m.FoulSituation):
        named = {situation.offender, situation.victim}
        facts["bodies"] = [b for b in facts["bodies"] if b["player"] in named]
    for b in facts["bodies"]:
        b["parts"] = {k: [round(c, 2) for c in v] for k, v in b["parts"].items()}
    return facts


def packet_for(match: ev.Match, incident: m.Incident) -> CheckPacket:
    event = match.events[incident.event_index]
    earlier = [g for g in match.goals() if g.index < incident.event_index]
    score = (sum(g.team == match.home for g in earlier), sum(g.team == match.away for g in earlier))
    recent = tuple(_event(e) for e in match.events[max(0, incident.event_index - RECENT_EVENTS):incident.event_index])
    facts = _facts(incident.situation)
    clubs = league()
    ids = {event.player, *(r["player"] for r in recent)}
    ids |= {facts.get(k) for k in ("attacker", "passer", "offender", "victim")}
    ids |= {b["player"] for b in facts["bodies"]}
    players = {}
    for pid in sorted(i for i in ids if i):
        p = clubs[pid.split("-")[0]].player(pid)
        players[pid] = {"name": p.name, "shirt": p.shirt, "team": pid.split("-")[0], "role": p.role}
    on_pitch = {code: len(team) for code, team in lineups_at(match, incident.event_index).items()}
    return CheckPacket(incident.id, incident.category, match.id, match.home, match.away, score, event.period,
                       event.clock, incident.team, incident.on_field, _event(event), recent, facts, players, on_pitch)


def packet_dict(packet: CheckPacket) -> dict:
    return asdict(packet)


def gaps(packet: CheckPacket) -> str | None:
    """What the tracking lacks for this decision, or None when the packet is complete.

    A player missing from the freeze-frame can move the offside line or lose the contact,
    and the measurement would still look exact, so an incomplete packet is never measured.
    """
    bodies = (packet.facts or {}).get("bodies")
    if not bodies:
        return "the packet has no tracked positions"
    tracked = {b["player"] for b in bodies}
    if packet.category == m.OFFSIDE:
        if packet.facts.get("attacker") not in tracked:
            return "tracking lost the player being assessed"
        defending = packet.away if packet.facts.get("attacking_team") == packet.home else packet.home
        expected, seen = packet.on_pitch.get(defending), sum(b["team"] == defending for b in bodies)
        if expected and seen < expected:
            return f"tracking has {seen} of {expected} {defending} players, so the offside line cannot be set"
        return None
    named = [packet.facts.get(role) for role in ("offender", "victim")]
    if any(pid and pid not in tracked for pid in named):
        return "tracking lost a player in the challenge"
    return None
