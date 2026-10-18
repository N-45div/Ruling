"""Runtime settings, read from the environment or, if unset, from the active azd environment."""

from __future__ import annotations

import os
import shutil
import subprocess
from functools import cache
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]


@cache
def setting(name: str) -> str:
    value = os.environ.get(name)
    if value:
        return value
    azd = shutil.which("azd") or str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Azure Dev CLI" / "azd.exe")
    out = subprocess.run([azd, "env", "get-value", name], capture_output=True, text=True, cwd=REPO)
    if out.returncode != 0 or not out.stdout.strip():
        raise RuntimeError(f"{name} is not set; run `azd provision` or export it")
    return out.stdout.strip()


def foundry_endpoint() -> str:
    return setting("FOUNDRY_PROJECT_ENDPOINT")


def chat_model() -> str:
    return setting("FOUNDRY_CHAT_MODEL")
