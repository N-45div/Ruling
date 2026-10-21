"""JSON views of matches, incidents and case files.

The public incident view never includes ground truth: no scenario, no Law decision, no
correct outcome. A case file is the desk's own work, so all of it can be shown.
"""

from __future__ import annotations

from dataclasses import asdict

from ..desk.packet import packet_dict, packet_for
from ..desk.workflow import CaseFile, precedent_line
from ..incidents import model as m
from ..sim import events as ev
from ..sim import pitch
from ..sim.clubs import league
from ..sim.shape import frame_at


def club(code: str) -> dict:
    c = league()[code]
    return {"code": c.code, "name": c.name, "colour": c.colour, "formation": c.formation}


def match_summary(match: ev.Match) -> dict:
    home, away = match.score()
    by_category: dict[str, int] = {}
    for incident in match.incidents:
        by_category[incident.category] = by_category.get(incident.category, 0) + 1
    return {"seed": match.seed, "id": match.id, "home": club(match.home), "away": club(match.away),
            "score": [home, away], "incidents": len(match.incidents), "by_category": by_category}


def event_row(e: ev.Event) -> dict:
    return {"i": e.index, "clock": e.clock, "period": e.period, "second": e.second, "team": e.team,
            "player": e.player, "type": e.type, "result": e.result, "start": [e.start_x, e.start_y],
            "end": [e.end_x, e.end_y], "detail": e.detail}


def incident_public(incident: m.Incident, match: ev.Match) -> dict:
    event = match.events[incident.event_index]
    return {"id": incident.id, "category": incident.category, "clock": event.clock, "period": event.period,
            "team": incident.team, "on_field": incident.on_field, "event_index": incident.event_index}


def match_detail(match: ev.Match) -> dict:
    players = {}
    for code in (match.home, match.away):
        for p in league()[code].players:
            players[p.id] = {"name": p.name, "shirt": p.shirt, "team": code, "role": p.role}
    return {**match_summary(match), "events": [event_row(e) for e in match.events],
            "incidents": [incident_public(i, match) for i in match.incidents], "players": players}


def frame(match: ev.Match, index: int) -> dict:
    f = frame_at(match, index)
    return {"index": index, "clock": match.events[index].clock, "ball": [f.ball_x, f.ball_y],
            "possession": f.possession, "players": [asdict(p) for p in f.players]}


def incident_detail(incident: m.Incident, match: ev.Match) -> dict:
    """What the desk sees: the check packet (positions, cues, the on-field call), never the truth."""
    return {**incident_public(incident, match), "packet": packet_dict(packet_for(match, incident))}


def case_dict(case: CaseFile) -> dict:
    p, e, v = case.packet, case.evidence, case.verdict
    offside_line = None
    if e and e.numbers.get("line_x") is not None:
        line = e.numbers["line_x"]
        offside_line = line if p.facts.get("attacks_right") else pitch.LENGTH - line  # absolute x
    return {
        "incident_id": p.incident_id, "category": p.category, "match_id": p.match_id, "clock": p.clock,
        "home": p.home, "away": p.away, "score": list(p.score), "team": p.team, "on_field": p.on_field,
        "status": case.status, "failure": case.failure, "holding": case.holding,
        "evidence": None if not e else {"facts": list(e.facts), "numbers": e.numbers, "borderline": e.borderline,
                                        "borderline_reason": e.borderline_reason, "law_decision": e.law_decision,
                                        "reason": e.reason, "offside_line_x": offside_line},
        "law": None if not case.law else asdict(case.law),
        "verdict": asdict(v) if v else None,
        "precedent": asdict(case.precedent) if case.precedent else None,
        "precedent_line": precedent_line(case.precedent, v.final_decision) if v else None,
        "consistency_flag": case.consistency_flag,
        "drafts": case.drafts.model_dump() if case.drafts else None,
        "check": None if not case.check else {"passed": case.check.passed, "issues": list(case.check.issues),
                                              "style": list(case.check.style), "claims": list(case.check.claims)},
        "check_history": case.check_history, "revisions": case.revisions,
        "steps": [asdict(s) for s in case.steps],
        "tokens": {"input": case.tokens_in, "output": case.tokens_out},
    }
