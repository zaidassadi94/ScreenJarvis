"""Frame selection for the understanding stage.

An LLM shouldn't be handed every frame of a session — it gets a shortlist:
the first frame of each scene (detected by a tiny perceptual diff) plus the
frames nearest each candidate moment (clicks, gestures, pointing phrases),
capped to a budget. Priority: clicks > gestures > phrases > scene starts.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

SCENE_THRESHOLD = 14.0  # mean abs pixel diff (0-255) on a 16x10 grayscale thumb


def _signature(path: Path) -> list[int]:
    with Image.open(path) as img:
        return list(img.convert("L").resize((16, 10)).tobytes())


def scene_start_indices(frames: list[dict], session_dir: Path) -> list[int]:
    starts: list[int] = []
    prev = None
    for k, frame in enumerate(frames):
        sig = _signature(session_dir / frame["path"])
        if prev is None or sum(abs(a - b) for a, b in zip(sig, prev)) / len(sig) >= SCENE_THRESHOLD:
            starts.append(k)
        prev = sig
    return starts


def _nearest(frames: list[dict], t: float) -> dict:
    return min(frames, key=lambda f: abs(f["t"] - t))


def select_frames(session_dir: Path, frames: list[dict],
                  candidate_times: list[tuple[float, int]], max_frames: int) -> list[dict]:
    """candidate_times: (t, priority) — lower priority number = more important."""
    if not frames:
        return []
    picked: dict[str, dict] = {}

    for t, _priority in sorted(candidate_times, key=lambda c: c[1]):
        if len(picked) >= max_frames:
            break
        frame = _nearest(frames, t)
        picked.setdefault(frame["path"], frame)

    for idx in scene_start_indices(frames, session_dir):
        if len(picked) >= max_frames:
            break
        picked.setdefault(frames[idx]["path"], frames[idx])

    if len(picked) < max_frames:  # cheap grounding: how the session ended
        last = frames[-1]
        picked.setdefault(last["path"], last)

    return sorted(picked.values(), key=lambda f: f["t"])
