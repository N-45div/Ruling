"""Desk commands.

    ruling-desk precedents                    # build the precedent index from the archive (seeds 1-120)
    ruling-desk check 5004                    # run the first incident of seed 5004 through the desk
    ruling-desk check 5004 --category red_card --nth 0
"""

from __future__ import annotations

import argparse
import asyncio
import time

from ..sim.cli import match_for_seed
from ..sim.clubs import league
from . import precedent
from .packet import packet_for
from .workflow import precedent_line, run_check


def _print_case(case, seconds: float) -> None:
    p = case.packet
    clubs = league()
    print(f"{clubs[p.home].name} v {clubs[p.away].name}, {p.clock}: {p.category.replace('_', ' ')}"
          f" (on-field: {p.on_field})")
    for step in case.steps:
        print(f"  {step.agent:13} {step.seconds:6.2f}s  {step.note}")
    if case.evidence:
        print("Evidence:")
        for fact in case.evidence.facts:
            print(f"  - {fact}")
    if case.verdict:
        v = case.verdict
        print(f"Verdict: {v.review.replace('_', ' ')} -> {v.final_decision}, card {v.card}, Law {v.clause}"
              + (" (announced)" if v.announced else ""))
    line = precedent_line(case.precedent, case.verdict.final_decision) if case.verdict else None
    if line:
        print(f"Precedent: {line}" + (f"  [{case.consistency_flag}]" if case.consistency_flag else ""))
    if case.drafts and case.status == "published":
        d = case.drafts
        print(f"Match Centre: {d.match_centre}")
        print(f"Stadium:      {d.stadium or '(no announcement due)'}")
        for bullet in d.broadcaster:
            print(f"Broadcaster:  - {bullet}")
        print(f"Fan:          {d.fan}")
    if case.holding:
        print(f"Holding line: {case.holding}")
    print(f"Status: {case.status}, {case.revisions} rewrite(s), {case.tokens_in}+{case.tokens_out} tokens, "
          f"{seconds:.1f}s")


async def _check(seed: int, category: str | None, nth: int) -> None:
    match = match_for_seed(seed)
    incidents = [i for i in match.incidents if category is None or i.category == category]
    if not incidents:
        raise SystemExit(f"no {category or ''} incident in seed {seed}")
    started = time.perf_counter()
    case = await run_check(packet_for(match, incidents[nth]))
    _print_case(case, time.perf_counter() - started)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ruling-desk", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("precedents", help="build the precedent index from the archive")
    one = sub.add_parser("check", help="run one incident through the desk")
    one.add_argument("seed", type=int)
    one.add_argument("--category")
    one.add_argument("--nth", type=int, default=0)
    args = parser.parse_args(argv)
    if args.command == "precedents":
        count = asyncio.run(precedent.build_index())
        print(f"indexed {count} past checks at {precedent.INDEX}")
    else:
        asyncio.run(_check(args.seed, args.category, args.nth))


if __name__ == "__main__":
    main()
