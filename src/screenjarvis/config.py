"""Configuration: defaults, optional ~/.config/screenjarvis/config.toml, env overrides."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

CONFIG_PATH = Path("~/.config/screenjarvis/config.toml").expanduser()


@dataclass
class Config:
    sessions_dir: Path = field(default_factory=lambda: Path("~/ScreenJarvis/sessions").expanduser())
    stt: str = "auto"  # auto | openai | groq | json
    fps: float = 2.0
    cursor_hz: float = 15.0
    jpeg_quality: int = 80
    figure_quality: int = 90
    max_frame_width: int = 1600
    crop: str = "none"  # none | region
    hold_key: str = "alt_r"
    max_secs: float = 600.0
    open_after: bool = True
    smart: str = "auto"  # auto (use Claude when ANTHROPIC_API_KEY is set) | on | off
    llm_model: str = "claude-opus-4-8"
    max_llm_frames: int = 14
    llm_image_width: int = 1024
    sounds: bool = True
    copy_on_done: str = "claude-prompt"  # claude-prompt | path | off
    # keys may live in the config file because the menu-bar app is launched
    # outside any shell and inherits no environment variables
    openai_api_key: str = ""
    groq_api_key: str = ""
    anthropic_api_key: str = ""
    trigger_phrases: list[str] | None = None  # None -> built-in defaults
    extra_trigger_phrases: list[str] = field(default_factory=list)


def load_config() -> Config:
    cfg = Config()
    if CONFIG_PATH.exists():
        data = tomllib.loads(CONFIG_PATH.read_text())
        for key, value in data.items():
            if not hasattr(cfg, key):
                continue
            if key == "sessions_dir":
                value = Path(value).expanduser()
            setattr(cfg, key, value)
    if env_dir := os.environ.get("SCREENJARVIS_SESSIONS_DIR"):
        cfg.sessions_dir = Path(env_dir).expanduser()
    if env_stt := os.environ.get("SCREENJARVIS_STT"):
        cfg.stt = env_stt
    return cfg


_KEY_ENV_VARS = {
    "openai_api_key": "OPENAI_API_KEY",
    "groq_api_key": "GROQ_API_KEY",
    "anthropic_api_key": "ANTHROPIC_API_KEY",
}


def apply_api_keys(cfg: Config) -> None:
    """Export config-file keys into the environment; real env vars still win."""
    for attr, env in _KEY_ENV_VARS.items():
        value = getattr(cfg, attr)
        if value and not os.environ.get(env):
            os.environ[env] = value
