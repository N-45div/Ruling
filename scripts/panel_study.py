"""The post-match panel on every checkable incident in the development matches.

Each incident's packet, evidence, verdict and precedent are rebuilt exactly as the desk builds them,
then the five-seat panel votes. The study reports how often the panel is unanimous, where it splits,
and whether it ever dissents on a factual call (it should not: those are measured).

    uv run python scripts/panel_study.py             -> results/panel-dev-<stamp>.json
"""

from __future__ import annotations

import asyncio
import json
import time
from collections import Counter
from datetime import datetime, timezone

from ruling import settings
from ruling.desk import panel, precedent
from ruling.desk.assessor import assess
from ruling.desk.evidence import gather
from ruling.desk.packet import gaps, packet_for
from ruling.desk.workflow import precedent_line
from ruling.sim.cli import SETS, match_for_seed

SUBJECTIVE = {"penalty_claim", "red_card", "handball"}  # judgement calls; offside and handball_goal are factual


async def one(m, incident, gate: asyncio.Semaphore) -> dict | None:
    packet = packet_for(m, incident)
    if gaps(packet):
        return None
    evidence = gather(packet)
    verdict = assess(packet, evidence)
    async with gate:
        try:
            p = await asyncio.wait_for(precedent.find(packet, evidence, verdict.final_decision), 30)
        except Exception:
            p = None  # the panel sits without precedent, as the desk does
        started = time.perf_counter()
        votes = await panel.convene(packet, evidence, verdict, precedent_line(p, verdict.final_decision))
    row = {"incident_id": incident.id, "category": packet.category, "on_field": packet.on_field,
           "law_decision": evidence.law_decision, "final": verdict.final_decision, "review": verdict.review,
           "borderline": evidence.borderline, "seconds": round(time.perf_counter() - started, 1), "panel": votes}
    print(f"{incident.id}: {votes['decision_correct']} / VAR {votes['var_right']} in {row['seconds']} s", flush=True)
    return row


async def main() -> None:
    gate = asyncio.Semaphore(2)  # two panels at a time, as the review pack convenes them
    matches = [match_for_seed(seed) for seed in SETS["dev"]]
    jobs = [one(m, incident, gate) for m in matches for incident in m.incidents]
    results = await asyncio.gather(*jobs, return_exceptions=True)
    failures = [f"{type(r).__name__}: {r}" for r in results if isinstance(r, BaseException)]
    rows = [r for r in results if isinstance(r, dict)]
    unanimous = [r for r in rows if r["panel"]["unanimous"]]
    split = [r for r in rows if not r["panel"]["unanimous"]]
    factual_dissent = [r for r in split if r["category"] not in SUBJECTIVE]
    questioned = [r for r in rows if r["panel"]["verdict"] != "decision upheld"]
    summary = {
        "checks": len(rows), "panel_failures": failures, "unanimous": len(unanimous), "split": len(split),
        "split_by_category": dict(Counter(r["category"] for r in split)),
        "split_on_factual_calls": len(factual_dissent),
        "questioned": [{"incident_id": r["incident_id"], "on_field": r["on_field"], "law_decision": r["law_decision"],
                        "final": r["final"], "borderline": r["borderline"], "tally": r["panel"]["decision_correct"],
                        "var_right": r["panel"]["var_right"]} for r in questioned],
        "close_calls": [{"incident_id": r["incident_id"], "tally": r["panel"]["decision_correct"],
                         "var_right": r["panel"]["var_right"]} for r in rows if r["borderline"]],
        "median_seconds": sorted(r["seconds"] for r in rows)[len(rows) // 2],
    }
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")
    out = settings.REPO / "results" / f"panel-dev-{stamp}.json"
    out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=1, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=1))
    print(f"-> {out}")


if __name__ == "__main__":
    asyncio.run(main())
