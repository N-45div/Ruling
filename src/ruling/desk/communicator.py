"""The communicator: turn a verdict and its evidence into a short explanation for fans.

It may use only the computed facts and our paraphrase of the governing clause, so every
claim in the explanation can be traced to evidence or to the Law.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from ..laws.clauses import EDITION, clause
from . import llm
from .assessor import Verdict
from .evidence import Evidence
from .packet import CheckPacket

INSTRUCTIONS = (
    "You write the explanation fans see after a VAR check at a professional football match. "
    f"The Laws of the Game {EDITION} apply. Use only the facts and the Law summary you are given: "
    "do not add positions, distances, intentions or rules that are not in them. "
    "Say what was decided and why, in plain words, in at most 60 words. "
    "Name players as they appear in the facts and refer to them by name or role, not by pronoun. "
    "The facts come from tracking data: never say that video or a replay shows anything. "
    "Never criticise the referee."
)

_DECISIONS = {
    "goal": "the goal stands", "no_goal": "the goal is disallowed", "penalty": "a penalty kick",
    "free_kick": "a free kick outside the area", "no_foul": "no foul, play restarts without a penalty",
    "red": "a red card", "yellow": "a yellow card", "no_card": "no card",
}
_REVIEWS = {
    "check_complete": "the VAR checked and the on-field decision stands",
    "var_overturn": "the VAR corrected a factual decision",
    "on_field_review": "the referee reviewed the incident at the monitor and changed the decision",
}


# Shared with the checker: a close call that stands is explained in exactly these words.
CLOSE_CALL = "It was a close call, so the on-field decision stands: not a clear and obvious error."
# Each final decision in words, for holding lines and the checker's decision record.
DECISION_WORDS = {"goal": "the goal stands", "no_goal": "the goal is disallowed", "penalty": "a penalty is awarded",
                  "free_kick": "a free kick is awarded outside the area", "no_foul": "no foul", "red": "a red card",
                  "yellow": "a yellow card", "no_card": "no card"}
# Words the fan card must contain for each final decision (the checker looks for them).
DECISION_PHRASE = {"goal": "the goal stands", "no_goal": "the goal is disallowed", "penalty": "penalty",
                   "free_kick": "free kick", "no_foul": "no foul", "red": "red card", "yellow": "yellow card",
                   "no_card": "no card"}
_PRONOUNS = ((r"\bHis\b", "The player's"), (r"\bhis\b", "the player's"), (r"\bHe\b", "The player"),
             (r"\bhe\b", "the player"), (r"\bhimself\b", "the player"), (r"\bhim\b", "the player"),
             (r"\bher\b(?=\s+[a-z])", "the player's"), (r"\bShe\b", "The player"), (r"\bshe\b", "the player"),
             (r"\bher\b", "the player"))


def neutral(text: str) -> str:
    """Replace gendered pronouns with 'the player': the league's players are referred to by name or role."""
    for pattern, replacement in _PRONOUNS:
        text = re.sub(pattern, replacement, text)
    return text


class FanExplanation(BaseModel):
    explanation: str = Field(description="At most 60 words, for fans.")


def prompt_for(packet: CheckPacket, evidence: Evidence, verdict: Verdict) -> str:
    law = clause(verdict.clause)
    lines = [
        f"Incident: {packet.category.replace('_', ' ')} at {packet.clock}.",
        f"On-field decision: {_DECISIONS.get(packet.on_field, packet.on_field)}.",
        f"Outcome: {_REVIEWS[verdict.review]}; final decision: {_DECISIONS.get(verdict.final_decision)}"
        + (f", {_DECISIONS[verdict.card]}" if verdict.card != "no_card" and packet.category != "red_card" else "") + ".",
        "Facts:",
        *[f"- {f}" for f in evidence.facts],
        f"Law {law.id} ({law.law}, {law.title}): {law.summary}",
        *[f"- {c}" for c in law.criteria],
    ]
    if evidence.borderline and verdict.review == "check_complete":
        lines.append(f"Close call ({evidence.borderline_reason}). Explain it with this sentence and do not state "
                     f"the Law's conclusion either way: {CLOSE_CALL}")
    return "\n".join(lines)


async def explain(packet: CheckPacket, evidence: Evidence, verdict: Verdict) -> tuple[str, llm.Usage]:
    value, usage = await llm.structured("communicator", INSTRUCTIONS, prompt_for(packet, evidence, verdict),
                                        FanExplanation, effort="low")
    return value.explanation, usage


class Drafts(BaseModel):
    match_centre: str = Field(description="The league Match Centre post, at most 280 characters.")
    stadium: str = Field(description='The referee\'s stadium announcement as REF: "...", or "" if none is due.')
    broadcaster: list[str] = Field(description="Three short bullet points for a broadcaster's refereeing analyst.")
    fan: str = Field(description="The fan card, at most 60 words.")


CHANNEL_INSTRUCTIONS = INSTRUCTIONS + (
    " Write four messages about the same decision. "
    "match_centre: the league Match Centre post, at most 280 characters. If the decision changed, start with "
    "'#<HOMEAWAY> – <minute>' VAR OVERTURN' and say what the referee overturned; if it stood, say the referee's call "
    "was checked and confirmed by VAR. "
    "stadium: only if an announcement is due, the referee's words to the crowd as REF: \"After review, <what the "
    "review found, naming the player as <Club> No.<shirt>>. Final decision is <decision>.\" in at most 25 words, "
    "every angle-bracket part filled in and never a literal '...'; otherwise an empty string. "
    "broadcaster: exactly three bullets: the decision, the measured evidence it rests on, and the Law with any "
    "precedent. fan: at most 60 words."
)


def channel_prompt(packet: CheckPacket, evidence: Evidence, verdict: Verdict, clubs: dict[str, str],
                   precedent_line: str | None, feedback: list[str]) -> str:
    lines = [prompt_for(packet, evidence, verdict),
             f"Clubs: {packet.home} is {clubs[packet.home]}, {packet.away} is {clubs[packet.away]}. "
             f"Hashtag: #{packet.home}{packet.away}. Minute: {packet.clock.split(':')[0]}.",
             "A stadium announcement is due." if verdict.announced else "No stadium announcement is due."]
    if precedent_line:
        lines.append(f"Precedent: {precedent_line}")
    lines += [
        "Checklist (every draft is checked against it):",
        "- match_centre at most 280 characters; fan at most 60 words; broadcaster exactly three bullets.",
        f"- The fan card must contain the words \"{DECISION_PHRASE[verdict.final_decision]}\".",
        "- Use only figures that appear in the facts, written the same way.",
        "- Refer to players by name or role, never as he, him, his, she or her.",
        "- The facts come from tracking data: say 'tracking data', never video, replays or cameras.",
        "- Say who did what: the VAR checks; only for an on-field review does the referee review at the monitor.",
        "- stadium: " + ('REF: "After review, <what the review found>. Final decision is <decision>." in at most '
                         '25 words; it is read aloud to the crowd, so never write "...".'
                         if verdict.announced else "an empty string."),
    ]
    if feedback:
        lines.append("Your previous draft failed these checks; fix every one:")
        lines += [f"- {issue}" for issue in feedback]
    return "\n".join(lines)


LANGUAGES = {"es": "Spanish", "hi": "Hindi", "fr": "French", "pt": "Portuguese"}


class Translation(BaseModel):
    text: str


def _figures(text: str) -> list[str]:
    return sorted(re.findall(r"\d+(?:\.\d+)?", text))


async def translate(text: str, language: str) -> tuple[str, bool]:
    """Translate an approved fan card. Names, shirt numbers and every figure must survive
    unchanged; if they do not after one retry, the card stays in English (returns False)."""
    instructions = (f"Translate this explanation of a VAR decision into {LANGUAGES[language]} for football fans. "
                    "Keep every player name, club code, shirt number and figure exactly as written. "
                    "Add nothing and leave nothing out.")
    for _ in range(2):
        result, _usage = await llm.structured("translator", instructions, text, Translation, effort="minimal")
        if _figures(result.text) == _figures(text):
            return result.text, True
    return text, False


async def draft(packet: CheckPacket, evidence: Evidence, verdict: Verdict, clubs: dict[str, str],
                precedent_line: str | None = None, feedback: list[str] | None = None,
                effort: str = "low") -> tuple[Drafts, llm.Usage]:
    prompt = channel_prompt(packet, evidence, verdict, clubs, precedent_line, feedback or [])
    drafts, usage = await llm.structured("communicator", CHANNEL_INSTRUCTIONS, prompt, Drafts, effort=effort)
    return Drafts(match_centre=neutral(drafts.match_centre), stadium=neutral(drafts.stadium),
                  broadcaster=[neutral(b) for b in drafts.broadcaster], fan=neutral(drafts.fan)), usage
