"""Platform-free brain of the menu-bar app.

Every UI side effect (status icon, notifications, clipboard, sounds) is an
injected callable, so this class runs — and is tested — without rumps,
pynput, mss, or a display. The macOS shell in menubar.py is a thin wrapper.

Threading:
- on_press/on_release arrive on the hotkey listener thread; the auto-stop on
  the capture watchdog thread. These stay cheap: on_release hands the (possibly
  multi-second) capture teardown to the compile worker rather than blocking the
  hotkey callback — a slow callback can get the macOS event tap disabled.
- A single daemon worker stops + compiles queued captures in order, so the user
  can start the next recording while the previous one compiles (Wispr-style).
- Status is recomputed from shared state after every change, priority
  recording > compiling > ready.
"""

from __future__ import annotations

import queue
import threading
import time
from pathlib import Path

from ..compiler.compile import compile_session
from ..config import Config
from ..recorder.capture import PERMISSION_HINT, CaptureSession
from ..session import latest_session, transcript_md_path


def claude_prompt(md_path: Path | str) -> str:
    return (f"Read '{md_path}' — a narrated screen session with figures — "
            "and help me with what I describe.")


class AppController:
    _SENTINEL = object()

    def __init__(self, cfg: Config, *, set_status, notify, clipboard, play,
                 capture_factory=CaptureSession, compile_fn=compile_session):
        self._cfg = cfg
        self._set_status = set_status
        self._notify = notify
        self._clipboard = clipboard
        self._play = play
        self._capture_factory = capture_factory
        self._compile_fn = compile_fn
        self._lock = threading.Lock()
        self._capture: CaptureSession | None = None
        self._pending = 0  # captures enqueued or compiling right now
        self._closing = False
        self._last_result = None
        self._queue: queue.Queue = queue.Queue()
        self._worker = threading.Thread(target=self._work, name="sj-compile", daemon=True)
        self._worker.start()
        self._refresh_status()

    # -- hotkey events -----------------------------------------------------

    def on_press(self) -> None:
        with self._lock:
            if self._closing or self._capture is not None:
                return
            capture = self._capture_factory(self._cfg, on_auto_stop=self._auto_stop)
            self._capture = capture
        try:
            capture.start()
        except Exception as exc:
            with self._lock:
                self._capture = None
            self._notify("ScreenJarvis",
                         f"Could not start recording: {exc}. " + PERMISSION_HINT)
            self._play("error")
            self._refresh_status()
            return
        self._play("start")
        self._refresh_status()

    def on_release(self) -> None:
        # hand the capture to the worker to stop() + compile — stop() does thread
        # joins and must not block the hotkey callback thread. Status becomes
        # "compiling" here so the icon flips the instant the key is released.
        with self._lock:
            capture, self._capture = self._capture, None
            if capture is not None:
                self._pending += 1
        if capture is None:
            return
        self._play("stop")
        self._queue.put(capture)
        self._refresh_status()

    def _auto_stop(self) -> None:
        # fires instead of stop() at max_secs; the release path does the stop
        self._notify("ScreenJarvis",
                     f"Max duration reached ({self._cfg.max_secs:.0f}s) — stopping.")
        self.on_release()

    # -- compile worker ------------------------------------------------------

    def _work(self) -> None:
        while True:
            item = self._queue.get()
            if item is self._SENTINEL:
                return
            try:
                self._process(item)
            except Exception as exc:  # never let one bad job kill the worker
                self._safe("notify", "ScreenJarvis", f"Unexpected error: {exc}")
            finally:
                with self._lock:
                    self._pending -= 1
                self._refresh_status()

    def _process(self, capture) -> None:
        sdir = capture.stop()
        if sdir is None:
            return
        self._compile_one(sdir)

    def _compile_one(self, sdir: Path) -> None:
        try:
            result = self._compile_fn(sdir, self._cfg)
        except Exception as exc:
            self._notify("ScreenJarvis",
                         f"Compile failed: {exc} — recording kept at {sdir}")
            self._play("error")
            return
        with self._lock:
            self._last_result = result
        copied = self._hand_off(result)
        suffix = " — prompt copied, paste into Claude Code" if copied else ""
        self._notify("ScreenJarvis",
                     f"{len(result.figures)} figure(s) · {result.mode} mode{suffix}")
        self._play("done")

    def _hand_off(self, result) -> bool:
        mode = self._cfg.copy_on_done
        if mode == "claude-prompt":
            text = claude_prompt(result.md_path)
        elif mode == "path":
            text = str(result.md_path)
        else:
            return False
        try:
            self._clipboard(text)
            return True
        except Exception:
            return False  # e.g. pbcopy missing: degrade to a plain notification

    def _safe(self, kind: str, *args) -> None:
        try:
            (self._notify if kind == "notify" else self._play)(*args)
        except Exception:
            pass

    # -- menu queries --------------------------------------------------------

    def last_session_dir(self) -> Path | None:
        with self._lock:
            if self._last_result is not None:
                return self._last_result.session_dir
        return latest_session(self._cfg.sessions_dir)

    def last_claude_prompt(self) -> str | None:
        with self._lock:
            if self._last_result is not None:
                return claude_prompt(self._last_result.md_path)
        d = latest_session(self._cfg.sessions_dir)
        if d is None:
            return None
        md = transcript_md_path(d)
        return claude_prompt(md) if md.exists() else None

    # -- lifecycle -------------------------------------------------------------

    def shutdown(self, timeout: float = 15.0) -> None:
        """Stop any active capture (its session still gets compiled), drain
        the queue, and stop the worker — bounded by `timeout`, never hangs."""
        deadline = time.monotonic() + timeout
        with self._lock:
            self._closing = True
            capture, self._capture = self._capture, None
            if capture is not None:
                self._pending += 1
        if capture is not None:
            self._queue.put(capture)
        self._refresh_status()
        self._queue.put(self._SENTINEL)
        self._worker.join(max(0.0, deadline - time.monotonic()))

    # -- status ----------------------------------------------------------------

    def _refresh_status(self) -> None:
        with self._lock:
            if self._capture is not None:
                s = "recording"
            elif self._pending:
                s = "compiling"
            else:
                s = "ready"
        self._set_status(s)
