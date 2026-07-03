"""Recording orchestration: wires audio + frames + events together for one session."""

from __future__ import annotations

import shutil
import threading
from pathlib import Path

from .. import session as S
from ..config import Config
from .audio import AudioRecorder
from .events import AppWatcher, Clock, ClickWatcher, CursorTracker, EventLog
from .frames import FrameGrabber


def record_session(cfg: Config, *, hold: str | None = None) -> Path:
    cfg.sessions_dir.mkdir(parents=True, exist_ok=True)
    sdir = S.new_session_dir(cfg.sessions_dir)

    done = threading.Event()
    state: dict = {}
    stop_lock = threading.Lock()

    def start_capture():
        clock = Clock()
        log = EventLog(S.events_path(sdir))
        audio = AudioRecorder(S.audio_path(sdir))
        cursor = CursorTracker(clock, log, cfg.cursor_hz)
        frames = FrameGrabber(
            sdir, clock, log, lambda: cursor.position,
            fps=cfg.fps, quality=cfg.jpeg_quality, max_width=cfg.max_frame_width,
        )
        clicks = ClickWatcher(clock, log, on_click=frames.request_click_frame)
        apps = AppWatcher(clock, log)
        watchdog = threading.Timer(cfg.max_secs, lambda: (print("\nmax duration reached — stopping."), stop_capture()))
        watchdog.daemon = True

        audio.start()
        cursor.start()
        frames.start()
        clicks.start()
        apps.start()
        watchdog.start()
        state.update(clock=clock, log=log, audio=audio, cursor=cursor,
                     frames=frames, clicks=clicks, apps=apps, watchdog=watchdog)
        hint = "release the key to stop" if hold else "press Enter to stop"
        print(f"● recording — talk and point; {hint}.", flush=True)

    def stop_capture():
        with stop_lock:
            if not state or state.get("stopped"):
                return
            state["stopped"] = True
        state["watchdog"].cancel()
        for part in ("cursor", "frames", "clicks", "apps"):
            state[part].stop()
        for part in ("cursor", "frames", "apps"):  # let capture threads finish their last write
            state[part].join(timeout=2.0)
        state["audio"].stop()
        state["log"].write(t=round(state["clock"].t(), 3), type="end")
        state["log"].close()
        done.set()

    try:
        if hold:
            from .hotkey import HoldListener

            print(f"hold [{hold}] to record …", flush=True)
            listener = HoldListener(hold, start_capture, stop_capture)
            listener.start()
            try:
                done.wait()
            except KeyboardInterrupt:
                stop_capture()
            listener.stop()
        else:
            start_capture()

            def wait_for_enter():
                try:
                    input()
                except EOFError:
                    pass
                stop_capture()

            threading.Thread(target=wait_for_enter, daemon=True).start()
            try:
                done.wait()
            except KeyboardInterrupt:
                stop_capture()
    finally:
        # only a session that actually captured and stopped is worth keeping
        if not state.get("stopped"):
            shutil.rmtree(sdir, ignore_errors=True)

    if not sdir.exists():
        raise SystemExit("cancelled — nothing recorded.")
    return sdir
