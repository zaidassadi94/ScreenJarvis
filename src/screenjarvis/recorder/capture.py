"""One capture session: audio + frames + events with clean start/stop.

Used by both the CLI (`sj record`) and the menu-bar app. start() either fully
succeeds or cleans up after itself (no junk session dirs); stop() is
idempotent and safe to call from any thread — hotkey listener, watchdog
timer, or UI.
"""

from __future__ import annotations

import shutil
import threading
from pathlib import Path

from .. import session as S
from ..config import Config
from .audio import AudioRecorder
from .events import AppWatcher, Clock, ClickWatcher, CursorTracker, EventLog
from .frames import FrameGrabber

PERMISSION_HINT = (
    "On macOS: grant Microphone, Screen Recording, and Accessibility / Input "
    "Monitoring permissions (System Settings → Privacy & Security) to the app "
    "you launched ScreenJarvis from, then retry."
)


class CaptureSession:
    """Lifecycle: construct → start() → stop() → session_dir.

    `on_auto_stop`, when given, fires *instead of* stop() at max_secs — it
    must itself call stop() (lets the caller notify/log before stopping).
    """

    def __init__(self, cfg: Config, *, on_auto_stop=None):
        self._cfg = cfg
        self._on_auto_stop = on_auto_stop
        self._lock = threading.Lock()
        # serializes the bodies of start() and stop(): a release that arrives
        # while start() is still bringing parts up simply waits for it, so
        # stop() never sees a half-constructed capture
        self._lifecycle = threading.Lock()
        self._parts: dict = {}
        self._started = False
        self._finished = False
        self.session_dir: Path | None = None

    @property
    def recording(self) -> bool:
        with self._lock:
            return self._started and not self._finished

    def start(self) -> None:
        with self._lifecycle:
            with self._lock:
                if self._started:
                    return
                self._started = True
            try:
                self._cfg.sessions_dir.mkdir(parents=True, exist_ok=True)
                self.session_dir = S.new_session_dir(self._cfg.sessions_dir)
                clock = Clock()
                self._parts["clock"] = clock
                log = EventLog(S.events_path(self.session_dir))
                self._parts["log"] = log

                # register each part the moment it is live, so _abort() can
                # tear down exactly what a partial failure left running
                audio = AudioRecorder(S.audio_path(self.session_dir))
                audio.start()
                self._parts["audio"] = audio
                cursor = CursorTracker(clock, log, self._cfg.cursor_hz)
                cursor.start()
                self._parts["cursor"] = cursor
                frames = FrameGrabber(
                    self.session_dir, clock, log, lambda: cursor.position,
                    fps=self._cfg.fps, quality=self._cfg.jpeg_quality,
                    max_width=self._cfg.max_frame_width,
                )
                frames.start()
                self._parts["frames"] = frames
                clicks = ClickWatcher(clock, log, on_click=frames.request_click_frame)
                clicks.start()
                self._parts["clicks"] = clicks
                apps = AppWatcher(clock, log)
                apps.start()
                self._parts["apps"] = apps
                watchdog = threading.Timer(self._cfg.max_secs, self._on_auto_stop or self.stop)
                watchdog.daemon = True
                watchdog.start()
                self._parts["watchdog"] = watchdog
            except Exception:
                self._abort()
                raise

    def stop(self) -> Path | None:
        """Returns the session dir once, on the stop that actually stopped it."""
        with self._lifecycle:
            with self._lock:
                if not self._started or self._finished:
                    return None
                self._finished = True
            p = self._parts  # complete: start() finished under _lifecycle
            p["watchdog"].cancel()
            for name in ("cursor", "frames", "clicks", "apps"):
                p[name].stop()
            for name in ("cursor", "frames", "apps"):  # let capture threads finish their last write
                p[name].join(timeout=2.0)
            p["audio"].stop()
            p["log"].write(t=round(p["clock"].t(), 3), type="end")
            p["log"].close()
            return self.session_dir

    def _abort(self) -> None:
        """Tear down a partially-started capture and leave no trace."""
        if watchdog := self._parts.get("watchdog"):
            watchdog.cancel()
        for name in ("cursor", "frames", "clicks", "apps", "audio"):
            part = self._parts.get(name)
            if part:
                try:
                    part.stop()
                except Exception:
                    pass  # partial start: some parts never came up
        if log := self._parts.get("log"):
            log.close()
        with self._lock:
            self._finished = True
        if self.session_dir:
            shutil.rmtree(self.session_dir, ignore_errors=True)
            self.session_dir = None
