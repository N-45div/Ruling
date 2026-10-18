"""What the desk sees when the VAR checks an incident.

A check packet holds the match up to the moment, the event under review, the observed
facts (freeze-frame bodies, challenge and handball cues) and the on-field decision.
Ground truth is never copied in: not the scenario, not the Law's decision, not the
ruling, not the correct outcome. Every arm of the evaluation receives the same packet.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

from ..incidents import model as m
from ..sim import events as ev
from ..sim.clubs import league

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
    return CheckPacket(incident.id, incident.category, match.id, match.home, match.away, score, event.period,
                       event.clock, incident.team, incident.on_field, _event(event), recent, facts, players)


def packet_dict(packet: CheckPacket) -> dict:
    return asdict(packet)
