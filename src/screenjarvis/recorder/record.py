"""CLI recording flow: one-shot session, Enter-to-stop or hold-to-record.

The capture lifecycle itself lives in CaptureSession (shared with the
menu-bar app); this module only provides the terminal UX around it.
"""

from __future__ import annotations

import threading
from pathlib import Path

from ..config import Config
from .capture import CaptureSession


def record_session(cfg: Config, *, hold: str | None = None) -> Path:
    done = threading.Event()
    result: dict = {}

    def _finish():
        sdir = cap.stop()
        if sdir:
            result["dir"] = sdir
        done.set()

    def _auto_stop():
        print(f"\nmax duration ({cfg.max_secs:.0f}s) reached — stopping.")
        _finish()

    cap = CaptureSession(cfg, on_auto_stop=_auto_stop)

    def _start():
        try:
            cap.start()
        except Exception as exc:  # e.g. missing permissions; reported by the CLI
            result["error"] = exc
            done.set()
            return
        hint = "release the key to stop" if hold else "press Enter to stop"
        print(f"● recording — talk and point; {hint}.", flush=True)

    if hold:
        from .hotkey import HoldListener

        print(f"hold [{hold}] to record …", flush=True)
        listener = HoldListener(hold, _start, _finish)
        listener.start()
        try:
            done.wait()
        except KeyboardInterrupt:
            _finish()
        listener.stop()
    else:
        _start()
        if "error" not in result:
            def wait_for_enter():
                try:
                    input()
                except EOFError:
                    pass
                _finish()

            threading.Thread(target=wait_for_enter, daemon=True).start()
            try:
                done.wait()
            except KeyboardInterrupt:
                _finish()

    if error := result.get("error"):
        raise error
    if "dir" not in result:
        raise SystemExit("cancelled — nothing recorded.")
    return result["dir"]
