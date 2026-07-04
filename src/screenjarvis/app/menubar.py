"""The rumps menu-bar shell (macOS-only; cli imports this module only on darwin).

THREADING RULE: controller callbacks (set_status, notify, play) arrive on
worker threads — the pynput hotkey listener and the compile thread — and
rumps/AppKit UI may only be touched from the main thread. So set_status just
stores the latest status string; a 0.5s rumps timer, which runs on the main
thread, copies it into the status-bar title and the status menu item.
"""

from __future__ import annotations

import os

import rumps

from .. import session as S
from ..config import CONFIG_PATH, Config
from ..recorder.hotkey import HoldListener
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
# copy_on_done = "claude-prompt"   # claude-prompt | path | off

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
            "Copy Claude Prompt",
            "Open Sessions Folder",
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

    @rumps.clicked("Copy Claude Prompt")
    def copy_claude_prompt(self, _sender) -> None:
        prompt = self.controller.last_claude_prompt()
        if not prompt:
            notify.notify("ScreenJarvis", self._no_sessions_message())
            return
        notify.copy_to_clipboard(prompt)
        notify.notify("ScreenJarvis", "Claude prompt copied to clipboard.")

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
