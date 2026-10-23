"""Failure drills: break one check on purpose, on the real stack, and watch the desk hold.

Each drill injects a single fault. Everything else is the real desk: the real packet,
real model calls, the real checker and fail-safe. Drill checks are never stored as case
files, so they never reach the review pack.
"""

from __future__ import annotations

from dataclasses import replace

from ..incidents import model as m
from ..laws.offside import judge
from .communicator import DECISION_PHRASE, Drafts
from .evidence import situation_from_facts
from .packet import CheckPacket

DRILLS = {
    "tracking_dropout": "Tracking drops out: the freeze-frame has no players",
    "player_missing": "Tracking loses the player the decision turns on",
    "model_timeout": "The writing model times out on every attempt",
    "wrong_draft": "The writer states the opposite decision to the broadcaster",
}
DRILL_TIMEOUT = 0.05  # seconds the writing model gets in the timeout drill: every real call is cut off
OPPOSITE = {"goal": "no_goal", "no_goal": "goal", "penalty": "no_foul", "free_kick": "penalty", "no_foul": "penalty",
            "red": "no_card", "yellow": "red", "no_card": "red"}


def decisive_player(packet: CheckPacket) -> str | None:
    """The player the call turns on: the defender setting the offside line (or the attacker,
    when the ball sets it), or the player fouled (or the offender, for a handball)."""
    facts = packet.facts
    if packet.category == m.OFFSIDE:
        return judge(situation_from_facts(packet.category, facts)).second_last or facts.get("attacker")
    return facts.get("victim") or facts.get("offender")


def break_packet(packet: CheckPacket, drill: str | None) -> CheckPacket:
    bodies = packet.facts.get("bodies", [])
    if drill == "tracking_dropout":
        bodies = []
    elif drill == "player_missing":
        missing = decisive_player(packet)
        bodies = [b for b in bodies if b["player"] != missing]
    else:
        return packet
    return replace(packet, facts={**packet.facts, "bodies": bodies})


def wrong_line(final: str) -> str:
    return f"Decision: {DECISION_PHRASE[OPPOSITE[final]]}."


def plant(drafts: Drafts, final: str) -> Drafts:
    """The first broadcaster bullet states the opposite decision; the other channels are untouched,
    so only the checker reading the messages against the decision record can catch it."""
    return drafts.model_copy(update={"broadcaster": [wrong_line(final), *drafts.broadcaster[1:]]})


def caught(check_history: list[list[str]], final: str) -> bool:
    """Whether the checker has already flagged the planted line."""
    phrase = DECISION_PHRASE[OPPOSITE[final]].lower()
    return any(phrase in issue.lower() for issues in check_history for issue in issues
               if not issue.startswith("style:"))
