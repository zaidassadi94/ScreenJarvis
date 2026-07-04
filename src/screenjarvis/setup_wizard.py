"""Interactive first-run setup: API keys, hotkey, preferences.

Plain input() prompts so it runs in any terminal with no extra dependencies.
Keys are stored in the config file (not the shell environment) because the
menu-bar app is launched outside any shell; cli.main exports them at startup
via apply_api_keys. The file is written by MERGING into the existing TOML so
hand-edited settings (fps, smart, ...) survive, and serialized by hand to
avoid adding a TOML-writer dependency.
"""

from __future__ import annotations

import re

from .config import CONFIG_PATH, Config

_STT_INTRO = "Speech-to-text — one of these keys is needed to transcribe recordings."
_ANTHROPIC_INTRO = (
    "Anthropic API key — enables smart mode: Claude cleans the prose, picks "
    "figures, writes captions. Without it output falls back to the offline heuristic."
)
_NO_STT_WARNING = (
    "warning: no speech-to-text key set — recordings will be kept but cannot "
    "be transcribed until you add an OpenAI or Groq key (rerun `uv run sj setup`)."
)
_ABORT_MESSAGE = "setup aborted — nothing written."


def run_setup(cfg: Config) -> int:
    print("ScreenJarvis setup — Enter keeps the current value.\n")
    try:
        print(_STT_INTRO)
        openai_key = _prompt_key("OpenAI API key", cfg.openai_api_key)
        if openai_key.startswith("gsk_"):
            print("  ⚠ that looks like a Groq key (starts with gsk_). OpenAI keys "
                  "start with sk-. Clear it here with '-' and paste it at the Groq "
                  "question below instead.")
        groq_key = _prompt_key("Groq API key", cfg.groq_api_key)
        if groq_key.startswith("sk-"):
            print("  ⚠ that looks like an OpenAI key (starts with sk-). Groq keys "
                  "start with gsk_. It belongs at the OpenAI question above.")
        if not openai_key and not groq_key:
            print(_NO_STT_WARNING)
        print()
        print(_ANTHROPIC_INTRO)
        anthropic_key = _prompt_key("Anthropic API key", cfg.anthropic_api_key)
        print()
        hold_key = _prompt_token("Recording hold key", cfg.hold_key)
        sounds = _prompt_yes_no("Play start/stop sounds?", cfg.sounds)
    except (KeyboardInterrupt, EOFError):
        print(f"\n{_ABORT_MESSAGE}")
        return 1

    _merge_into_config_file({
        "openai_api_key": openai_key,
        "groq_api_key": groq_key,
        "anthropic_api_key": anthropic_key,
        "hold_key": hold_key,
        "sounds": sounds,
    })

    print(f"\nsaved: {CONFIG_PATH}")
    print(f"  openai_api_key    = {_mask(openai_key)}")
    print(f"  groq_api_key      = {_mask(groq_key)}")
    print(f"  anthropic_api_key = {_mask(anthropic_key)}")
    print(f"  hold_key          = {hold_key}")
    print(f"  sounds            = {'on' if sounds else 'off'}")
    print("\nmacOS will ask for these permissions on first use "
          "(System Settings → Privacy & Security):")
    print("  - Microphone       (your voice)")
    print("  - Screen Recording (screenshots)")
    print("  - Accessibility    (cursor position)")
    print("  - Input Monitoring (the hold key)")
    print("\nnext steps:")
    print("  uv run sj app                    start the menu-bar app")
    print("  uv run sj app --install-login    start it automatically at login")
    return 0


def _mask(key: str) -> str:
    if not key:
        return "(not set)"
    if len(key) <= 8:
        return "…" + key[-2:]
    return f"{key[:3]}…{key[-4:]}"


def _prompt_key(label: str, current: str) -> str:
    """Enter keeps `current` (or skips when unset); '-' clears a stored key."""
    if current:
        hint = f"[{_mask(current)}] Enter keeps, '-' clears"
    else:
        hint = "Enter skips"
    raw = input(f"{label} ({hint}): ").strip()
    if not raw:
        return current
    if raw == "-":
        return ""
    return raw


def _prompt_token(label: str, default: str) -> str:
    # accept any non-empty token: pynput must not be imported here (setup
    # runs on machines where the app permissions aren't granted yet)
    raw = input(f"{label} [{default}]: ").strip()
    return raw or default


def _prompt_yes_no(label: str, default: bool) -> bool:
    hint = "Y/n" if default else "y/N"
    while True:
        raw = input(f"{label} [{hint}]: ").strip().lower()
        if not raw:
            return default
        if raw in ("y", "yes"):
            return True
        if raw in ("n", "no"):
            return False
        print("please answer y or n")


def _merge_into_config_file(updates: dict[str, object]) -> None:
    """Edit only the given keys in place, line by line.

    Comments, blank lines, [tables], and any hand-added values we don't touch
    are preserved verbatim — we never round-trip the whole file through a
    serializer, so an exotic existing value can't make setup fail. Edits and
    insertions stay in the top-level region (before the first [section]), which
    is where every ScreenJarvis key lives.
    """
    existing = CONFIG_PATH.read_text() if CONFIG_PATH.exists() else ""
    lines = existing.splitlines()
    top_end = next((i for i, ln in enumerate(lines) if ln.lstrip().startswith("[")), len(lines))

    def key_of(line: str) -> str | None:
        m = re.match(r"\s*([A-Za-z0-9_]+)\s*=", line)
        return m.group(1) if m else None

    appends: list[str] = []
    for key, value in updates.items():
        new_line = None if value == "" else f"{key} = {_toml_value(value)}"
        idx = next((i for i in range(top_end) if key_of(lines[i]) == key), None)
        if idx is not None:
            if new_line is None:
                del lines[idx]
                top_end -= 1
            else:
                lines[idx] = new_line
        elif new_line is not None:
            appends.append(new_line)

    lines[top_end:top_end] = appends
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text("\n".join(lines) + "\n" if lines else "")


def _toml_value(value: object) -> str:
    if isinstance(value, bool):  # before int: bool is an int subclass
        return "true" if value else "false"
    if isinstance(value, str):
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(v) for v in value) + "]"
    raise TypeError(f"cannot serialize config value of type {type(value).__name__}")
