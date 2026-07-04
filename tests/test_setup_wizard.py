"""Setup-wizard tests — headless: CONFIG_PATH points at tmp_path and input()
is a scripted iterator, so no terminal, filesystem config, or pynput needed."""

import builtins
import tomllib
from pathlib import Path

import pytest

import screenjarvis.setup_wizard as sw
from screenjarvis.config import Config


def script_input(monkeypatch, answers: list[str]) -> None:
    it = iter(answers)

    def fake_input(prompt: str = "") -> str:
        try:
            return next(it)
        except StopIteration:
            raise EOFError from None

    monkeypatch.setattr(builtins, "input", fake_input)


@pytest.fixture
def config_path(tmp_path, monkeypatch) -> Path:
    path = tmp_path / "config" / "config.toml"
    monkeypatch.setattr(sw, "CONFIG_PATH", path)
    return path


def test_fresh_setup_writes_all_values(config_path, monkeypatch):
    script_input(monkeypatch, ["sk-openai-abcdef", "gsk-groq-123456",
                               "sk-ant-xyz789", "f13", "n"])
    assert sw.run_setup(Config()) == 0

    data = tomllib.loads(config_path.read_text())
    assert data["openai_api_key"] == "sk-openai-abcdef"
    assert data["groq_api_key"] == "gsk-groq-123456"
    assert data["anthropic_api_key"] == "sk-ant-xyz789"
    assert data["hold_key"] == "f13"
    assert data["sounds"] is False


def test_enter_through_preserves_existing_config(config_path, monkeypatch):
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        'fps = 4.0\nsmart = "off"\nanthropic_api_key = "sk-ant-keepme"\n'
    )
    # cli.main loads the config before calling run_setup, so cfg mirrors the file
    cfg = Config(anthropic_api_key="sk-ant-keepme")
    script_input(monkeypatch, ["", "", "", "", ""])
    assert sw.run_setup(cfg) == 0

    data = tomllib.loads(config_path.read_text())
    assert data["fps"] == 4.0
    assert data["smart"] == "off"
    assert data["anthropic_api_key"] == "sk-ant-keepme"
    assert data["hold_key"] == cfg.hold_key
    assert data["sounds"] is True


def test_merge_preserves_comments_tables_and_lists(config_path, monkeypatch):
    # a hand-edited file with comments, a list, and a [table]/date the naive
    # serializer choked on — none of it may be lost, and setup must not fail
    config_path.parent.mkdir(parents=True)
    config_path.write_text(
        "# my settings\n"
        'extra_trigger_phrases = ["this widget"]\n'
        'anthropic_api_key = "sk-ant-old"\n'
        "\n"
        "[experimental]\n"
        "since = 2026-07-04\n"
    )
    cfg = Config(anthropic_api_key="sk-ant-old", extra_trigger_phrases=["this widget"])
    script_input(monkeypatch, ["sk-new", "", "-", "", "y"])  # set openai, clear anthropic
    assert sw.run_setup(cfg) == 0

    text = config_path.read_text()
    assert "# my settings" in text                       # comment preserved
    assert "[experimental]" in text and "2026-07-04" in text  # table + date survived
    data = tomllib.loads(text)
    assert data["extra_trigger_phrases"] == ["this widget"]
    assert data["openai_api_key"] == "sk-new"            # new key added at top level
    assert "anthropic_api_key" not in data               # cleared
    assert data["experimental"]["since"].isoformat() == "2026-07-04"


def test_dash_clears_a_stored_key(config_path, monkeypatch):
    config_path.parent.mkdir(parents=True)
    config_path.write_text('openai_api_key = "sk-openai-oldkey"\n')
    cfg = Config(openai_api_key="sk-openai-oldkey", groq_api_key="gsk-groq-keep1")
    script_input(monkeypatch, ["-", "", "", "", ""])
    assert sw.run_setup(cfg) == 0

    data = tomllib.loads(config_path.read_text())
    assert data.get("openai_api_key", "") == ""
    assert data["groq_api_key"] == "gsk-groq-keep1"


def test_no_stt_key_warns_but_still_saves(config_path, monkeypatch, capsys):
    script_input(monkeypatch, ["", "", "", "", ""])
    assert sw.run_setup(Config()) == 0
    assert "cannot be transcribed" in capsys.readouterr().out
    assert config_path.exists()


def test_eof_aborts_without_writing(config_path, monkeypatch, capsys):
    script_input(monkeypatch, [])
    assert sw.run_setup(Config()) == 1
    assert "setup aborted — nothing written." in capsys.readouterr().out
    assert not config_path.exists()


def test_keyboard_interrupt_mid_flow_leaves_file_untouched(config_path, monkeypatch):
    config_path.parent.mkdir(parents=True)
    original = 'fps = 4.0\n'
    config_path.write_text(original)
    answers = iter(["sk-openai-abcdef"])

    def fake_input(prompt: str = "") -> str:
        try:
            return next(answers)
        except StopIteration:
            raise KeyboardInterrupt from None

    monkeypatch.setattr(builtins, "input", fake_input)
    assert sw.run_setup(Config()) == 1
    assert config_path.read_text() == original
