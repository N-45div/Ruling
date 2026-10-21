"""The desk API.

    GET  /api/health
    GET  /api/matches                         demo matches (development seeds)
    GET  /api/matches/{seed}                  events, incidents (no ground truth), players
    GET  /api/matches/{seed}/frames/{index}   where all 22 players stand at an event
    GET  /api/incidents/{incident_id}         the check packet the desk works from
    POST /api/checks                          start a VAR check {"incident_id", "auto_approve"}
    GET  /api/checks/{check_id}               the case file so far
    GET  /api/checks/{check_id}/events        every agent step, live (server-sent events)
    POST /api/checks/{check_id}/decision      a person approves or holds the messages
    GET  /api/cases?match_id=                 finished case files (the post-match review)

Run locally: uv run uvicorn ruling.api.app:app --reload
"""

from __future__ import annotations

import json
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import settings
from ..desk import precedent
from ..sim import events as ev
from ..sim.cli import SETS, match_for_seed
from . import serialize
from .checks import Checks
from .store import make_store

DEMO_SEEDS = SETS["dev"]  # never the held-out set
WEB = settings.REPO / "web"


@lru_cache(maxsize=64)
def _match(seed: int) -> ev.Match:
    if seed not in DEMO_SEEDS:
        raise HTTPException(404, f"match {seed} is not in the demo set")
    return match_for_seed(seed)


def _incident(incident_id: str):
    try:
        seed = int(incident_id.split(":")[0].split("-")[-1])
    except ValueError:
        raise HTTPException(404, "unknown incident") from None
    match = _match(seed)
    incident = next((i for i in match.incidents if i.id == incident_id), None)
    if incident is None:
        raise HTTPException(404, "unknown incident")
    return incident, match


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.checks = Checks(make_store())
    try:
        app.state.precedents = len(precedent.load_index())
    except FileNotFoundError:
        app.state.precedents = 0  # the desk carries on without precedent
    yield


app = FastAPI(title="Ruling", description="A decision desk for refereeing calls.", lifespan=lifespan)


class StartCheck(BaseModel):
    incident_id: str
    auto_approve: bool = False


class Decision(BaseModel):
    decision: str  # "approve", or anything else to hold


@app.get("/api/health")
async def health():
    try:
        model = settings.chat_model()
    except RuntimeError:  # no Foundry settings: matches still load, checks cannot run
        model = None
    return {"ok": True, "model": model, "precedents": app.state.precedents}


@app.get("/api/matches")
async def matches():
    return [serialize.match_summary(_match(seed)) for seed in DEMO_SEEDS]


@app.get("/api/matches/{seed}")
async def match(seed: int):
    return serialize.match_detail(_match(seed))


@app.get("/api/matches/{seed}/frames/{index}")
async def frame(seed: int, index: int):
    m = _match(seed)
    if not 0 <= index < len(m.events):
        raise HTTPException(404, "no such event")
    return serialize.frame(m, index)


@app.get("/api/incidents/{incident_id}")
async def incident(incident_id: str):
    return serialize.incident_detail(*_incident(incident_id))


@app.post("/api/checks", status_code=202)
async def start_check(body: StartCheck):
    from ..desk.packet import packet_for

    incident, m = _incident(body.incident_id)
    session = app.state.checks.start(packet_for(m, incident), body.auto_approve)
    return {"check_id": session.id}


def _session(check_id: str):
    session = app.state.checks.sessions.get(check_id)
    if session is None:
        raise HTTPException(404, "unknown check")
    return session


@app.get("/api/checks/{check_id}")
async def check(check_id: str):
    s = _session(check_id)
    return {"check_id": s.id, "done": s.done, "awaiting_approval": s.request_id is not None,
            "case": serialize.case_dict(s.case) if s.case else None}


@app.get("/api/checks/{check_id}/events")
async def check_events(check_id: str):
    s = _session(check_id)

    async def stream():
        async for event in s.follow():
            yield ": ping\n\n" if event is None else f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/checks/{check_id}/decision", status_code=202)
async def decide(check_id: str, body: Decision):
    s = _session(check_id)
    if s.request_id is None:
        raise HTTPException(409, "this check is not waiting for approval")
    app.state.checks.decide(s, body.decision)
    return {"check_id": s.id, "decision": body.decision}


@app.get("/api/cases")
async def cases(match_id: str | None = None):
    return await app.state.checks.store.cases(match_id)


if Path(WEB).is_dir():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
