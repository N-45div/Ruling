"""Generate the seeded match sets defined in docs/eval-plan.md.

    ruling-sim generate dev            # seeds 5001-5020, for development
    ruling-sim generate archive        # seeds 1-120, the precedent library
    ruling-sim generate held-out --confirm-held-out   # seeds 9001-9080, evaluation only
    ruling-sim summary 5001            # one match, printed

Each match is written to <out>/<set>/<match id>/ as events.jsonl, incidents.jsonl and match.json.
Incidents carry ground truth: the evaluation must not show those fields to the desk.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from ..incidents.model import incident_to_dict
from .calibration import fixtures
from .clubs import league
from .engine import simulate
from .events import Match, write_events

SETS = {
    "dev": range(5001, 5021),
    "archive": range(1, 121),
    "held-out": range(9001, 9081),
}


def match_for_seed(seed: int) -> Match:
    clubs = league()
    (home, away, _), = fixtures([seed])
    return simulate(clubs[home], clubs[away], seed)


def write_match(match: Match, folder: Path) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    write_events(folder / "events.jsonl", match.events)
    with (folder / "incidents.jsonl").open("w", encoding="utf-8") as fh:
        for incident in match.incidents:
            fh.write(json.dumps(incident_to_dict(incident), separators=(",", ":")) + "\n")
    home_goals, away_goals = match.score()
    meta = {
        "id": match.id, "seed": match.seed, "home": match.home, "away": match.away,
        "score": [home_goals, away_goals],
        "home_lineup": match.home_lineup, "away_lineup": match.away_lineup,
        "events": len(match.events),
        "incidents": len(match.incidents),
    }
    (folder / "match.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")


def _generate(args: argparse.Namespace) -> None:
    if args.set == "held-out" and not args.confirm_held_out:
        raise SystemExit("The held-out set is for the final evaluation only; pass --confirm-held-out.")
    out = Path(args.out) / args.set
    for seed in SETS[args.set]:
        match = match_for_seed(seed)
        write_match(match, out / match.id)
    print(f"wrote {len(SETS[args.set])} matches to {out}")


def _summary(args: argparse.Namespace) -> None:
    match = match_for_seed(args.seed)
    clubs = league()
    home_goals, away_goals = match.score()
    print(f"{clubs[match.home].name} {home_goals}-{away_goals} {clubs[match.away].name}  ({match.id})")
    incidents = {i.event_index: i for i in match.incidents}
    for e in match.events:
        if e.result == "goal" or e.type in ("card", "penalty", "offside", "var_decision"):
            who = clubs[e.team].player(e.player).name if e.player else e.team
            line = f"  {e.clock:>8}  {e.type:12} {e.result:13} {who} ({e.team})"
            if e.type == "var_decision":
                incident = incidents[int(e.detail.rsplit(":", 1)[1])]
                ruling = incident.ruling
                margin = ruling.get("margin_m", ruling.get("area_margin_m"))
                margin = f", {margin * 100:+.0f} cm" if margin is not None and abs(margin) < 3 else ""
                line += (f"  [{incident.category}, on-field {incident.on_field}, {e.detail.split('|')[0]}:"
                         f" Law {ruling['clause']} {ruling['reason']}{margin}]")
            print(line)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="ruling-sim", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    gen = sub.add_parser("generate", help="write a seeded match set")
    gen.add_argument("set", choices=sorted(SETS))
    gen.add_argument("--out", default="data/generated")
    gen.add_argument("--confirm-held-out", action="store_true")
    gen.set_defaults(func=_generate)
    show = sub.add_parser("summary", help="print one match's key moments")
    show.add_argument("seed", type=int)
    show.set_defaults(func=_summary)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
