"""API-key precedence: `sj setup` (the config file) is authoritative, so a
stale shell env var can't silently shadow it — the trap that caused repeated
401s in real use."""

import os

from screenjarvis.config import Config, apply_api_keys


def test_config_key_overrides_stale_shell_env(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "gsk_stale_from_shell")
    notices = apply_api_keys(Config(groq_api_key="gsk_good_from_setup"))
    assert os.environ["GROQ_API_KEY"] == "gsk_good_from_setup"
    assert any("GROQ_API_KEY" in n for n in notices)  # override is announced, not silent


def test_env_is_the_fallback_when_config_has_no_key(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-shell")
    notices = apply_api_keys(Config())  # nothing saved for openai
    assert os.environ["OPENAI_API_KEY"] == "sk-from-shell"  # untouched
    assert notices == []


def test_matching_env_and_config_is_silent(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-same")
    assert apply_api_keys(Config(anthropic_api_key="sk-ant-same")) == []
    assert os.environ["ANTHROPIC_API_KEY"] == "sk-ant-same"


def test_config_key_set_when_env_absent(monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    assert apply_api_keys(Config(groq_api_key="gsk_x")) == []
    assert os.environ["GROQ_API_KEY"] == "gsk_x"
