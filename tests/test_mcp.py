"""The desk's MCP tools, over the official MCP client in process. No model is called: the explain
test reads a finished case from the store."""

import asyncio
import json

from mcp import Client

from ruling.api.app import LIMITER, MCP, app
from ruling.api.checks import Checks
from ruling.api.store import MemoryStore


def _call(name, args=None):
    async def run():
        async with Client(MCP) as client:
            if name == "__list__":
                return await client.list_tools()
            return await client.call_tool(name, args or {})
    return asyncio.run(run())


def _payload(result):
    assert not result.is_error, result.content
    return result.structured_content or json.loads(result.content[0].text)


def setup_module():
    app.state.checks = Checks(MemoryStore())
    app.state.limiter = LIMITER


def test_the_five_tools_are_listed():
    names = {t.name for t in _call("__list__").tools}
    assert names == {"list_var_checks", "explain_var_check", "law_clause", "similar_past_checks", "post_match_panel"}


def test_a_match_lists_its_checks_without_the_truth():
    out = _payload(_call("list_var_checks", {"seed": 5004}))
    assert out["match"] == "NBR-FVT-5004" and len(out["incidents"]) == 4
    assert set(out["incidents"][0]) == {"id", "clock", "category", "on_field"}
    assert _call("list_var_checks", {"seed": 9001}).is_error  # the held-out set is never served


def test_a_law_clause_comes_with_its_criteria_and_the_official_link():
    out = _payload(_call("law_clause", {"clause_id": "11.2"}))
    assert out["title"] == "Offside offence" and out["criteria"] and out["official_text"].startswith("https://")
    assert _payload(_call("law_clause", {"clause_id": "12.3"}))["id"].startswith("12.3")
    assert _call("law_clause", {"clause_id": "99"}).is_error


def test_a_finished_case_is_explained_from_the_store():
    case = {"check_id": "abc", "incident_id": "NBR-FVT-5004:1044:offside", "match_id": "NBR-FVT-5004",
            "clock": "64:51", "category": "offside", "on_field": "goal", "status": "published", "holding": None,
            "failure": None, "verdict": {"final_decision": "no_goal", "review": "var_overturn", "card": "no_card",
                                         "announced": False},
            "law": {"id": "11.2", "title": "Offside offence", "summary": "…", "url": "https://example.org"},
            "evidence": {"facts": ["15 cm beyond the offside line."]}, "precedent_line": "8 of the 8 …",
            "drafts": {"match_centre": "m", "stadium": "", "broadcaster": ["a", "b", "c"], "fan": "f"},
            "check": {"passed": True, "claims": [{}, {}]}}
    asyncio.run(app.state.checks.store.save(case))
    out = _payload(_call("explain_var_check", {"incident_id": "NBR-FVT-5004:1044:offside"}))
    assert out["status"] == "published" and out["decision"]["final"] == "no_goal"
    assert out["checker"] == {"passed": True, "claims_backed": 2} and out["desk"].endswith("?seed=5004")
    unknown = _call("explain_var_check", {"incident_id": "nope"})
    assert unknown.is_error and "list_var_checks gives the ids" in unknown.content[0].text


def test_the_panel_needs_a_published_decision_and_keeps_its_votes():
    unpublished = _call("post_match_panel", {"incident_id": "NBR-FVT-5004:221:penalty_claim"})
    assert unpublished.is_error and "no published decision" in unpublished.content[0].text
    case = {"check_id": "def", "incident_id": "NBR-FVT-5004:425:offside", "match_id": "NBR-FVT-5004",
            "status": "published", "verdict": {"final_decision": "goal"},
            "panel": {"decision_correct": "5-0", "var_right": "5-0", "verdict": "decision upheld", "members": []}}
    asyncio.run(app.state.checks.store.save(case))
    out = _payload(_call("post_match_panel", {"incident_id": "NBR-FVT-5004:425:offside"}))
    assert out["decision_correct"] == "5-0" and out["desk_decision"] == "goal"
