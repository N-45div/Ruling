"""Where finished case files are kept: Cosmos DB in Azure, memory on a laptop."""

from __future__ import annotations

import os


class Store:
    async def save(self, case: dict) -> None:
        raise NotImplementedError

    async def cases(self, match_id: str | None = None) -> list[dict]:
        raise NotImplementedError


class MemoryStore(Store):
    def __init__(self):
        self._cases: dict[str, dict] = {}

    async def save(self, case: dict) -> None:
        self._cases[case["incident_id"]] = case

    async def cases(self, match_id: str | None = None) -> list[dict]:
        return [c for c in self._cases.values() if match_id is None or c["match_id"] == match_id]


def make_store() -> Store:
    if os.environ.get("COSMOS_ENDPOINT"):
        from .cosmos import CosmosStore

        return CosmosStore(os.environ["COSMOS_ENDPOINT"], os.environ.get("COSMOS_DATABASE", "ruling"))
    return MemoryStore()
