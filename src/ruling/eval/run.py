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
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

from .. import settings
from ..desk.packet import packet_for
from ..sim.cli import SETS, match_for_seed
from . import claims
from .arms import ARMS
from .scoring import expected, score, score_dict, summarize


async def evaluate(seeds, arm_names: list[str], concurrency: int, limit: int | None, audit_claims: bool = True):
    cases = []
    for seed in seeds:
        match = match_for_seed(seed)
        cases += [(incident, packet_for(match, incident)) for incident in match.incidents]
    cases = cases[:limit] if limit else cases
    gate = asyncio.Semaphore(concurrency)

    async def one(arm_name, incident, packet):
        async with gate:
            result = await ARMS[arm_name].run(packet)
            s = score(arm_name, incident, result)
            audit = None
            text = result.verdict.explanation if result.verdict else ""
            if audit_claims and text:
                try:
                    audit, _ = await claims.audit(packet, text)
                    s = replace(s, claims_scored=audit.scored, claims_unsupported=audit.unsupported)
                except Exception as exc:  # an audit failure is recorded, not hidden
                    s = replace(s, error=s.error or f"claim audit failed: {type(exc).__name__}")
            return arm_name, incident, result, s, audit

    results = await asyncio.gather(*(one(a, i, p) for i, p in cases for a in arm_names))
    records, scores = [], []
    for arm_name, incident, result, s, audit in results:
        scores.append(s)
        final, card = expected(incident)
        records.append({
            "arm": arm_name, "incident_id": incident.id, "category": incident.category,
            "scenario": incident.scenario, "on_field": incident.on_field,
            "expected": {"final": final, "card": card, "review": incident.var_review, "clause": incident.ruling["clause"]},
            "verdict": asdict(result.verdict) if result.verdict else None, "score": score_dict(s),
            "extra": result.extra, "claims": list(audit.claims) if audit else None,
        })
    return records, scores, len(cases)


def _commit() -> str:
    out = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=settings.REPO)
    return out.stdout.strip()


def _print(summary: dict) -> None:
    print(f"{'arm':20} {'n':>4} {'verdict':>8} {'contested':>11} {'law':>6} {'clause':>7} {'stale':>6}"
          f" {'unsupp':>7} {'sec':>6}")
    for arm, s in summary["arms"].items():
        c = s["contested"]
        unsupported = s.get("unsupported_claim_rate")
        print(f"{arm:20} {s['incidents']:>4} {s['verdict_ok']:>8.3f} {c['verdict_ok'] or 0:>6.3f} ({c['incidents']:>2})"
              f" {s['law_ok']:>6.3f} {s['clause_ok']:>7.3f} {s['stale_rate']:>6.3f}"
              f" {unsupported if unsupported is not None else float('nan'):>7.3f} {s['mean_seconds']:>6.1f}")
    for arm, by_subset in summary.get("difference", {}).items():
        for label, d in by_subset.items():
            print(f"difference ({label}): {d['comparison']} = {d['verdict_ok']:+.3f}, "
                  f"95% CI [{d['ci95'][0]:+.3f}, {d['ci95'][1]:+.3f}], n={d['pairs']}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ruling-eval", description=__doc__.splitlines()[0])
    parser.add_argument("--set", choices=sorted(SETS), default="dev")
    parser.add_argument("--arms", default="model_only,ruling")
    parser.add_argument("--no-claims", action="store_true", help="skip the claim audit")
    parser.add_argument("--limit", type=int)
    parser.add_argument("--concurrency", type=int, default=6)
    parser.add_argument("--out")
    parser.add_argument("--confirm-held-out", action="store_true")
    args = parser.parse_args(argv)
    if args.set == "held-out" and not args.confirm_held_out:
        raise SystemExit("The held-out set is for the final evaluation only; pass --confirm-held-out.")
    arm_names = [a.strip() for a in args.arms.split(",") if a.strip()]
    records, scores, n = asyncio.run(evaluate(SETS[args.set], arm_names, args.concurrency, args.limit,
                                              audit_claims=not args.no_claims))
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
