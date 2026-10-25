"""Checked words read aloud by Azure AI Speech: the referee's stadium announcement for the PA, and
the fan card in the fan's language.

Only text that has passed the checker (or a translation that kept every name and figure) is
spoken, word for word. Speech runs on the same Foundry (AI Services) resource as the models and
signs in the same way, with the developer's `azd auth login` locally and the app's managed
identity in Azure; no keys.
"""

from __future__ import annotations

import asyncio
import re
from functools import cache
from urllib.parse import urlparse
from xml.sax.saxutils import escape

import httpx
from azure.identity import AzureDeveloperCliCredential, ChainedTokenCredential, DefaultAzureCredential

from .. import settings
from .llm import with_retry

VOICE = "en-GB-RyanNeural"  # a calm British voice, as a stadium PA would carry it
# One neural voice per fan-card language: (SSML locale, voice).
VOICES = {
    "en": ("en-GB", VOICE), "es": ("es-ES", "es-ES-AlvaroNeural"), "hi": ("hi-IN", "hi-IN-MadhurNeural"),
    "fr": ("fr-FR", "fr-FR-HenriNeural"), "pt": ("pt-BR", "pt-BR-AntonioNeural"), "ar": ("ar-SA", "ar-SA-HamedNeural"),
    "id": ("id-ID", "id-ID-ArdiNeural"), "zh": ("zh-CN", "zh-CN-YunxiNeural"), "de": ("de-DE", "de-DE-ConradNeural"),
    "ja": ("ja-JP", "ja-JP-KeitaNeural"), "sw": ("sw-KE", "sw-KE-RafikiNeural"),
}
FORMAT = "audio-24khz-96kbitrate-mono-mp3"
SCOPE = "https://cognitiveservices.azure.com/.default"
TIMEOUT = 20.0

_REF = re.compile(r'^\s*REF:\s*"(?P<words>.+)"\s*$', re.S)


def spoken(stadium: str) -> str:
    """The words the referee says: the text inside REF: "...", or the draft itself if unwrapped."""
    match = _REF.match(stadium or "")
    return (match["words"] if match else stadium or "").strip()


def ssml(words: str, language: str = "en") -> str:
    locale, voice = VOICES[language]
    return f'<speak version="1.0" xml:lang="{locale}"><voice name="{voice}">{escape(words)}</voice></speak>'


def endpoint() -> str:
    """The resource's own text-to-speech endpoint, from the Foundry project endpoint's account name."""
    account = urlparse(settings.foundry_endpoint()).hostname.split(".")[0]
    return f"https://{account}.cognitiveservices.azure.com/tts/cognitiveservices/v1"


@cache
def _credential() -> ChainedTokenCredential:
    return ChainedTokenCredential(AzureDeveloperCliCredential(), DefaultAzureCredential())


async def announce(stadium: str) -> bytes:
    """MP3 audio of the stadium announcement. Raises ValueError when there is nothing to say."""
    words = spoken(stadium)
    if not words:
        raise ValueError("no stadium announcement is due")
    return await speak(words, "en")


async def speak(words: str, language: str = "en") -> bytes:
    """MP3 audio of `words` in the voice for `language` (a key of VOICES)."""
    token = await asyncio.to_thread(_credential().get_token, SCOPE)

    async def call() -> bytes:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            response = await client.post(endpoint(), content=ssml(words, language).encode("utf-8"), headers={
                "Authorization": f"Bearer {token.token}", "Content-Type": "application/ssml+xml",
                "X-Microsoft-OutputFormat": FORMAT, "User-Agent": "ruling"})
            response.raise_for_status()
            return response.content

    return await with_retry(call, attempts=3, timeout=TIMEOUT, backoff=2.0)
