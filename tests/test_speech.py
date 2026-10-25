import pytest

from ruling.desk import speech


def test_only_the_referees_words_are_spoken():
    assert speech.spoken('REF: "Fernvale Town No.9 fouled the attacker. Final decision is a penalty kick."') == \
        "Fernvale Town No.9 fouled the attacker. Final decision is a penalty kick."
    assert speech.spoken("Final decision: goal.") == "Final decision: goal."
    assert speech.spoken("") == ""


def test_the_words_are_escaped_into_ssml():
    body = speech.ssml('Norbeck & Rovers <No.4> "offside"')
    assert "Norbeck &amp; Rovers &lt;No.4&gt;" in body
    assert body.startswith('<speak version="1.0" xml:lang="en-GB"><voice name="en-GB-RyanNeural">')


def test_speech_uses_the_foundry_resource_itself(monkeypatch):
    monkeypatch.setattr(speech.settings, "foundry_endpoint",
                        lambda: "https://ruling-ai-abc123.services.ai.azure.com/api/projects/ruling")
    assert speech.endpoint() == "https://ruling-ai-abc123.cognitiveservices.azure.com/tts/cognitiveservices/v1"


def test_nothing_to_say_is_refused_before_any_call():
    import asyncio

    with pytest.raises(ValueError):
        asyncio.run(speech.announce(""))
