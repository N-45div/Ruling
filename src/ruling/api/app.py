"""The desk API.

    GET  /api/health
    GET  /api/matches                         demo matches (development seeds)
    GET  /api/matches/{seed}                  events, incidents (no ground truth), players
    GET  /api/matches/{seed}/frames/{index}   where all 22 players stand at an event
    GET  /api/incidents/{incident_id}         the check packet the desk works from
    GET  /api/drills                          failure drills a check can be run with
    POST /api/checks                          start a VAR check {"incident_id", "auto_approve", "drill"}
    GET  /api/checks/{check_id}               the case file so far
    GET  /api/checks/{check_id}/events        every agent step, live (server-sent events)
    POST /api/checks/{check_id}/decision      a person approves or holds the messages
    POST /api/checks/{check_id}/translate     the approved fan card in another language
    GET  /api/checks/{check_id}/announcement  the checked stadium announcement, spoken (audio/mpeg)
    GET  /api/checks/{check_id}/listen?language=  the published fan card read aloud, in the fan's language
    POST /api/checks/{check_id}/panel         the post-match panel's five votes on a published decision
    GET  /api/cases?match_id=               finished case files (the post-match review)
    POST /api/live                            replay a match through Event Hubs {"seed", "speed", "from_minute"}
    GET  /api/live                            feed state and recent events
    GET  /api/live/events                     the feed, live; VAR checks start the desk on their own
    POST /api/live/stop
    POST /api/live/stall                      a drill: the upstream feed freezes {"seconds"}
    POST /mcp                                 the desk as MCP tools (streamable HTTP; see mcp_server.py)

Requests that start work are rate limited per client, and model use has an hourly budget (limits.py).

Run locally: uv run uvicorn ruling.api.app:app --reload
"""

from __future__ import annotations

import json
import os
from contextlib import asynccontextmanager
from functools import lru_cache
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .. import settings
from ..desk import precedent
from ..sim import events as ev
from ..sim.cli import SETS, match_for_seed
from . import limits, mcp_server, serialize, telemetry
from .checks import Checks
from .live import LiveFeed
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
    app.state.tracing = telemetry.configure()
    app.state.checks = Checks(make_store())
    app.state.translations = {}  # (check_id, language) -> (text, verified)
    app.state.announcements = {}  # check_id -> mp3 bytes of the spoken stadium announcement
    app.state.panels_sitting = set()  # check_ids the post-match panel is reviewing right now
    app.state.listens = {}  # (check_id, language) -> mp3 bytes of the fan card read aloud
    app.state.live = LiveFeed(app.state.checks, os.environ.get("EVENTHUB_NAMESPACE"), os.environ.get("EVENTHUB_NAME"))
    app.state.live.start_consumer()
    try:
        app.state.precedents = len(precedent.load_index())
    except FileNotFoundError:
        app.state.precedents = 0  # the desk carries on without precedent
    app.state.limiter = LIMITER
    async with MCP.session_manager.run():
        yield
    await app.state.live.close()


app = FastAPI(title="Ruling", description="A decision desk for refereeing calls.", lifespan=lifespan)
LIMITER = limits.Limiter()


class StartCheck(BaseModel):
    incident_id: str
    auto_approve: bool = False
    drill: str | None = None  # a failure drill to inject (GET /api/drills)


class Translate(BaseModel):
    language: str  # es, hi, fr, pt


class StartFeed(BaseModel):
    seed: int
    speed: float = 30.0  # match seconds per real second
    from_minute: int = 0


class Stall(BaseModel):
    seconds: float = 15.0  # how long the upstream feed freezes (a drill)


class Decision(BaseModel):
    decision: str  # "approve", or anything else to hold


@app.get("/api/health")
async def health():
    try:
        model = settings.chat_model()
    except RuntimeError:  # no Foundry settings: matches still load, checks cannot run
        model = None
    return {"ok": True, "model": model, "precedents": app.state.precedents, "tracing": app.state.tracing,
            "store": type(app.state.checks.store).__name__}


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


@app.get("/api/drills")
async def drills():
    from ..desk.drills import DRILLS

    return [{"id": key, "label": label} for key, label in DRILLS.items()]


@app.post("/api/checks", status_code=202)
async def start_check(body: StartCheck, request: Request):
    from ..desk.drills import DRILLS, break_packet
    from ..desk.packet import packet_for

    if body.drill is not None and body.drill not in DRILLS:
        raise HTTPException(422, f"drills: {', '.join(DRILLS)}")
    incident, m = _incident(body.incident_id)
    # The tracking drills stop at intake, before any model call.
    limits.enforce(LIMITER, request, "check", uses_model=body.drill not in ("tracking_dropout", "player_missing"))
    packet = break_packet(packet_for(m, incident), body.drill)
    session = app.state.checks.start(packet, body.auto_approve, body.drill)
    return {"check_id": session.id, "drill": body.drill}


async def _stored(check_id: str) -> dict:
    """A finished case file from the store, for a check run before a restart or on another replica."""
    case = await app.state.checks.store.case(check_id)
    if case is None:
        raise HTTPException(404, "unknown check")
    return case


@app.get("/api/checks/{check_id}")
async def check(check_id: str):
    s = app.state.checks.sessions.get(check_id)
    if s is None:
        return {"check_id": check_id, "done": True, "awaiting_approval": False, "case": await _stored(check_id)}
    return {"check_id": s.id, "done": s.done, "awaiting_approval": s.request_id is not None,
            "case": serialize.case_dict(s.case) if s.case else None}


@app.get("/api/checks/{check_id}/events")
async def check_events(check_id: str):
    s = app.state.checks.sessions.get(check_id)
    stored = await _stored(check_id) if s is None else None

    async def stream():
        if stored:
            yield f"data: {json.dumps({'type': 'final', 'check_id': check_id, 'case': stored})}\n\n"
            return
        async for event in s.follow():
            yield ": ping\n\n" if event is None else f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/checks/{check_id}/decision", status_code=202)
async def decide(check_id: str, body: Decision):
    s = app.state.checks.sessions.get(check_id)
    if s is None:
        await _stored(check_id)  # 404 if it never existed
    if s is None or s.request_id is None:
        raise HTTPException(409, "this check is not waiting for approval")
    app.state.checks.decide(s, body.decision)
    return {"check_id": s.id, "decision": body.decision}


@app.post("/api/checks/{check_id}/translate")
async def translate(check_id: str, body: Translate, request: Request):
    from ..desk import communicator

    s = app.state.checks.sessions.get(check_id)
    if s is None:
        case = await _stored(check_id)
    else:
        case = serialize.case_dict(s.case) if s.case else {"status": None}
    if case["status"] != "published":
        raise HTTPException(409, "only a published fan card is translated")
    if body.language not in communicator.LANGUAGES:
        raise HTTPException(422, f"supported: {', '.join(communicator.LANGUAGES)}")
    key, cache = (check_id, body.language), app.state.translations
    if key not in cache:
        limits.enforce(LIMITER, request, "translate", uses_model=True)
        cache[key] = await communicator.translate(case["drafts"]["fan"], body.language)
    text, verified = cache[key]
    return {"language": body.language, "text": text, "verified": verified}


@app.get("/api/checks/{check_id}/announcement")
async def announcement(check_id: str, request: Request):
    from ..desk import speech

    s = app.state.checks.sessions.get(check_id)
    if s is None:
        case = await _stored(check_id)
    else:
        case = serialize.case_dict(s.case) if s.case else {"status": None}
    if case["status"] not in ("checked", "published"):
        raise HTTPException(409, "only a checked announcement is spoken")
    if not (case.get("drafts") or {}).get("stadium"):
        raise HTTPException(404, "no stadium announcement is due for this decision")
    cache = app.state.announcements
    if check_id not in cache:
        limits.enforce(LIMITER, request, "speech", uses_model=True)
        try:
            cache[check_id] = await speech.announce(case["drafts"]["stadium"])
        except Exception as exc:
            raise HTTPException(502, "the announcement could not be spoken; try again in a moment") from exc
    return Response(cache[check_id], media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=3600"})


@app.get("/api/checks/{check_id}/listen")
async def listen(check_id: str, request: Request, language: str = "en"):
    """The published fan card read aloud, in English or in a translation that kept every name and figure."""
    from ..desk import communicator, speech

    s = app.state.checks.sessions.get(check_id)
    if s is None:
        case = await _stored(check_id)
    else:
        case = serialize.case_dict(s.case) if s.case else {"status": None}
    if case["status"] != "published":
        raise HTTPException(409, "only a published fan card is read aloud")
    if language != "en" and language not in communicator.LANGUAGES:
        raise HTTPException(422, f"supported: en, {', '.join(communicator.LANGUAGES)}")
    key, audio = (check_id, language), app.state.listens
    if key not in audio:
        limits.enforce(LIMITER, request, "speech", uses_model=True)
        words, voice = case["drafts"]["fan"], "en"
        try:
            if language != "en":
                if key not in app.state.translations:
                    app.state.translations[key] = await communicator.translate(words, language)
                translated, verified = app.state.translations[key]
                if verified:  # an unverified translation stays in English, and so does its voice
                    words, voice = translated, language
            audio[key] = await speech.speak(words, voice)
        except Exception as exc:
            raise HTTPException(502, "the fan card could not be read aloud; try again in a moment") from exc
    return Response(audio[key], media_type="audio/mpeg", headers={"Cache-Control": "public, max-age=3600"})


async def convene_panel(case: dict) -> dict:
    """Convene the post-match panel on a published case file, and keep its votes with the case."""
    from ..desk import panel as kmi
    from ..desk.assessor import assess
    from ..desk.evidence import gather
    from ..desk.packet import packet_for

    incident, m = _incident(case["incident_id"])
    packet = packet_for(m, incident)  # the measurement is code, so it is rebuilt exactly
    evidence = gather(packet)
    votes = await kmi.convene(packet, evidence, assess(packet, evidence), case.get("precedent_line"))
    await app.state.checks.store.save({**case, "panel": votes})
    return votes


@app.post("/api/checks/{check_id}/panel")
async def panel(check_id: str, request: Request):
    """The post-match panel's votes on a published decision; convened once, then kept with the case file."""
    case = await app.state.checks.store.case(check_id)
    if case is None:
        s = app.state.checks.sessions.get(check_id)
        if s is None:
            raise HTTPException(404, "unknown check")
        case = {"check_id": check_id, **serialize.case_dict(s.case)} if s.case else {"status": None}
    if case["status"] != "published":
        raise HTTPException(409, "the panel reviews published decisions only")
    if case.get("panel"):
        return case["panel"]
    sitting = app.state.panels_sitting
    if check_id in sitting:
        raise HTTPException(409, "the panel is already reviewing this decision")
    limits.enforce(LIMITER, request, "panel", uses_model=True)
    sitting.add(check_id)
    try:
        return await convene_panel(case)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(502, "the panel could not sit; try again in a moment") from exc
    finally:
        sitting.discard(check_id)


@app.get("/api/cases")
async def cases(match_id: str | None = None):
    return await app.state.checks.store.cases(match_id)


@app.post("/api/live", status_code=202)
async def start_feed(body: StartFeed, request: Request):
    if not 1 <= body.speed <= 600:
        raise HTTPException(422, "speed must be between 1 and 600")
    match = _match(body.seed)
    limits.enforce(LIMITER, request, "feed")
    app.state.live.play(match, body.speed, body.from_minute)
    return app.state.live.state


@app.get("/api/live")
async def feed_state():
    return {**app.state.live.state, "recent": list(app.state.live.log)[-60:]}


@app.get("/api/live/events")
async def feed_events():
    async def stream():
        async for event in app.state.live.follow():
            yield ": ping\n\n" if event is None else f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/live/stop")
async def stop_feed():
    app.state.live.stop()
    return app.state.live.state


@app.post("/api/live/stall", status_code=202)
async def stall_feed(body: Stall, request: Request):
    if not app.state.live.state["running"]:
        raise HTTPException(409, "no match is playing")
    if not 1 <= body.seconds <= 60:
        raise HTTPException(422, "seconds must be between 1 and 60")
    limits.enforce(LIMITER, request, "feed")
    app.state.live.stall(body.seconds)
    return app.state.live.state


# The desk as MCP tools for assistants (see mcp_server.py); its session manager runs in the lifespan.
MCP = mcp_server.build(app)
app.router.routes.extend(mcp_server.routes(MCP, LIMITER))

if Path(WEB).is_dir():
    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
