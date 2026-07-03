"""Shared clock, JSONL event writer, and cursor/click/active-app trackers."""

from __future__ import annotations

import json
import sys
import threading
import time
from pathlib import Path


class Clock:
    """One monotonic t0 per session; every event and frame is stamped against it."""

    def __init__(self):
        self._t0 = time.monotonic()

    def t(self) -> float:
        return time.monotonic() - self._t0


class EventLog:
    def __init__(self, path: Path):
        self._f = open(path, "a", encoding="utf-8")
        self._lock = threading.Lock()

    def write(self, **event) -> None:
        line = json.dumps(event, separators=(",", ":"))
        with self._lock:
            self._f.write(line + "\n")
            self._f.flush()

    def close(self) -> None:
        with self._lock:
            self._f.close()


class CursorTracker(threading.Thread):
    """Polls the global cursor position; logs on movement plus a 1s heartbeat."""

    def __init__(self, clock: Clock, log: EventLog, hz: float):
        super().__init__(daemon=True, name="sj-cursor")
        self._clock = clock
        self._log = log
        self._interval = 1.0 / hz
        self._stop = threading.Event()
        self.position: tuple[int, int] | None = None

    def run(self) -> None:
        from pynput import mouse

        ctrl = mouse.Controller()
        last_logged: tuple[int, int] | None = None
        last_log_t = -10.0
        while not self._stop.wait(self._interval):
            try:
                x, y = ctrl.position
            except Exception:
                continue
            x, y = int(x), int(y)
            self.position = (x, y)
            t = self._clock.t()
            moved = last_logged is None or abs(x - last_logged[0]) + abs(y - last_logged[1]) >= 2
            if moved or t - last_log_t >= 1.0:
                self._log.write(t=round(t, 3), type="cursor", x=x, y=y)
                last_logged = (x, y)
                last_log_t = t

    def stop(self) -> None:
        self._stop.set()


class ClickWatcher:
    """Logs mouse-down events; clicks are the strongest pointing signal, so the
    frame grabber is poked for an immediate capture on each one."""

    def __init__(self, clock: Clock, log: EventLog, on_click=None):
        self._clock = clock
        self._log = log
        self._on_click = on_click
        self._listener = None

    def start(self) -> None:
        from pynput import mouse

        def handle(x, y, button, pressed):
            if not pressed:
                return
            self._log.write(
                t=round(self._clock.t(), 3), type="click", x=int(x), y=int(y),
                button=str(button).replace("Button.", ""),
            )
            if self._on_click:
                self._on_click()

        self._listener = mouse.Listener(on_click=handle)
        self._listener.start()

    def stop(self) -> None:
        if self._listener:
            self._listener.stop()


class AppWatcher(threading.Thread):
    """Best-effort frontmost-app tracking (macOS only; silently absent elsewhere)."""

    def __init__(self, clock: Clock, log: EventLog):
        super().__init__(daemon=True, name="sj-app")
        self._clock = clock
        self._log = log
        self._stop = threading.Event()

    def run(self) -> None:
        if sys.platform != "darwin":
            return
        try:
            from AppKit import NSWorkspace
        except ImportError:
            return
        last = None
        while not self._stop.wait(0.5):
            try:
                app = NSWorkspace.sharedWorkspace().frontmostApplication()
                name = str(app.localizedName()) if app else None
            except Exception:
                continue
            if name and name != last:
                self._log.write(t=round(self._clock.t(), 3), type="window", app=name)
                last = name

    def stop(self) -> None:
        self._stop.set()
