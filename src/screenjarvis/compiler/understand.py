"""The understanding stage: Claude reads the whole session — timestamped
transcript, gesture/click timeline, and trail-overlaid frames — and plans the
compiled document (cleaned prose, figure moments, highlights, captions).

This subsumes the lexical trigger list: the model catches references like
"the thing in the corner", tolerates lag between speech and pointing, and
turns a circled area into a region highlight. The heuristic pass in
anchors.py remains the free/offline fallback.
"""

from __future__ import annotations

import base64
import io
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

from ..config import Config
from . import anchors as anchor_mod
from .annotate import render_trail_frame
from .gestures import Gesture
from .keyframes import select_frames
from .render import fmt_clock

SYSTEM_PROMPT = """\
You are the understanding stage of ScreenJarvis, a tool that records a user's
voice, screen, and cursor while they talk about what's on screen, then compiles
an annotated markdown document — an asynchronous screen share.

You receive the spoken transcript with timestamps, a timeline of cursor
gestures / clicks / app switches, and screenshots sampled from the recording.
Each screenshot shows the cursor's recent path as a magenta trail ending in a
dot at that frame's moment.

Produce the compiled document:

- paragraphs: the narration cleaned up for reading. Remove filler words and
  false starts, fix grammar, keep the speaker's meaning, first-person voice,
  and order. Do not invent information that is not in the transcript.
- figures: one for each moment the narration refers to something visible on
  screen. Pick the frame whose moment best matches the reference, attach it
  after the paragraph that makes the reference, and set the highlight to what
  the user indicated: a point where they pointed or clicked; a region when the
  trail shows they circled or swept an area. Highlight coordinates are pixels
  in the image exactly as provided to you. Captions name the concrete thing
  shown (the element, value, or error — not "the screen").
- title: a short, specific title for the session.

Not every frame needs a figure. Include exactly the moments a reader needs in
order to follow the narration."""


class Highlight(BaseModel):
    kind: Literal["point", "region"]
    x: int
    y: int
    width: int | None = None   # region only
    height: int | None = None  # region only


class Figure(BaseModel):
    frame: int                 # index into the provided frame list
    paragraph: int             # figure is placed after this paragraph (0-based)
    highlight: Highlight | None
    caption: str


class SessionPlan(BaseModel):
    title: str
    paragraphs: list[str]
    figures: list[Figure]


@dataclass
class SelectedFrame:
    ev: dict            # the frame event (path, t, mon, ...)
    model_width: int    # width of the image as shown to the model


def plan_session(session_dir: Path, transcript: dict, events: dict,
                 gestures: list[Gesture], cfg: Config) -> tuple[SessionPlan, list[SelectedFrame]]:
    frames = _select(session_dir, transcript, events, gestures, cfg)
    if not frames:
        raise RuntimeError("no frames captured; nothing for the model to look at")
    content = _build_content(session_dir, transcript, events, gestures, frames, cfg)
    plan = _call_claude(SYSTEM_PROMPT, content, cfg)
    return _validated(plan, frames), frames


def _select(session_dir: Path, transcript: dict, events: dict,
            gestures: list[Gesture], cfg: Config) -> list[SelectedFrame]:
    candidates: list[tuple[float, int]] = []
    candidates += [(c["t"], 0) for c in events.get("clicks", [])]
    candidates += [((g.t_start + g.t_end) / 2, 1) for g in gestures if g.kind != "dwell"]
    words = transcript["words"]
    for i, j, _phrase in anchor_mod.find_trigger_spans(words, anchor_mod.DEFAULT_TRIGGER_PHRASES):
        candidates.append(((words[i]["start"] + words[j]["end"]) / 2, 2))
    picked = select_frames(session_dir, events.get("frames", []), candidates, cfg.max_llm_frames)
    return [SelectedFrame(ev=f, model_width=cfg.llm_image_width) for f in picked]


def _build_content(session_dir: Path, transcript: dict, events: dict,
                   gestures: list[Gesture], frames: list[SelectedFrame], cfg: Config) -> list[dict]:
    lines = ["TRANSCRIPT (timestamped segments):"]
    lines += [f"[{fmt_clock(s['start'])}] {s['text'].strip()}" for s in transcript["segments"]]

    lines.append("")
    lines.append("EVENT TIMELINE:")
    timeline: list[tuple[float, str]] = []
    for g in gestures:
        span = f"[{fmt_clock(g.t_start)}–{fmt_clock(g.t_end)}]"
        if g.kind == "circle":
            timeline.append((g.t_start, f"{span} cursor circles an area (~{g.region[2]}×{g.region[3]} px)"))
        elif g.kind == "wiggle":
            timeline.append((g.t_start, f"{span} cursor wiggles in place (emphasis)"))
        else:
            timeline.append((g.t_start, f"{span} cursor rests in one spot"))
    timeline += [(c["t"], f"[{fmt_clock(c['t'])}] mouse click") for c in events.get("clicks", [])]
    timeline += [(w["t"], f"[{fmt_clock(w['t'])}] active app → {w['app']}") for w in events.get("windows", [])]
    lines += [text for _t, text in sorted(timeline)] or ["(none)"]

    lines.append("")
    lines.append(f"FRAMES ({len(frames)} screenshots, in time order, cursor trail overlaid):")
    content: list[dict] = [{"type": "text", "text": "\n".join(lines)}]

    cursor_samples = events.get("cursor", [])
    for idx, sf in enumerate(frames):
        img = render_trail_frame(session_dir / sf.ev["path"], sf.ev, cursor_samples,
                                 sf.ev["t"], width=sf.model_width)
        sf.model_width = img.width  # actual width after (no-op) downscale
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=80)
        content.append({"type": "text", "text": f"Frame {idx} — at {fmt_clock(sf.ev['t'])}:"})
        content.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/jpeg",
                "data": base64.standard_b64encode(buf.getvalue()).decode(),
            },
        })
    return content


def _call_claude(system: str, content: list[dict], cfg: Config) -> SessionPlan:
    import anthropic

    client = anthropic.Anthropic()
    response = client.messages.parse(
        model=cfg.llm_model,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        system=system,
        messages=[{"role": "user", "content": content}],
        output_format=SessionPlan,
    )
    plan = getattr(response, "parsed_output", None)
    if plan is None:
        raise RuntimeError(f"model returned no structured output (stop_reason={response.stop_reason})")
    return plan


def _validated(plan: SessionPlan, frames: list[SelectedFrame]) -> SessionPlan:
    if not plan.paragraphs:
        raise RuntimeError("model returned an empty document")
    last_para = len(plan.paragraphs) - 1
    figures = []
    for fig in plan.figures:
        if not 0 <= fig.frame < len(frames):
            continue
        fig.paragraph = min(max(fig.paragraph, 0), last_para)
        figures.append(fig)
    plan.figures = figures
    return plan
