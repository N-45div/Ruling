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
                error=result.error)
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


def paired_bootstrap(a: list[bool], b: list[bool], resamples: int = 10_000, seed: int = 0) -> tuple[float, float, float]:
    """Mean difference b - a with a 95% percentile interval, resampling incidents with replacement."""
    rng = random.Random(seed)
    n = len(a)
    diffs = [int(y) - int(x) for x, y in zip(a, b)]
    means = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(resamples))
    return round(sum(diffs) / n, 4), round(means[int(0.025 * resamples)], 4), round(means[int(0.975 * resamples)], 4)


def summarize(scores: list[Score]) -> dict:
    by_arm: dict[str, list[Score]] = defaultdict(list)
    for s in scores:
        by_arm[s.arm].append(s)
    summary = {"arms": {}}
    for arm, rows in by_arm.items():
        cats = sorted({r.category for r in rows})
        summary["arms"][arm] = {
            "incidents": len(rows),
            **{k: _rate(rows, k) for k in ("verdict_ok", "final_ok", "card_ok", "review_ok", "law_ok", "clause_ok")},
            "contested": {"incidents": sum(r.contested for r in rows),
                          "verdict_ok": _rate([r for r in rows if r.contested], "verdict_ok")},
            "by_category": {c: {"incidents": sum(r.category == c for r in rows),
                                "verdict_ok": _rate([r for r in rows if r.category == c], "verdict_ok")} for c in cats},
            "stale_rate": round(sum(bool(r.stale) for r in rows) / len(rows), 4),
            "raw_data_rate": round(sum(bool(r.raw) for r in rows) / len(rows), 4),
            "unsupported_claim_rate": (round(sum(r.claims_unsupported for r in rows)
                                             / sum(r.claims_scored for r in rows), 4)
                                       if any(r.claims_scored for r in rows) else None),
            "explanations_with_unsupported": round(sum(r.claims_unsupported > 0 for r in rows) / len(rows), 4),
            "errors": sum(r.error is not None for r in rows),
            "mean_seconds": round(sum(r.seconds for r in rows) / len(rows), 2),
            "tokens": {"input": sum(r.input_tokens for r in rows), "output": sum(r.output_tokens for r in rows)},
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
            if subset:
                diff, low, high = paired_bootstrap([x.verdict_ok for x, _ in subset], [y.verdict_ok for _, y in subset])
                summary.setdefault("difference", {}).setdefault(arm, {})[label] = {
                    "comparison": f"{arm} - {baseline}", "verdict_ok": diff, "ci95": [low, high], "pairs": len(subset)}
    return summary


def score_dict(s: Score) -> dict:
    return asdict(s)
