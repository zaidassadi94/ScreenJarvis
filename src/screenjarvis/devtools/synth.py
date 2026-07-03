"""Generate a synthetic session bundle — no mic or screen needed.

Lets the compiler run end-to-end on any machine (CI, containers): fake
"pricing page" and "devtools" screens, a scripted cursor path with one click,
and a hand-written word-timestamped transcript containing two pointing phrases
plus a decoy ("this week") that must NOT trigger.
"""

from __future__ import annotations

import json
import wave
from pathlib import Path

from PIL import Image, ImageDraw

MON = {"left": 0, "top": 0, "width": 1440, "height": 900}
CARD_TARGET = (720, 690)   # where the middle card crosses the container edge
RULE_TARGET = (320, 514)   # the min-width line in the fake devtools
CLICK_T = 24.6
DURATION = 36.0
FPS = 2.0
SCENE_SWITCH_T = 20.0

SEGMENTS = [
    (0.6, 6.2, "We looked into the billing report this week and found a layout bug on the pricing page."),
    (10.4, 16.6, "Look at this — the middle card overflows its container when the toggle is set to annual."),
    (22.4, 28.2, "The problem is the flex rule right here, the min width is fighting the gap."),
    (30.2, 33.4, "Let's patch it and rerun the visual tests."),
]

# cursor script: (until_t, position) — parked at each spot, lerped between spots
CURSOR_PATH = [
    (9.0, (240, 180)),
    (10.0, CARD_TARGET),
    (16.0, CARD_TARGET),
    (22.0, RULE_TARGET),
    (29.0, RULE_TARGET),
    (36.0, (900, 800)),
]


def _words_from_segments() -> list[dict]:
    words = []
    for start, end, text in SEGMENTS:
        tokens = text.split()
        step = (end - start) / len(tokens)
        for k, token in enumerate(tokens):
            words.append({"word": token, "start": round(start + k * step, 3),
                          "end": round(start + (k + 1) * step, 3)})
    return words


def _cursor_at(t: float) -> tuple[int, int]:
    prev_t, prev_pos = 0.0, CURSOR_PATH[0][1]
    for until, pos in CURSOR_PATH:
        if t <= until:
            span = until - prev_t
            frac = (t - prev_t) / span if span else 1.0
            return (round(prev_pos[0] + frac * (pos[0] - prev_pos[0])),
                    round(prev_pos[1] + frac * (pos[1] - prev_pos[1])))
        prev_t, prev_pos = until, pos
    return CURSOR_PATH[-1][1]


def _draw_pricing(t: float) -> Image.Image:
    img = Image.new("RGB", (MON["width"], MON["height"]), (246, 247, 249))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1440, 70], fill=(28, 32, 44))
    d.text((40, 26), "acme.com/pricing", fill=(235, 235, 240))
    d.text((1330, 26), f"t={t:05.1f}", fill=(120, 130, 150))
    d.text((640, 130), "Billing: Annual", fill=(60, 66, 80))
    d.rectangle([120, 180, 1320, 700], outline=(205, 210, 220), width=2)  # container
    for i, x in enumerate((170, 550, 930)):
        bottom = 760 if i == 1 else 640  # the bug: middle card overflows the container
        d.rectangle([x, 240, x + 340, bottom], fill=(255, 255, 255), outline=(180, 186, 199), width=2)
        d.text((x + 24, 264), ("Basic", "Pro", "Team")[i], fill=(30, 34, 44))
        d.text((x + 24, 304), ("$9", "$29", "$79")[i] + " / mo", fill=(90, 96, 110))
    return img


def _draw_devtools(t: float) -> Image.Image:
    img = Image.new("RGB", (MON["width"], MON["height"]), (32, 34, 40))
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 1440, 60], fill=(24, 26, 31))
    d.text((40, 22), "DevTools — Elements / Styles", fill=(200, 204, 214))
    d.text((1330, 22), f"t={t:05.1f}", fill=(110, 115, 130))
    rules = [".pricing-grid {", "  display: flex;", "  gap: 24px;", "}", "",
             ".price-card {", "  flex: 1 1 0;", "  min-width: 360px;", "  padding: 24px;", "}"]
    for k, line in enumerate(rules):
        color = (255, 196, 88) if "min-width" in line else (168, 214, 168)
        d.text((160, 200 + k * 44), line, fill=color)
    return img


def _scene(t: float) -> Image.Image:
    return _draw_pricing(t) if t < SCENE_SWITCH_T else _draw_devtools(t)


def make_synthetic_session(session_dir: Path) -> Path:
    frames_dir = session_dir / "raw" / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    (session_dir / "images").mkdir(exist_ok=True)

    events: list[dict] = [{"t": 0.0, "type": "window", "app": "Google Chrome"},
                          {"t": SCENE_SWITCH_T, "type": "window", "app": "Google Chrome — DevTools"}]

    t = 0.0
    while t <= DURATION:
        x, y = _cursor_at(t)
        events.append({"t": round(t, 3), "type": "cursor", "x": x, "y": y})
        t += 0.2

    frame_times = [(round(t / 10, 3), "tick") for t in range(2, int(DURATION * 10), 5)]
    frame_times.append((CLICK_T + 0.03, "click"))
    for ft, reason in sorted(frame_times):
        name = f"{int(ft * 1000):09d}.jpg"
        _scene(ft).save(frames_dir / name, "JPEG", quality=80)
        events.append({"t": ft, "type": "frame", "path": f"raw/frames/{name}",
                       "mon": dict(MON), "w": MON["width"], "h": MON["height"], "reason": reason})

    events.append({"t": CLICK_T, "type": "click", "x": RULE_TARGET[0], "y": RULE_TARGET[1], "button": "left"})
    events.append({"t": DURATION, "type": "end"})
    events.sort(key=lambda e: e["t"])
    with open(session_dir / "raw" / "events.jsonl", "w") as f:
        for ev in events:
            f.write(json.dumps(ev, separators=(",", ":")) + "\n")

    words = _words_from_segments()
    transcript = {
        "text": " ".join(seg[2] for seg in SEGMENTS),
        "language": "en",
        "duration": DURATION,
        "segments": [{"start": s, "end": e, "text": text} for s, e, text in SEGMENTS],
        "words": words,
    }
    (session_dir / "raw" / "transcript.json").write_text(json.dumps(transcript, indent=1))

    with wave.open(str(session_dir / "raw" / "audio.wav"), "wb") as wf:  # 1s of silence
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16_000)
        wf.writeframes(b"\x00\x00" * 16_000)
    return session_dir
