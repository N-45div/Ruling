"""Stale-law detector (amendment 1 of docs/eval-plan.md).

Flags explanations that rely on wording removed from or changed in earlier editions of
the Laws. Pattern-based, so it under-counts paraphrases; a sample is checked by hand.
"""

from __future__ import annotations

import re

_NEGATION = re.compile(r"\b(not|no longer|isn't|is not|doesn't|does not|never)\b", re.I)
_PATTERNS = {
    # The "arm above shoulder level" criterion was removed in 2022/23.
    "handball_above_shoulder": re.compile(r"above (the )?shoulder", re.I),
    # The handball "creates a goal-scoring opportunity" offence was removed in 2022/23.
    "handball_creates_chance": re.compile(r"creat\w* (a )?goal[- ]scoring (opportunity|chance)", re.I),
    # In-area DOGSO with an attempt to play the ball has been a caution since 2016/17.
    "dogso_triple_punishment": re.compile(r"triple punishment|automatic(ally)? (a )?red", re.I),
    # A clearly wrong second caution is reviewable from 2026/27.
    "second_yellow_not_reviewable": re.compile(r"second (yellow|caution)[^.]*(not|cannot|can't) be review", re.I),
}
_DOGSO = re.compile(r"goal[- ]scoring opportunity|DOGSO", re.I)


def _sentences(text: str) -> list[str]:
    return [s for s in re.split(r"(?<=[.!?])\s+", text) if s]


def stale_citations(text: str, category: str) -> list[str]:
    hits = []
    for sentence in _sentences(text):
        for name, pattern in _PATTERNS.items():
            if not pattern.search(sentence):
                continue
            # "An arm above the shoulder is not automatically handball" is current Law, not stale.
            if name == "handball_above_shoulder" and _NEGATION.search(sentence):
                continue
            hits.append(name)
        # DOGSO considerations listed without the attackers added in 2026/27.
        if (category == "red_card" and _DOGSO.search(sentence) and re.search(r"defender", sentence, re.I)
                and not re.search(r"attacker", sentence, re.I)):
            hits.append("dogso_without_attackers")
    return sorted(set(hits))
