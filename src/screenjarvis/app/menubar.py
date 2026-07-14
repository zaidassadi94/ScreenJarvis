"""The rumps menu-bar shell (macOS-only; cli imports this module only on darwin).

THREADING RULE: controller callbacks (set_status, notify, play) arrive on
worker threads — the pynput hotkey listener and the compile thread — and
rumps/AppKit UI may only be touched from the main thread. So set_status just
stores the latest status string; a 0.5s rumps timer, which runs on the main
thread, copies it into the status-bar title and the status menu item.
"""

from __future__ import annotations

import os
from pathlib import Path

import rumps

from .. import session as S
from ..compiler import deliver
from ..config import CONFIG_PATH, Config, apply_api_keys, load_config
from ..recorder.hotkey import HoldListener
from ..setup_wizard import save_keys
from . import launchagent, notify
from .controller import AppController

TITLES = {"ready": "🎙", "recording": "🔴", "compiling": "⏳"}
STATUS_LABELS = {"ready": "Ready", "recording": "Recording…", "compiling": "Compiling…"}

CONFIG_TEMPLATE = """\
# ScreenJarvis configuration — every key is optional; values below are the defaults.
# See also: sj setup (interactive).

# sessions_dir = "~/ScreenJarvis/sessions"
# hold_key = "alt_r"               # e.g. alt_r, cmd_r, f8, or a single character
# max_secs = 600.0                 # auto-stop watchdog
# sounds = true
# on_done = "paste-text"           # what releasing the key does with the result:
#   paste-text | copy-text | copy-rich | open-html | claude-prompt | path | off

# stt = "auto"                     # auto | openai | groq | json
# smart = "auto"                   # auto (Claude when key is set) | on | off
# llm_model = "claude-opus-4-8"

# API keys may live here because the menu-bar app is launched outside any
# shell and inherits no environment variables:
# openai_api_key = ""
# groq_api_key = ""
# anthropic_api_key = ""
"""


class ScreenJarvisApp(rumps.App):
    def __init__(self, cfg: Config):
        super().__init__("ScreenJarvis", title=TITLES["ready"], quit_button=None)
        self._cfg = cfg
        self._status = "ready"
        self._listener = None  # set by run_app; stopped before shutdown on quit
        self._status_item = rumps.MenuItem("Status: Ready")  # no callback -> disabled
        login_item = rumps.MenuItem("Start at Login")
        login_item.state = int(launchagent.installed())
        self.menu = [
            self._status_item,
            None,
            "Open Last Session",
            "Copy Text",
            "Copy Rich Text (with images)",
            "Open as Web Page",
            "Copy Claude Prompt",
            None,
            "Open Sessions Folder",
            "Set API Keys…",
            "Open Config File",
            None,
            login_item,
            None,
            "Quit ScreenJarvis",
        ]
        self.controller = AppController(
            cfg,
            set_status=self._set_status,
            notify=notify.notify,
            clipboard=notify.copy_to_clipboard,
            play=lambda event: notify.play(event, enabled=cfg.sounds),
            paste=notify.paste_text_into_frontmost,
            copy_rich=notify.copy_rich,
            open_doc=notify.open_path,
        )

    def _set_status(self, status: str) -> None:
        # worker threads land here; only store — the timer applies it on main
        self._status = status

    @rumps.timer(0.5)
    def _refresh_status(self, _timer) -> None:
        self.title = TITLES.get(self._status, TITLES["ready"])
        label = STATUS_LABELS.get(self._status, self._status)
        self._status_item.title = f"Status: {label}"

    @rumps.clicked("Open Last Session")
    def open_last_session(self, _sender) -> None:
        sdir = self.controller.last_session_dir()
        if sdir is None:
            notify.notify("ScreenJarvis", self._no_sessions_message())
            return
        md = S.transcript_md_path(sdir)
        notify.open_path(md if md.exists() else sdir)

    @rumps.clicked("Copy Text")
    def copy_text(self, _sender) -> None:
        sdir = self._compiled_session()
        if sdir is None:
            return
        notify.copy_to_clipboard(deliver.session_text(sdir))
        notify.notify("ScreenJarvis", "Narration copied — paste it anywhere.")

    @rumps.clicked("Copy Rich Text (with images)")
    def copy_rich_text(self, _sender) -> None:
        sdir = self._compiled_session()
        if sdir is None:
            return
        notify.copy_rich(deliver.write_html(sdir, embed=False))
        notify.notify("ScreenJarvis", "Copied with images — paste into Notion, Docs, or email.")

    @rumps.clicked("Open as Web Page")
    def open_as_web_page(self, _sender) -> None:
        sdir = self._compiled_session()
        if sdir is None:
            return
        notify.open_path(deliver.write_html(sdir, embed=True))

    @rumps.clicked("Copy Claude Prompt")
    def copy_claude_prompt(self, _sender) -> None:
        prompt = self.controller.last_claude_prompt()
        if not prompt:
            notify.notify("ScreenJarvis", self._no_sessions_message())
            return
        notify.copy_to_clipboard(prompt)
        notify.notify("ScreenJarvis", "Claude prompt copied to clipboard.")

    @rumps.clicked("Set API Keys…")
    def set_api_keys(self, _sender) -> None:
        stt = notify.prompt_secret(
            "ScreenJarvis — Speech-to-text key",
            "Paste an OpenAI (sk-…) or Groq (gsk_…) key. Needed to transcribe your voice.",
        )
        if stt is None:  # cancelled
            return
        updates: dict[str, str] = {}
        if stt.startswith("gsk_"):
            updates["groq_api_key"] = stt
        elif stt:
            updates["openai_api_key"] = stt
        anthropic = notify.prompt_secret(
            "ScreenJarvis — Anthropic key (optional)",
            "Paste an Anthropic key (sk-ant-…) to enable smart mode, or leave blank.",
        )
        if anthropic:
            updates["anthropic_api_key"] = anthropic
        if not updates:
            notify.notify("ScreenJarvis", "No keys entered — nothing changed.")
            return
        save_keys(updates)
        self._reload_keys()
        notify.notify("ScreenJarvis", "Keys saved. Hold your key and start talking.")

    @rumps.clicked("Open Sessions Folder")
    def open_sessions_folder(self, _sender) -> None:
        self._cfg.sessions_dir.mkdir(parents=True, exist_ok=True)
        notify.open_path(self._cfg.sessions_dir)

    @rumps.clicked("Open Config File")
    def open_config_file(self, _sender) -> None:
        if not CONFIG_PATH.exists():
            CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
            CONFIG_PATH.write_text(CONFIG_TEMPLATE)
        notify.open_path(CONFIG_PATH)

    @rumps.clicked("Start at Login")
    def toggle_login_item(self, sender) -> None:
        if launchagent.installed():
            launchagent.uninstall_login_item()
        else:
            launchagent.install_login_item()
        sender.state = int(launchagent.installed())

    @rumps.clicked("Quit ScreenJarvis")
    def quit_app(self, _sender) -> None:
        if self._listener is not None:  # stop new recordings before draining
            self._listener.stop()
        self.controller.shutdown(timeout=15)
        rumps.quit_application()

    def _compiled_session(self) -> Path | None:
        """The latest session that has a transcript.md, or None (with a nudge)."""
        sdir = self.controller.last_session_dir()
        if sdir is None or not S.transcript_md_path(sdir).exists():
            notify.notify("ScreenJarvis", self._no_sessions_message())
            return None
        return sdir

    def _reload_keys(self) -> None:
        # keys are read from the environment at compile time; update the process
        # env (and the shared cfg) so freshly-saved keys take effect without a
        # restart. self._cfg is the same object the controller holds.
        fresh = load_config()
        for attr in ("openai_api_key", "groq_api_key", "anthropic_api_key"):
            setattr(self._cfg, attr, getattr(fresh, attr))
        apply_api_keys(self._cfg)

    def _no_sessions_message(self) -> str:
        return f"No sessions yet — hold {self._cfg.hold_key} and start talking."


def run_app(cfg: Config) -> int:
    app = ScreenJarvisApp(cfg)
    stt_unconfigured = (
        cfg.stt != "json"  # json is the offline/dev backend, needs no key
        and not os.environ.get("OPENAI_API_KEY")
        and not os.environ.get("GROQ_API_KEY")
    )
    if stt_unconfigured:
        notify.notify(
            "ScreenJarvis",
            "Speech-to-text is not configured yet — run  sj setup  in Terminal.",
        )
    listener = HoldListener(cfg.hold_key, app.controller.on_press, app.controller.on_release)
    app._listener = listener
    listener.start()
    try:
        app.run()
    finally:
        listener.stop()
        app.controller.shutdown()
    return 0
