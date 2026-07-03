"""Screen frame capture: a steady ~2 fps ring of JPEGs from the display under
the cursor, plus an immediate capture whenever the user clicks.

Screenshots don't include the cursor; the pointer ring is drawn at compile time
from the cursor log, which is also what makes it exact.

Each frame event records the monitor's logical rectangle and the saved image
size, so the compiler can map global cursor coordinates into image pixels
regardless of HiDPI capture scale or downscaling:

    scale  = saved_width / monitor_logical_width
    ring_x = (cursor_x - monitor_left) * scale
"""

from __future__ import annotations

import threading
import time
from pathlib import Path

from .events import Clock, EventLog


class FrameGrabber(threading.Thread):
    CLICK_DEBOUNCE = 0.15

    def __init__(self, session_dir: Path, clock: Clock, log: EventLog, get_cursor,
                 *, fps: float, quality: int, max_width: int):
        super().__init__(daemon=True, name="sj-frames")
        self._frames_dir = session_dir / "raw" / "frames"
        self._clock = clock
        self._log = log
        self._get_cursor = get_cursor
        self._interval = 1.0 / fps
        self._quality = quality
        self._max_width = max_width
        self._stop = threading.Event()
        self._click_flag = threading.Event()

    def request_click_frame(self) -> None:
        self._click_flag.set()

    def stop(self) -> None:
        self._stop.set()

    def run(self) -> None:
        import mss
        from PIL import Image

        last_capture = -1e9
        with mss.mss() as sct:
            monitors = sct.monitors
            while not self._stop.is_set():
                now = self._clock.t()
                click = self._click_flag.is_set()
                if click:
                    self._click_flag.clear()
                    if now - last_capture < self.CLICK_DEBOUNCE:
                        click = False
                if not (click or now - last_capture >= self._interval):
                    time.sleep(0.03)
                    continue
                mon = self._pick_monitor(monitors)
                try:
                    shot = sct.grab(mon)
                except Exception:
                    time.sleep(0.2)
                    continue
                t = self._clock.t()
                img = Image.frombytes("RGB", (shot.width, shot.height), shot.bgra, "raw", "BGRX")
                if img.width > self._max_width:
                    ratio = self._max_width / img.width
                    img = img.resize((self._max_width, round(img.height * ratio)), Image.LANCZOS)
                name = f"{int(t * 1000):09d}.jpg"
                img.save(self._frames_dir / name, "JPEG", quality=self._quality)
                self._log.write(
                    t=round(t, 3), type="frame", path=f"raw/frames/{name}",
                    mon={k: mon[k] for k in ("left", "top", "width", "height")},
                    w=img.width, h=img.height,
                    reason="click" if click else "tick",
                )
                last_capture = t

    def _pick_monitor(self, monitors):
        pos = self._get_cursor()
        if pos and len(monitors) > 2:
            x, y = pos
            for mon in monitors[1:]:
                if (mon["left"] <= x < mon["left"] + mon["width"]
                        and mon["top"] <= y < mon["top"] + mon["height"]):
                    return mon
        return monitors[1]
