"""Typed calls to the Foundry chat model through Microsoft Agent Framework."""

from __future__ import annotations

import time
from dataclasses import dataclass
from functools import cache
from typing import Any

from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureDeveloperCliCredential, ChainedTokenCredential, DefaultAzureCredential

from .. import settings


@dataclass(frozen=True, slots=True)
class Usage:
    seconds: float
    input_tokens: int
    output_tokens: int


@cache
def client() -> FoundryChatClient:
    # Locally: the developer's `azd auth login`. In Azure: the app's managed identity.
    credential = ChainedTokenCredential(AzureDeveloperCliCredential(), DefaultAzureCredential())
    return FoundryChatClient(project_endpoint=settings.foundry_endpoint(), model=settings.chat_model(),
                             credential=credential)


async def structured(name: str, instructions: str, prompt: str, schema: type, effort: str = "low") -> tuple[Any, Usage]:
    """Ask the model for an answer in `schema` (a pydantic model). Returns the parsed value and usage."""
    agent = client().as_agent(name=name, instructions=instructions,
                              default_options={"reasoning": {"effort": effort}, "response_format": schema})
    started = time.perf_counter()
    result = await agent.run(prompt)
    details = getattr(result, "usage_details", None) or {}
    usage = Usage(round(time.perf_counter() - started, 2), int(details.get("input_token_count", 0) or 0),
                  int(details.get("output_token_count", 0) or 0))
    value = result.value if getattr(result, "value", None) is not None else schema.model_validate_json(result.text)
    return value, usage
