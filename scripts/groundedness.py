"""Groundedness of the fan explanations, judged by Azure AI Foundry's groundedness evaluator.

An independent judge alongside our own claim audit (docs/eval-plan.md, amendment 4: exploratory).
Each explanation is scored 1-5 against the same record the claim audit uses: the clubs, the raw
check data, the measured facts and the Law summary. Each arm's run is logged to the Foundry project.

    uv run --group eval python scripts/groundedness.py run results/held-out-<stamp>.json --arm model_only
    uv run --group eval python scripts/groundedness.py run results/held-out-<stamp>.json --arm ruling
    uv run --group eval python scripts/groundedness.py compare results/held-out-<stamp>.json

One arm per process: a second logged run in the same process stalls in the evaluation SDK.
"""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

from ruling import settings


def _out(path: Path, arm: str, suffix: str) -> Path:
    return path.with_name(f"{path.stem}.groundedness-{arm}{suffix}")


def rows(results: dict, arm: str, limit: int | None) -> list[dict]:
    from ruling.desk.packet import packet_for
    from ruling.eval.claims import record
    from ruling.sim.cli import match_for_seed

    matches, out = {}, []
    for r in results["records"]:
        text = (r.get("verdict") or {}).get("explanation")
        if r["arm"] != arm or not text:
            continue
        seed = int(r["incident_id"].split(":")[0].split("-")[-1])
        match = matches.setdefault(seed, match_for_seed(seed))
        incident = next(i for i in match.incidents if i.id == r["incident_id"])
        out.append({"incident_id": r["incident_id"], "category": r["category"], "response": text,
                    "context": record(packet_for(match, incident))})
    return out[:limit] if limit else out


def run(path: Path, arm: str, limit: int | None, upload: bool) -> None:
    from azure.ai.evaluation import AzureOpenAIModelConfiguration, GroundednessEvaluator, evaluate
    from azure.identity import AzureDeveloperCliCredential, ChainedTokenCredential, DefaultAzureCredential

    results = json.loads(path.read_text(encoding="utf-8"))
    credential = ChainedTokenCredential(AzureDeveloperCliCredential(), DefaultAzureCredential())
    config = AzureOpenAIModelConfiguration(
        azure_endpoint=f"https://{settings.setting('FOUNDRY_ACCOUNT_NAME')}.openai.azure.com/",
        azure_deployment=settings.chat_model(), api_version="2025-04-01-preview")
    data = _out(path, arm, ".jsonl")
    data.write_text("\n".join(json.dumps(r) for r in rows(results, arm, limit)), encoding="utf-8")
    outcome = evaluate(
        data=str(data),
        evaluators={"groundedness": GroundednessEvaluator(config, credential=credential, is_reasoning_model=True)},
        evaluator_config={"groundedness": {"column_mapping": {"response": "${data.response}",
                                                              "context": "${data.context}"}}},
        evaluation_name=f"ruling {results['settings']['set']} groundedness: {arm}",
        azure_ai_project=settings.foundry_endpoint() if upload else None,
        output_path=str(_out(path, arm, ".out.json")))
    print(arm, outcome["metrics"], outcome.get("studio_url"))


def bootstrap(diffs: list[float], resamples: int = 10_000, seed: int = 0) -> tuple[float, float, float]:
    rng, n = random.Random(seed), len(diffs)
    means = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(resamples))
    return round(sum(diffs) / n, 3), round(means[int(0.025 * resamples)], 3), round(means[int(0.975 * resamples)], 3)


def compare(path: Path, arms: list[str]) -> None:
    summary, scores = {"results": path.name, "judge": settings.chat_model(), "arms": {}}, {}
    for arm in arms:
        outcome = json.loads(_out(path, arm, ".out.json").read_text(encoding="utf-8"))
        per = {row["inputs.incident_id"]: row.get("outputs.groundedness.groundedness") for row in outcome["rows"]}
        scores[arm] = {k: v for k, v in per.items() if isinstance(v, (int, float))}
        values = list(scores[arm].values())
        summary["arms"][arm] = {
            "explanations": len(per), "scored": len(values),
            "mean": round(sum(values) / len(values), 3) if values else None,
            "pass_rate": round(sum(v >= 3 for v in values) / len(values), 4) if values else None,
            "studio_url": outcome.get("studio_url")}
    if len(arms) == 2:
        both = sorted(set(scores[arms[0]]) & set(scores[arms[1]]))
        diff = bootstrap([scores[arms[1]][i] - scores[arms[0]][i] for i in both])
        summary["difference"] = {"comparison": f"{arms[1]} - {arms[0]}", "mean": diff[0],
                                 "ci95": [diff[1], diff[2]], "pairs": len(both)}
    out = path.with_name(f"{path.stem}.groundedness.json")
    out.write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(json.dumps(summary, indent=1))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    one = sub.add_parser("run", help="judge one arm's explanations and log the run to Foundry")
    one.add_argument("results")
    one.add_argument("--arm", required=True)
    one.add_argument("--limit", type=int)
    one.add_argument("--no-upload", action="store_true", help="keep the run out of the Foundry project")
    both = sub.add_parser("compare", help="summarise the judged arms and their paired difference")
    both.add_argument("results")
    both.add_argument("--arms", default="model_only,ruling")
    args = parser.parse_args()
    if args.command == "run":
        run(Path(args.results), args.arm, args.limit, not args.no_upload)
    else:
        compare(Path(args.results), [a.strip() for a in args.arms.split(",")])


if __name__ == "__main__":
    main()
