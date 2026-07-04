"""Regression tests for recorder shutdown (no mic or screen needed).

threading.Thread has an internal _stop() *method* that join()/is_alive() call
once a thread has finished. A subclass that keeps its shutdown flag in an
attribute named `_stop` shadows that method, and every clean stop then crashes
with TypeError: 'Event' object is not callable.
"""

import screenjarvis.recorder.capture as capture_mod
from screenjarvis.config import Config
from screenjarvis.recorder.capture import CaptureSession
from screenjarvis.recorder.events import AppWatcher, Clock, CursorTracker, EventLog
from screenjarvis.recorder.frames import FrameGrabber


def _capture_threads(tmp_path, log):
    clock = Clock()
    return [
        CursorTracker(clock, log, 15.0),
        FrameGrabber(tmp_path, clock, log, lambda: None, fps=2.0, quality=80, max_width=1600),
        AppWatcher(clock, log),
    ]


def test_join_after_stop_does_not_crash(tmp_path):
    log = EventLog(tmp_path / "events.jsonl")
    for thread in _capture_threads(tmp_path, log):
        thread.run = lambda: None  # skip platform capture; exercise the Thread lifecycle only
        thread.start()
        thread.stop()
        thread.join(timeout=2.0)  # raised TypeError while `_stop` shadowed Thread._stop
        assert not thread.is_alive()
    log.close()


class _FakeRecorder:
    """Stands in for a sub-recorder; records whether it was stopped."""
    started = []

    def __init__(self, *a, **k):
        self.stopped = False
        self.position = None

    def start(self):
        _FakeRecorder.started.append(self)

    def stop(self):
        self.stopped = True

    def join(self, timeout=None):
        pass

    def request_click_frame(self):
        pass


def test_partial_start_failure_cleans_up_and_leaves_no_junk(tmp_path, monkeypatch):
    # a sub-recorder failing mid-start must tear down the ones already running
    # and remove the just-created session dir (the resident app catches the
    # exception and keeps going, so a leak here would be a hot mic forever)
    _FakeRecorder.started = []
    for name in ("AudioRecorder", "CursorTracker", "FrameGrabber", "AppWatcher"):
        monkeypatch.setattr(capture_mod, name, _FakeRecorder)

    class BoomClicks(_FakeRecorder):
        def start(self):
            raise RuntimeError("input monitoring denied")

    monkeypatch.setattr(capture_mod, "ClickWatcher", BoomClicks)

    cap = CaptureSession(Config(sessions_dir=tmp_path / "sessions"))
    import pytest
    with pytest.raises(RuntimeError, match="input monitoring denied"):
        cap.start()

    assert cap.session_dir is None
    assert list((tmp_path / "sessions").iterdir()) == []  # no orphan session dir
    assert all(r.stopped for r in _FakeRecorder.started)  # everything torn down
    assert cap.stop() is None  # stop after a failed start is a safe no-op


def test_event_log_drops_writes_after_close(tmp_path):
    log = EventLog(tmp_path / "events.jsonl")
    log.write(t=0.0, type="cursor", x=1, y=2)
    log.close()
    log.write(t=0.1, type="cursor", x=3, y=4)  # late event from a capture thread: dropped
    assert len((tmp_path / "events.jsonl").read_text().splitlines()) == 1
