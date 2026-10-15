# /// script
# requires-python = ">=3.12"
# dependencies = ["agent-framework-core", "agent-framework-foundry", "azure-identity"]
# ///
"""Make one real call to the Foundry project through Microsoft Agent Framework.

Run after `azd provision`:  uv run scripts/foundry_smoke.py
Settings come from the environment, or from the active azd environment if unset.
"""

import asyncio
import os
import shutil
import subprocess
import time

from agent_framework.foundry import FoundryChatClient
from azure.identity import AzureDeveloperCliCredential


def setting(name: str) -> str:
    value = os.environ.get(name)
    if value:
        return value
    azd = shutil.which("azd")
    if not azd:
        raise SystemExit(f"{name} is not set and azd is not on PATH")
    out = subprocess.run([azd, "env", "get-value", name], capture_output=True, text=True)
    if out.returncode != 0 or not out.stdout.strip():
        raise SystemExit(f"{name} is not set; run `azd provision` first")
    return out.stdout.strip()


async def main() -> None:
    client = FoundryChatClient(
        project_endpoint=setting("FOUNDRY_PROJECT_ENDPOINT"),
        model=setting("FOUNDRY_CHAT_MODEL"),
        credential=AzureDeveloperCliCredential(),
    )
    agent = client.as_agent(
        name="smoke",
        instructions="You answer in one short sentence.",
    )
    started = time.perf_counter()
    result = await agent.run("Which Law of the Game covers offside, and what is its number?")
    elapsed = time.perf_counter() - started
    print(f"model: {setting('FOUNDRY_CHAT_MODEL')}  latency: {elapsed:.1f}s")
    print(result.text)


if __name__ == "__main__":
    asyncio.run(main())
