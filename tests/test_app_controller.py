"""AppController tests — headless: fake capture and compiler, no pynput/mss/
sounddevice. Threads are synchronized with events/conditions, never sleeps."""

import threading
import types
from pathlib import Path

from screenjarvis.app.controller import AppController
from screenjarvis.config import Config
from screenjarvis.recorder.capture import PERMISSION_HINT

WAIT = 3.0


class StatusLog:
    """Records every set_status call; lets tests wait for a target status."""

    def __init__(self):
        self.values: list[str] = []
        self._cv = threading.Condition()

    def __call__(self, s: str) -> None:
        with self._cv:
            self.values.append(s)
            self._cv.notify_all()

    def wait_for(self, s: str, timeout: float = WAIT) -> bool:
        with self._cv:
            return self._cv.wait_for(lambda: self.values and self.values[-1] == s, timeout)


class FakeCapture:
    def __init__(self, cfg, *, on_auto_stop=None, sdir: Path | None = None,
                 fail: Exception | None = None):
        self.on_auto_stop = on_auto_stop
        self._sdir = sdir
        self._fail = fail
        self._recording = False

    @property
    def recording(self) -> bool:
        return self._recording

    def start(self) -> None:
        if self._fail is not None:
            raise self._fail
        self._recording = True

    def stop(self) -> Path | None:
        if not self._recording:
            return None
        self._recording = False
        d, self._sdir = self._sdir, None  # session dir handed out exactly once
        return d


class Harness:
    def __init__(self, tmp_path: Path, *, copy_on_done: str = "claude-prompt",
                 gate: threading.Event | None = None,
                 compile_fail: Exception | None = None,
                 start_fail: Exception | None = None):
        self.cfg = Config(sessions_dir=tmp_path / "sessions", copy_on_done=copy_on_done)
        self.status = StatusLog()
        self.notes: list[tuple[str, str]] = []
        self.clips: list[str] = []
        self.sounds: list[str] = []
        self.captures: list[FakeCapture] = []
        self.compiled: list[Path] = []

        def factory(cfg, *, on_auto_stop=None):
            sdir = tmp_path / f"session-{len(self.captures)}"
            sdir.mkdir()
            cap = FakeCapture(cfg, on_auto_stop=on_auto_stop, sdir=sdir, fail=start_fail)
            self.captures.append(cap)
            return cap

        def compile_fn(sdir, cfg):
            if gate is not None:
                assert gate.wait(WAIT)
            self.compiled.append(sdir)
            if compile_fail is not None:
                raise compile_fail
            return types.SimpleNamespace(md_path=sdir / "transcript.md", mode="smart",
                                         figures=[1, 2], session_dir=sdir)

        self.ctl = AppController(
            self.cfg, set_status=self.status,
            notify=lambda title, msg: self.notes.append((title, msg)),
            clipboard=self.clips.append, play=self.sounds.append,
            capture_factory=factory, compile_fn=compile_fn,
        )

    def messages(self) -> list[str]:
        return [msg for _, msg in self.notes]


def test_happy_flow_status_clipboard_and_notify(tmp_path):
    gate = threading.Event()
    h = Harness(tmp_path, gate=gate)
    assert h.status.wait_for("ready")

    h.ctl.on_press()
    assert h.status.values[-1] == "recording"
    h.ctl.on_release()
    assert h.status.values[-1] == "compiling"  # worker is gated, so this holds

    gate.set()
    assert h.status.wait_for("ready")
    assert h.status.values == ["ready", "recording", "compiling", "ready"]

    md_path = tmp_path / "session-0" / "transcript.md"
    assert len(h.clips) == 1 and str(md_path) in h.clips[0]
    assert h.messages()[-1] == "2 figure(s) · smart mode — prompt copied, paste into Claude Code"
    assert h.sounds == ["start", "stop", "done"]
    assert h.ctl.last_session_dir() == tmp_path / "session-0"
    assert str(md_path) in h.ctl.last_claude_prompt()

    h.ctl.shutdown(timeout=WAIT)


def test_press_while_recording_is_ignored(tmp_path):
    h = Harness(tmp_path)
    h.ctl.on_press()
    h.ctl.on_press()
    assert len(h.captures) == 1
    assert h.sounds == ["start"]
    h.ctl.shutdown(timeout=WAIT)


def test_release_without_press_is_ignored(tmp_path):
    h = Harness(tmp_path)
    assert h.status.wait_for("ready")
    h.ctl.on_release()
    assert h.sounds == []
    assert h.compiled == []
    assert h.status.values[-1] == "ready"
    h.ctl.shutdown(timeout=WAIT)


def test_two_recordings_queued_while_compiling_both_compile(tmp_path):
    gate = threading.Event()
    h = Harness(tmp_path, gate=gate)

    h.ctl.on_press()
    h.ctl.on_release()
    h.ctl.on_press()  # next recording starts while the first compile is gated
    assert h.status.values[-1] == "recording"
    h.ctl.on_release()

    gate.set()
    assert h.status.wait_for("ready")
    assert h.compiled == [tmp_path / "session-0", tmp_path / "session-1"]
    assert sum("figure(s)" in m for m in h.messages()) == 2
    h.ctl.shutdown(timeout=WAIT)


def test_compile_failure_notifies_with_session_dir(tmp_path):
    h = Harness(tmp_path, compile_fail=RuntimeError("no api key"))
    h.ctl.on_press()
    h.ctl.on_release()
    assert h.status.wait_for("ready")

    failure = h.messages()[-1]
    assert "Compile failed: no api key" in failure
    assert str(tmp_path / "session-0") in failure
    assert h.sounds[-1] == "error"
    assert h.clips == []
    h.ctl.shutdown(timeout=WAIT)


def test_copy_on_done_off_never_touches_clipboard(tmp_path):
    h = Harness(tmp_path, copy_on_done="off")
    h.ctl.on_press()
    h.ctl.on_release()
    assert h.status.wait_for("ready")
    assert h.clips == []
    assert h.messages()[-1] == "2 figure(s) · smart mode"
    h.ctl.shutdown(timeout=WAIT)


def test_copy_on_done_path_copies_bare_path(tmp_path):
    h = Harness(tmp_path, copy_on_done="path")
    h.ctl.on_press()
    h.ctl.on_release()
    assert h.status.wait_for("ready")
    assert h.clips == [str(tmp_path / "session-0" / "transcript.md")]
    h.ctl.shutdown(timeout=WAIT)


def test_auto_stop_notifies_and_still_compiles(tmp_path):
    h = Harness(tmp_path)
    h.ctl.on_press()
    h.captures[0].on_auto_stop()  # what the capture watchdog would fire
    assert any("max duration reached" in m.lower() for m in h.messages())
    assert h.status.wait_for("ready")
    assert h.compiled == [tmp_path / "session-0"]
    assert h.sounds[-1] == "done"
    h.ctl.shutdown(timeout=WAIT)


def test_start_failure_notifies_permission_hint_and_stays_ready(tmp_path):
    h = Harness(tmp_path, start_fail=RuntimeError("mic busy"))
    h.ctl.on_press()

    failure = h.messages()[-1]
    assert "Could not start recording: mic busy" in failure
    assert PERMISSION_HINT in failure
    assert h.sounds == ["error"]
    assert h.status.values[-1] == "ready"
    assert "recording" not in h.status.values

    h.ctl.shutdown(timeout=WAIT)


def test_clipboard_failure_keeps_worker_alive(tmp_path):
    # a broken clipboard (e.g. pbcopy missing) must not kill the compile worker
    h = Harness(tmp_path)
    def boom(_text):
        raise FileNotFoundError("pbcopy")
    h.ctl._clipboard = boom

    h.ctl.on_press(); h.ctl.on_release()
    assert h.status.wait_for("ready")
    assert "2 figure(s)" in h.messages()[-1]  # success notify still fired…
    assert "prompt copied" not in h.messages()[-1]  # …without the copied suffix

    h.ctl.on_press(); h.ctl.on_release()  # worker survived: a second session compiles
    assert h.status.wait_for("ready")
    assert h.compiled == [tmp_path / "session-0", tmp_path / "session-1"]
    h.ctl.shutdown(timeout=WAIT)


def test_on_press_ignored_after_shutdown(tmp_path):
    h = Harness(tmp_path)
    h.ctl.shutdown(timeout=WAIT)
    h.ctl.on_press()  # a hotkey callback racing quit must not start a recording
    assert h.captures == []
    assert h.status.values[-1] == "ready"


def test_last_claude_prompt_none_when_uncompiled(tmp_path):
    # a session dir exists but was never compiled (no transcript.md yet)
    (tmp_path / "sessions" / "2026-07-04_00-00-00" / "raw").mkdir(parents=True)
    h = Harness(tmp_path)
    assert h.ctl.last_claude_prompt() is None
    h.ctl.shutdown(timeout=WAIT)


def test_shutdown_drains_pending_work(tmp_path):
    gate = threading.Event()
    h = Harness(tmp_path, gate=gate)

    h.ctl.on_press()
    h.ctl.on_release()  # queued behind the gate
    h.ctl.on_press()    # still recording when shutdown arrives

    gate.set()
    h.ctl.shutdown(timeout=WAIT)
    assert h.compiled == [tmp_path / "session-0", tmp_path / "session-1"]
    assert not h.ctl._worker.is_alive()
    assert h.status.values[-1] == "ready"
