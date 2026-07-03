"""Anchor detection: bind deictic speech ("look at this") to a cursor position
and a captured frame.

Bias: over-capture, then curate — an extra figure is a two-second delete, a
missed one kills trust in the tool. Triggers are multi-word phrases to avoid
false fires on bare "this" ("this week", "this is why...").
"""

from __future__ import annotations

import bisect
import re
from dataclasses import dataclass

POINT_LAG = 0.2     # people finish saying "this" slightly before the cursor settles
CLICK_WINDOW = 1.0  # a click this close to the phrase *is* the pointing gesture
FRAME_WINDOW = 0.7  # preferred max distance between pointing moment and frame
MERGE_WINDOW = 2.0  # anchors closer than this are one gesture

DEFAULT_TRIGGER_PHRASES = [
    # explicit look/see/watch
    "look at this", "look at that", "look at these", "look at those",
    "look here", "look right here", "looking at this", "looking at that",
    "see this", "see that", "see here", "see how this", "see how that",
    "watch this", "watch that", "check this out", "check that out",
    "check out this", "check out that", "check this",
    # here/there deixis
    "right here", "right there", "over here", "over there",
    "up here", "up there", "down here", "down there", "this here", "that there",
    # this + common UI nouns
    "this one", "this thing", "this part", "this bit", "this piece",
    "this section", "this area", "this region", "this spot",
    "this error", "this warning", "this message", "this log",
    "this line", "this row", "this column", "this cell", "this value",
    "this button", "this link", "this menu", "this tab", "this panel",
    "this window", "this dialog", "this modal", "this popup",
    "this page", "this screen", "this view", "this form", "this field",
    "this box", "this card", "this icon", "this image", "this chart",
    "this graph", "this table", "this list", "this item", "this element",
    "this file", "this folder", "this function", "this method", "this class",
    "this variable", "this block", "this snippet", "this code", "this text",
    "this number", "this guy",
    # cursor self-reference
    "my cursor", "the cursor", "where my cursor", "where the cursor",
    "pointing at", "pointing to", "i'm pointing",
]

_PUNCT = re.compile(r"[^\w']+")


def norm_token(token: str) -> str:
    return _PUNCT.sub("", token.lower())


@dataclass
class Anchor:
    t: float                          # phrase midpoint (transcript time)
    t_point: float                    # moment used for cursor/frame lookup
    phrase: str
    word_start: float
    word_end: float
    cursor: tuple[int, int] | None
    frame: dict | None                # the chosen frame event
    clicked: bool
    figure: str | None = None         # set by the compile step
    ring: tuple[float, float] | None = None  # ring centre in figure pixels


def find_trigger_spans(words: list[dict], phrases: list[str]) -> list[tuple[int, int, str]]:
    """Return (first_word_index, last_word_index, phrase) matches, longest phrase wins."""
    tokens = [norm_token(w["word"]) for w in words]
    wanted = sorted(
        ((tuple(norm_token(t) for t in p.split()), p) for p in phrases),
        key=lambda item: -len(item[0]),
    )
    spans = []
    for i in range(len(tokens)):
        for p_tokens, phrase in wanted:
            j = i + len(p_tokens)
            if j <= len(tokens) and tuple(tokens[i:j]) == p_tokens:
                spans.append((i, j - 1, phrase))
                break
    spans.sort(key=lambda s: s[0])
    return spans


def cursor_at(samples: list[dict], t: float) -> tuple[int, int] | None:
    """Cursor position at time t, linearly interpolated between logged samples."""
    if not samples:
        return None
    times = [s["t"] for s in samples]
    idx = bisect.bisect_left(times, t)
    if idx <= 0:
        s = samples[0]
        return (s["x"], s["y"])
    if idx >= len(samples):
        s = samples[-1]
        return (s["x"], s["y"])
    a, b = samples[idx - 1], samples[idx]
    if b["t"] - a["t"] > 1.5:  # gap in the log: snap to the nearer sample
        s = a if t - a["t"] <= b["t"] - t else b
        return (s["x"], s["y"])
    frac = (t - a["t"]) / ((b["t"] - a["t"]) or 1e-9)
    return (round(a["x"] + frac * (b["x"] - a["x"])), round(a["y"] + frac * (b["y"] - a["y"])))


def pick_frame(frames: list[dict], t: float, prefer_click: bool) -> dict | None:
    if not frames:
        return None
    if prefer_click:
        click_frames = [f for f in frames if f.get("reason") == "click" and abs(f["t"] - t) <= CLICK_WINDOW]
        if click_frames:
            return min(click_frames, key=lambda f: abs(f["t"] - t))
    near = [f for f in frames if abs(f["t"] - t) <= FRAME_WINDOW]
    pool = near or frames
    return min(pool, key=lambda f: abs(f["t"] - t))


def detect(transcript: dict, events: dict, phrases: list[str] | None = None) -> list[Anchor]:
    phrases = phrases or DEFAULT_TRIGGER_PHRASES
    words = transcript["words"]
    cursor_samples = events.get("cursor", [])
    clicks = events.get("clicks", [])
    frames = events.get("frames", [])

    anchors: list[Anchor] = []
    for i, j, phrase in find_trigger_spans(words, phrases):
        w_start, w_end = words[i]["start"], words[j]["end"]
        t_mid = (w_start + w_end) / 2
        near_clicks = [c for c in clicks if abs(c["t"] - t_mid) <= CLICK_WINDOW]
        click = min(near_clicks, key=lambda c: abs(c["t"] - t_mid)) if near_clicks else None
        t_point = click["t"] if click else w_end + POINT_LAG
        cursor = (click["x"], click["y"]) if click else cursor_at(cursor_samples, t_point)
        anchor = Anchor(
            t=t_mid, t_point=t_point, phrase=phrase, word_start=w_start, word_end=w_end,
            cursor=cursor, frame=pick_frame(frames, t_point, prefer_click=click is not None),
            clicked=click is not None,
        )
        if anchors and anchor.t - anchors[-1].t < MERGE_WINDOW:
            if anchor.clicked and not anchors[-1].clicked:
                anchors[-1] = anchor  # same gesture; the clicked variant is more precise
            continue
        anchors.append(anchor)
    return [a for a in anchors if a.frame is not None and a.cursor is not None]
