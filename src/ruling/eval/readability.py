"""Readability (amendment 3 of docs/eval-plan.md): raw data leaking into text written for fans.

Counts an explanation as unreadable for fans if it contains a raw player id (ABC-12), a
data field name in snake_case, a coordinate pair, or a bare true/false value.
"""

from __future__ import annotations

import re

ARTIFACTS = {
    "raw_player_id": re.compile(r"\b[A-Z]{3}-\d{1,2}\b"),
    "field_name": re.compile(r"\b[a-z]+_[a-z_]+\b"),
    "coordinates": re.compile(r"\[\s*-?\d+(\.\d+)?\s*,\s*-?\d+(\.\d+)?\s*\]"),
    "boolean": re.compile(r"\b(true|false)\b"),
}


def raw_artifacts(text: str) -> list[str]:
    return [name for name, pattern in ARTIFACTS.items() if pattern.search(text or "")]
