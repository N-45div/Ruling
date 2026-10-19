"""Precedent: similar past VAR checks from the league archive, and how they were decided.

The archive is the precedent library (seeds 1-120, never the held-out set). Each past
check becomes a short case description, with player names removed so only the
situation counts, embedded with the Foundry embedding model. A new check is compared
with past checks of the same category; the desk reports how the closest ones ended and
whether its recommendation is consistent with them.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from functools import cache

from agent_framework.foundry import FoundryEmbeddingClient
from azure.identity.aio import AzureDeveloperCliCredential, ChainedTokenCredential, DefaultAzureCredential

from .. import settings
from ..sim.cli import SETS, match_for_seed
from .evidence import Evidence, gather
from .packet import CheckPacket, packet_for

INDEX = settings.REPO / "data" / "precedents" / "index.json"
_PLAYER = re.compile(r"\b[A-Z]{3} No\.\d+ [A-Z][a-z]+ [A-Z][a-z]+\b")


@dataclass(frozen=True, slots=True)
class PastCase:
    id: str
    match_id: str
    clock: str
    category: str
    on_field: str
    final: str
    reason: str
    text: str


@dataclass(frozen=True, slots=True)
class Precedent:
    similar: tuple[dict, ...]  # the closest past checks: id, clock, final, reason, similarity
    finals: dict  # final decision -> count among the closest checks
    agreeing: int  # closest checks that ended as the desk recommends
    consistent: bool  # the recommendation matches the most common past outcome


def case_text(packet: CheckPacket, evidence: Evidence) -> str:
    facts = " ".join(_PLAYER.sub("a player", f) for f in evidence.facts)
    return (f"{packet.category.replace('_', ' ')}; on-field decision {packet.on_field}; "
            f"Law {evidence.clause} {evidence.reason.replace('_', ' ')}. {facts}")


async def embed(texts: list[str]) -> list[list[float]]:
    credential = ChainedTokenCredential(AzureDeveloperCliCredential(), DefaultAzureCredential())
    client = FoundryEmbeddingClient(project_endpoint=settings.foundry_endpoint(),
                                    model=settings.setting("FOUNDRY_EMBEDDING_MODEL"), credential=credential)
    vectors: list[list[float]] = []
    try:
        for start in range(0, len(texts), 64):
            batch = await client.get_embeddings(texts[start:start + 64])
            vectors += [_unit(list(e.vector)) for e in batch]
    finally:
        await credential.close()
    return vectors


def _unit(v: list[float]) -> list[float]:
    norm = math.sqrt(sum(x * x for x in v)) or 1.0
    return [round(x / norm, 6) for x in v]


async def build_index(seeds=SETS["archive"]) -> int:
    cases: list[PastCase] = []
    for seed in seeds:
        match = match_for_seed(seed)
        for incident in match.incidents:
            packet = packet_for(match, incident)
            cases.append(PastCase(incident.id, match.id, packet.clock, incident.category, incident.on_field,
                                  incident.final, incident.ruling["reason"], case_text(packet, gather(packet))))
    vectors = await embed([c.text for c in cases])
    INDEX.parent.mkdir(parents=True, exist_ok=True)
    INDEX.write_text(json.dumps([{**asdict(c), "vector": v} for c, v in zip(cases, vectors)]), encoding="utf-8")
    load_index.cache_clear()
    return len(cases)


@cache
def load_index() -> tuple[tuple[PastCase, tuple[float, ...]], ...]:
    if not INDEX.exists():
        raise FileNotFoundError(f"No precedent index at {INDEX}; run `ruling-desk precedents`")
    rows = json.loads(INDEX.read_text(encoding="utf-8"))
    return tuple((PastCase(**{k: v for k, v in r.items() if k != "vector"}), tuple(r["vector"])) for r in rows)


def nearest(vector: list[float], category: str, k: int = 8) -> list[tuple[PastCase, float]]:
    scored = [(case, sum(a * b for a, b in zip(vector, v))) for case, v in load_index() if case.category == category]
    return sorted(scored, key=lambda pair: pair[1], reverse=True)[:k]


def summarize(neighbours: list[tuple[PastCase, float]], recommended: str) -> Precedent:
    finals: dict[str, int] = {}
    for case, _ in neighbours:
        finals[case.final] = finals.get(case.final, 0) + 1
    agreeing = finals.get(recommended, 0)
    most_common = max(finals.values(), default=0)
    similar = tuple({"id": c.id, "clock": c.clock, "final": c.final, "reason": c.reason, "similarity": round(s, 3)}
                    for c, s in neighbours[:3])
    return Precedent(similar, finals, agreeing, consistent=not neighbours or agreeing == most_common)


async def find(packet: CheckPacket, evidence: Evidence, recommended: str) -> Precedent:
    vector = (await embed([case_text(packet, evidence)]))[0]
    return summarize(nearest(vector, packet.category), recommended)
