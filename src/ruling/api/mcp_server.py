"""The desk over the Model Context Protocol, so an assistant (GitHub Copilot, a Foundry agent,
Claude) can use it as a tool.

    POST /mcp   streamable HTTP, stateless, JSON responses

Tools: list_var_checks, explain_var_check, law_clause, similar_past_checks. A check started
here is a real desk check: it is measured, written and checked like any other, and nothing is
published until a person approves it on the desk.
"""

from __future__ import annotations

import asyncio

from mcp.server.mcpserver import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings

from ..laws.clauses import CLAUSES, EDITION

DESK = "https://ruling-api.proudsea-2ac99296.eastus2.azurecontainerapps.io"
WAIT = 80.0  # seconds a tool waits for a check to reach checked messages (the desk's deadline is 90 s)

INSTRUCTIONS = (
    "Ruling is a decision desk for VAR calls on synthetic football matches (fictional clubs and players). "
    "Use list_var_checks to see a match's VAR checks, explain_var_check to have the desk measure one from "
    "tracking data, cite the Law, compare precedent and write checked messages, law_clause for the IFAB "
    f"Laws of the Game {EDITION} as paraphrased by the desk, and similar_past_checks for how similar calls "
    "ended. Never present a decision as published unless its status says published: a person approves "
    "every message on the desk."
)


def _case_summary(c: dict) -> dict:
    v, law, ev, drafts = c.get("verdict") or {}, c.get("law") or {}, c.get("evidence") or {}, c.get("drafts") or {}
    return {
        "incident_id": c["incident_id"], "clock": c["clock"], "category": c["category"],
        "on_field": c["on_field"], "status": c["status"], "holding_line": c.get("holding"),
        "why_held": c.get("failure"),
        "decision": {"final": v.get("final_decision"), "review": v.get("review"), "card": v.get("card"),
                     "stadium_announcement": v.get("announced")} if v else None,
        "law": {"id": law.get("id"), "title": law.get("title"), "summary": law.get("summary"),
                "official_text": law.get("url")} if law else None,
        "measured_facts": ev.get("facts"),
        "precedent": c.get("precedent_line"),
        "checked_messages": {k: drafts.get(k) for k in ("match_centre", "stadium", "broadcaster", "fan")} if drafts else None,
        "checker": {"passed": (c.get("check") or {}).get("passed"), "claims_backed": len((c.get("check") or {}).get("claims") or [])},
        "desk": f"{DESK}/?seed={int(c['match_id'].split('-')[-1])}",
    }


def build(app) -> MCPServer:
    """The MCP server for this app; tools reach the live desk through `app.state`."""
    from fastapi import HTTPException

    from ..desk.packet import packet_for
    from . import limits, serialize
    from .app import DEMO_SEEDS
    from .app import _incident as find_incident
    from .app import _match

    def _incident(incident_id: str):
        try:
            return find_incident(incident_id)
        except HTTPException:
            raise ToolError(f"unknown incident {incident_id!r}; list_var_checks gives the ids") from None

    def _spend_model_budget() -> None:
        if app.state.limiter.allow("model-budget", *limits.MODEL_BUDGET):
            raise ToolError("The demo's hourly model budget is used up; try again later.")

    server = MCPServer(name="ruling", title="Ruling VAR decision desk", instructions=INSTRUCTIONS,
                       website_url=DESK, version="1.0")

    @server.tool(description="The VAR checks in one demo match (seeds 5001-5020): each incident's id, clock, "
                             "category and on-field decision. The correct outcome is never included.")
    def list_var_checks(seed: int = 5004) -> dict:
        if seed not in DEMO_SEEDS:
            raise ToolError(f"seed must be one of the demo matches {DEMO_SEEDS.start}-{DEMO_SEEDS.stop - 1}")
        m = serialize.match_summary(_match(seed))
        detail = serialize.match_detail(_match(seed))
        return {"match": m["id"], "home": m["home"]["name"], "away": m["away"]["name"], "score": m["score"],
                "incidents": [{k: i[k] for k in ("id", "clock", "category", "on_field")} for i in detail["incidents"]],
                "desk": f"{DESK}/?seed={seed}"}

    @server.tool(description="Run the desk on one VAR check (or return its finished case): the decision "
                             "measured from tracking data, the Law clause, precedent, and the four messages "
                             "after the checker agent. Takes up to about 30 seconds. Nothing is published "
                             "until a person approves it on the desk.")
    async def explain_var_check(incident_id: str) -> dict:
        _incident(incident_id)  # 404s on an unknown id
        stored = [c for c in await app.state.checks.store.cases(incident_id.rsplit(":", 2)[0])
                  if c["incident_id"] == incident_id and c["status"] in ("published", "held")]
        if stored:
            return _case_summary(stored[-1])
        _spend_model_budget()
        incident, m = _incident(incident_id)
        session = app.state.checks.start(packet_for(m, incident))
        waited = 0.0
        while not session.done and session.request_id is None and waited < WAIT:
            await asyncio.sleep(0.5)
            waited += 0.5
        if session.case is None:
            return {"incident_id": incident_id, "status": "working", "desk": f"{DESK}/?seed={m.seed}"}
        summary = _case_summary(serialize.case_dict(session.case))
        if session.request_id is not None:
            summary["status"] = "awaiting a person's approval on the desk"
        return summary

    @server.tool(description=f"A clause of the IFAB Laws of the Game {EDITION} as the desk paraphrases it, "
                             "with the criteria it applies and a link to the official text. Ids: "
                             + ", ".join(CLAUSES))
    def law_clause(clause_id: str) -> dict:
        c = CLAUSES.get(clause_id) or next((x for k, x in CLAUSES.items() if k.split("-")[0] == clause_id), None)
        if c is None:
            raise ToolError(f"unknown clause; try one of {', '.join(CLAUSES)}")
        return {"id": c.id, "title": c.title, "summary": c.summary, "criteria": list(c.criteria),
                "official_text": c.url, "edition": EDITION, "note": "a paraphrase, not the official wording"}

    @server.tool(description="How the most similar past checks in the desk's archive ended, for one VAR check "
                             "(semantic search over 487 archived checks with Foundry embeddings).")
    async def similar_past_checks(incident_id: str) -> dict:
        from ..desk import precedent
        from ..desk.assessor import assess
        from ..desk.evidence import gather

        incident, m = _incident(incident_id)
        _spend_model_budget()
        packet = packet_for(m, incident)
        evidence = gather(packet)
        verdict = assess(packet, evidence)
        p = await precedent.find(packet, evidence, verdict.final_decision)
        return {"incident_id": incident_id, "desk_decision": verdict.final_decision,
                "agreeing": p.agreeing, "of": sum(p.finals.values()), "finals": p.finals,
                "closest": list(p.similar)}

    return server


class _PerClientLimit:
    """ASGI wrapper: each client gets a fixed number of MCP requests per minute."""

    def __init__(self, inner, limiter, per_minute: int = 60):
        self.inner, self.limiter, self.per_minute = inner, limiter, per_minute

    async def __call__(self, scope, receive, send):
        from starlette.requests import Request
        from starlette.responses import JSONResponse

        from .limits import client_of

        if scope["type"] == "http" and scope["method"] == "POST":
            wait = self.limiter.allow(f"mcp:{client_of(Request(scope))}", self.per_minute, 60)
            if wait:
                await JSONResponse({"error": f"Too many requests; try again in {int(wait) + 1} s."}, status_code=429,
                                   headers={"Retry-After": str(int(wait) + 1)})(scope, receive, send)
                return
        await self.inner(scope, receive, send)


def routes(server: MCPServer, limiter) -> list:
    """The /mcp route, rate limited, to add to the FastAPI app (its session manager runs in the app's lifespan)."""
    from starlette.routing import Route

    # The desk is a public, read-mostly API, so the localhost-only DNS-rebinding check is off.
    inner = server.streamable_http_app(streamable_http_path="/mcp", stateless_http=True, json_response=True,
                                       transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False))
    return [Route(r.path, endpoint=_PerClientLimit(r.endpoint, limiter), methods=r.methods) for r in inner.routes]
