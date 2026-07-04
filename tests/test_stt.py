"""Backend/key routing — a key must reach the service its prefix names, even
when pasted into the wrong slot (the mistake that caused repeated 401s)."""

import pytest

from screenjarvis.compiler import stt


def _env(monkeypatch, openai="", groq=""):
    for name, val in (("OPENAI_API_KEY", openai), ("GROQ_API_KEY", groq)):
        if val:
            monkeypatch.setenv(name, val)
        else:
            monkeypatch.delenv(name, raising=False)


def test_groq_key_in_openai_slot_routes_to_groq(monkeypatch):
    # the exact live bug: a gsk_ key sat in the OpenAI slot -> was sent to OpenAI -> 401
    _env(monkeypatch, openai="gsk_realGroqKey")
    assert stt.resolve_backend("auto") == ("groq", "gsk_realGroqKey")


def test_openai_key_in_groq_slot_routes_to_openai(monkeypatch):
    _env(monkeypatch, groq="sk-realOpenAIKey")
    assert stt.resolve_backend("auto") == ("openai", "sk-realOpenAIKey")


def test_auto_prefers_groq_when_both_present(monkeypatch):
    _env(monkeypatch, openai="sk-oa", groq="gsk_gq")
    assert stt.resolve_backend("auto") == ("groq", "gsk_gq")


def test_explicit_groq_finds_the_groq_key_in_either_slot(monkeypatch):
    _env(monkeypatch, openai="gsk_misplaced")  # only key present, wrong slot
    assert stt.resolve_backend("groq") == ("groq", "gsk_misplaced")


def test_no_key_raises_friendly_error(monkeypatch):
    _env(monkeypatch)
    with pytest.raises(SystemExit, match="No speech-to-text key"):
        stt.resolve_backend("auto")


def test_unknown_prefix_falls_back_to_slot(monkeypatch):
    # a key that matches neither prefix still works via its slot
    _env(monkeypatch, openai="customkey123")
    assert stt.resolve_backend("openai") == ("openai", "customkey123")
