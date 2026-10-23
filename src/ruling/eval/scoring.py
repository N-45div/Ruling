"""Scoring against the pre-registered metrics in docs/eval-plan.md."""

from __future__ import annotations

import random
import re
from collections import defaultdict
from dataclasses import asdict, dataclass, field

from ..desk.assessor import Verdict, card_after
from ..incidents import model as m
from .readability import raw_artifacts
from .stale import stale_citations

ALLOWED = {
    m.OFFSIDE: ("goal", "no_goal"),
    m.HANDBALL_GOAL: ("goal", "no_goal"),
    m.PENALTY_CLAIM: ("penalty", "free_kick", "no_foul"),
    m.HANDBALL: ("penalty", "free_kick", "no_foul"),
    m.RED_CARD: ("red", "yellow", "no_card"),
}
# gpt-5-mini list price, USD per million tokens (Azure OpenAI global standard).
PRICE = {"input": 0.25, "output": 2.00}


@dataclass(frozen=True, slots=True)
class ArmResult:
    verdict: Verdict | None
    seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None
    extra: dict | None = None  # arm-specific detail, e.g. the desk's status and revisions


@dataclass(frozen=True, slots=True)
class Score:
    arm: str
    incident_id: str
    category: str
    contested: bool
    verdict_ok: bool  # primary: the right final decision and the right card
    final_ok: bool
    card_ok: bool
    review_ok: bool
    law_ok: bool  # the right Law number (11, 12, 14)
    clause_ok: bool  # the right clause (e.g. 11.2, 12.1, 12.3)
    stale: tuple[str, ...] = field(default_factory=tuple)
    raw: tuple[str, ...] = field(default_factory=tuple)  # raw data in the fan text (amendment 3)
    seconds: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    error: str | None = None
    claims_scored: int = 0  # fact and law claims in the fan explanation (claim audit)
    claims_unsupported: int = 0
    planted: bool = False  # the on-field call is wrong: the correct final decision differs from it
    flagged: bool = False  # the arm's final decision differs from the on-field call


def expected(incident: m.Incident) -> tuple[str, str]:
    return incident.final, card_after(incident.category, incident.final, incident.ruling.get("card", "no_card"))


def contested(incident: m.Incident) -> bool:
    return incident.on_field != incident.law_decision or not incident.clear_and_obvious


def _law_number(text: str) -> str | None:
    match = re.search(r"\d+", text or "")
    return match.group() if match else None


def _clause(text: str) -> str | None:
    match = re.search(r"\d+(\.\d+)?", text or "")
    return match.group() if match else None


def score(arm: str, incident: m.Incident, result: ArmResult) -> Score:
    final, card = expected(incident)
    v = result.verdict
    base = dict(arm=arm, incident_id=incident.id, category=incident.category, contested=contested(incident),
                seconds=result.seconds, input_tokens=result.input_tokens, output_tokens=result.output_tokens,
                error=result.error, planted=final != incident.on_field,
                flagged=v is not None and v.final_decision != incident.on_field)
    if v is None:
        return Score(verdict_ok=False, final_ok=False, card_ok=False, review_ok=False, law_ok=False,
                     clause_ok=False, **base)
    truth_clause = incident.ruling["clause"].split("-")[0]
    final_ok = v.final_decision == final and v.final_decision in ALLOWED[incident.category]
    card_ok = v.card == card
    return Score(
        verdict_ok=final_ok and card_ok, final_ok=final_ok, card_ok=card_ok,
        review_ok=v.review == incident.var_review,
        law_ok=_law_number(v.clause) == _law_number(truth_clause),
        clause_ok=_clause(v.clause) == _clause(truth_clause),
        stale=tuple(stale_citations(v.explanation, incident.category, v.final_decision)),
        raw=tuple(raw_artifacts(v.explanation)), **base,
    )


def _rate(scores: list[Score], key: str) -> float | None:
    return round(sum(getattr(s, key) for s in scores) / len(scores), 4) if scores else None


def _claim_rate(scores) -> float | None:
    scored = sum(s.claims_scored for s in scores)
    return round(sum(s.claims_unsupported for s in scores) / scored, 4) if scored else None


def _percentile(values: list[float], q: float) -> float | None:
    ordered = sorted(values)
    return round(ordered[min(len(ordered) - 1, int(q * len(ordered)))], 2) if ordered else None


def planted_errors(scores: list[Score]) -> dict:
    """Planted-error detection: an arm flags an incident when its final decision differs from the
    on-field call; a planted error is an incident whose correct final decision differs from it."""
    hits = sum(s.flagged and s.planted for s in scores)
    flagged, planted = sum(s.flagged for s in scores), sum(s.planted for s in scores)
    return {"planted": planted, "flagged": flagged, "caught": hits,
            "precision": round(hits / flagged, 4) if flagged else None,
            "recall": round(hits / planted, 4) if planted else None}


def cost_per_incident(scores: list[Score]) -> float | None:
    if not scores:
        return None
    usd = sum(s.input_tokens * PRICE["input"] + s.output_tokens * PRICE["output"] for s in scores) / 1e6
    return round(usd / len(scores), 5)


def metrics(rows: list[Score]) -> dict:
    """Every pre-registered metric for one set of scores (an arm, a category, or the contested subset)."""
    if not rows:
        return {"incidents": 0}
    seconds = [r.seconds for r in rows]
    return {
        "incidents": len(rows),
        **{k: _rate(rows, k) for k in ("verdict_ok", "final_ok", "card_ok", "review_ok", "law_ok", "clause_ok")},
        "stale_rate": round(sum(bool(r.stale) for r in rows) / len(rows), 4),
        "raw_data_rate": round(sum(bool(r.raw) for r in rows) / len(rows), 4),
        "unsupported_claim_rate": _claim_rate(rows),
        "explanations_with_unsupported": round(sum(r.claims_unsupported > 0 for r in rows) / len(rows), 4),
        "planted_errors": planted_errors(rows),
        "errors": sum(r.error is not None for r in rows),
        "mean_seconds": round(sum(seconds) / len(rows), 2),
        "median_seconds": _percentile(seconds, 0.5),
        "p90_seconds": _percentile(seconds, 0.9),
        "cost_usd_per_incident": cost_per_incident(rows),
        "tokens": {"input": sum(r.input_tokens for r in rows), "output": sum(r.output_tokens for r in rows)},
    }


def paired_bootstrap(a: list[bool], b: list[bool], resamples: int = 10_000, seed: int = 0) -> tuple[float, float, float]:
    """Mean difference b - a with a 95% percentile interval, resampling incidents with replacement."""
    rng = random.Random(seed)
    n = len(a)
    diffs = [int(y) - int(x) for x, y in zip(a, b)]
    means = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(resamples))
    return round(sum(diffs) / n, 4), round(means[int(0.025 * resamples)], 4), round(means[int(0.975 * resamples)], 4)


def paired_claim_bootstrap(pairs: list[tuple[Score, Score]], resamples: int = 10_000,
                           seed: int = 0) -> tuple[float, float, float] | None:
    """Unsupported-claim rate difference (second - first) with a 95% interval. Each rate is unsupported
    claims over scored claims, recomputed on every resample of incidents."""
    if not any(x.claims_scored for x, _ in pairs) or not any(y.claims_scored for _, y in pairs):
        return None
    rng, n = random.Random(seed), len(pairs)

    def diff(idx) -> float:
        rate = []
        for side in (0, 1):
            scored = sum(pairs[i][side].claims_scored for i in idx)
            rate.append(sum(pairs[i][side].claims_unsupported for i in idx) / scored if scored else 0.0)
        return rate[1] - rate[0]

    draws = sorted(diff([rng.randrange(n) for _ in range(n)]) for _ in range(resamples))
    return round(diff(range(n)), 4), round(draws[int(0.025 * resamples)], 4), round(draws[int(0.975 * resamples)], 4)


def summarize(scores: list[Score]) -> dict:
    by_arm: dict[str, list[Score]] = defaultdict(list)
    for s in scores:
        by_arm[s.arm].append(s)
    summary = {"arms": {}}
    for arm, rows in by_arm.items():
        summary["arms"][arm] = {
            **metrics(rows),
            "contested": metrics([r for r in rows if r.contested]),
            "by_category": {c: metrics([r for r in rows if r.category == c]) for c in sorted({r.category for r in rows})},
        }
    # Every other arm against the baseline: the model alone if it ran, else the first arm.
    arms = list(by_arm)
    baseline = "model_only" if "model_only" in by_arm else arms[0]
    base_rows = {r.incident_id: r for r in by_arm[baseline]}
    for arm in arms:
        if arm == baseline:
            continue
        pairs = [(base_rows[r.incident_id], r) for r in by_arm[arm] if r.incident_id in base_rows]
        for label, subset in (("all", pairs), ("contested", [p for p in pairs if p[0].contested])):
            if not subset:
                continue
            diff, low, high = paired_bootstrap([x.verdict_ok for x, _ in subset], [y.verdict_ok for _, y in subset])
            entry = {"comparison": f"{arm} - {baseline}", "verdict_ok": diff, "ci95": [low, high], "pairs": len(subset)}
            claims = paired_claim_bootstrap(subset)
            if claims:
                entry["unsupported_claim_rate"] = {"difference": claims[0], "ci95": [claims[1], claims[2]]}
            raw = paired_bootstrap([bool(x.raw) for x, _ in subset], [bool(y.raw) for _, y in subset])
            entry["raw_data_rate"] = {"difference": raw[0], "ci95": [raw[1], raw[2]]}
            summary.setdefault("difference", {}).setdefault(arm, {})[label] = entry
    # The pre-registered test: the full desk beats the model alone on verdict accuracy and on the
    # unsupported-claim rate, each 95% interval excluding zero.
    head = summary.get("difference", {}).get("ruling", {}).get("all")
    if baseline == "model_only" and head:
        claims = head.get("unsupported_claim_rate")
        summary["success"] = {"verdict": head["ci95"][0] > 0,
                              "unsupported_claims": bool(claims) and claims["ci95"][1] < 0}
        summary["success"]["met"] = all(summary["success"].values())
    return summary


def score_dict(s: Score) -> dict:
    return asdict(s)
