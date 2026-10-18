"""Run the evaluation on a seed set and write every record plus the summary.

    ruling-eval --set dev                          # development seeds 5001-5020
    ruling-eval --set dev --limit 10 --arms ruling_v0
    ruling-eval --set held-out --confirm-held-out  # the final evaluation only
"""

from __future__ import annotations

import argparse
import asyncio
import json
import subprocess
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .. import settings
from ..desk.packet import packet_for
from ..sim.cli import SETS, match_for_seed
from .arms import ARMS
from .scoring import expected, score, score_dict, summarize


async def evaluate(seeds, arm_names: list[str], concurrency: int, limit: int | None):
    cases = []
    for seed in seeds:
        match = match_for_seed(seed)
        cases += [(incident, packet_for(match, incident)) for incident in match.incidents]
    cases = cases[:limit] if limit else cases
    gate = asyncio.Semaphore(concurrency)

    async def one(arm_name, incident, packet):
        async with gate:
            return arm_name, incident, await ARMS[arm_name].run(packet)

    results = await asyncio.gather(*(one(a, i, p) for i, p in cases for a in arm_names))
    records, scores = [], []
    for arm_name, incident, result in results:
        s = score(arm_name, incident, result)
        scores.append(s)
        final, card = expected(incident)
        records.append({
            "arm": arm_name, "incident_id": incident.id, "category": incident.category,
            "scenario": incident.scenario, "on_field": incident.on_field,
            "expected": {"final": final, "card": card, "review": incident.var_review, "clause": incident.ruling["clause"]},
            "verdict": asdict(result.verdict) if result.verdict else None, "score": score_dict(s),
        })
    return records, scores, len(cases)


def _commit() -> str:
    out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=settings.REPO)
    return out.stdout.strip()


def _print(summary: dict) -> None:
    print(f"{'arm':12} {'n':>4} {'verdict':>8} {'contested':>10} {'law':>6} {'clause':>7} {'stale':>6} {'sec':>6}")
    for arm, s in summary["arms"].items():
        c = s["contested"]
        print(f"{arm:12} {s['incidents']:>4} {s['verdict_ok']:>8.3f} {c['verdict_ok'] or 0:>6.3f} ({c['incidents']:>2})"
              f" {s['law_ok']:>6.3f} {s['clause_ok']:>7.3f} {s['stale_rate']:>6.3f} {s['mean_seconds']:>6.1f}")
    for label, d in summary.get("difference", {}).items():
        print(f"difference ({label}): {d['comparison']} = {d['verdict_ok']:+.3f}, 95% CI [{d['ci95'][0]:+.3f}, {d['ci95'][1]:+.3f}], n={d['pairs']}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ruling-eval", description=__doc__.splitlines()[0])
    parser.add_argument("--set", choices=sorted(SETS), default="dev")
    parser.add_argument("--arms", default=",".join(ARMS))
    parser.add_argument("--limit", type=int)
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--out")
    parser.add_argument("--confirm-held-out", action="store_true")
    args = parser.parse_args(argv)
    if args.set == "held-out" and not args.confirm_held_out:
        raise SystemExit("The held-out set is for the final evaluation only; pass --confirm-held-out.")
    arm_names = [a.strip() for a in args.arms.split(",") if a.strip()]
    records, scores, n = asyncio.run(evaluate(SETS[args.set], arm_names, args.concurrency, args.limit))
    summary = summarize(scores)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")
    out = Path(args.out or settings.REPO / "results" / f"{args.set}-{stamp}.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    run_settings = {"set": args.set, "incidents": n, "arms": {a: {"effort": ARMS[a].effort} for a in arm_names},
                    "model": settings.chat_model(), "commit": _commit(), "utc": stamp}
    out.write_text(json.dumps({"settings": run_settings, "summary": summary, "records": records}, indent=1),
                   encoding="utf-8")
    _print(summary)
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
