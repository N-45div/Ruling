"""Case files in Azure Cosmos DB, signed in with the app's managed identity (no keys)."""

from __future__ import annotations

from azure.cosmos.aio import CosmosClient
from azure.identity.aio import DefaultAzureCredential

from .store import Store

CONTAINER = "cases"  # partition key /match_id; created by infra/data.bicep


class CosmosStore(Store):
    def __init__(self, endpoint: str, database: str):
        self._endpoint, self._database = endpoint, database
        self._container = None

    def _cases(self):
        if self._container is None:
            client = CosmosClient(self._endpoint, credential=DefaultAzureCredential())
            self._container = client.get_database_client(self._database).get_container_client(CONTAINER)
        return self._container

    async def save(self, case: dict) -> None:
        await self._cases().upsert_item({**case, "id": case["incident_id"]})

    async def cases(self, match_id: str | None = None) -> list[dict]:
        if match_id:
            items = self._cases().query_items("SELECT * FROM c WHERE c.match_id = @m",
                                              parameters=[{"name": "@m", "value": match_id}],
                                              partition_key=match_id)
        else:
            items = self._cases().query_items("SELECT * FROM c")
        return [{k: v for k, v in item.items() if not k.startswith("_")} async for item in items]
