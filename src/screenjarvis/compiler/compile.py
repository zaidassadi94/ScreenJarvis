"""The pipeline: events + audio -> transcript -> understanding -> figures -> transcript.md.

Two interpreters over the same recording:

- smart — Claude reads the whole session (transcript + gesture timeline +
  trail-overlaid frames) and plans prose, figures, and highlights.
- basic — the deterministic heuristic: trigger phrases x cursor log x clicks.
  Free, offline, and the fallback whenever smart mode is off or fails.

A failed compile never loses a recording; the bundle stays on disk either way.
"""

from __future__ import annotations

import dataclasses
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from .. import session as S
from ..config import Config
from . import anchors as anchor_mod
from .annotate import annotate_frame
from .gestures import Gesture, detect_gestures
from .render import fmt_clock, render_markdown, render_plan_markdown
from .stt import load_transcript, pick_backend, transcribe


@dataclass
class FigureOut:
    path: str      # images/fig-01.jpg
    t: float
    label: str     # phrase (basic) or caption (smart)
    via: str       # "click" | "phrase" | "claude"


@dataclass
class CompileResult:
    session_dir: Path
    md_path: Path
    mode: str      # "smart" | "basic"
    words: int
    segments: int
    figures: list[FigureOut]
    anchors: list[anchor_mod.Anchor]  # basic mode only


def load_events(path: Path) -> dict:
    out: dict = {"cursor": [], "clicks": [], "frames": [], "windows": [], "end": None}
    kinds = {"cursor": "cursor", "click": "clicks", "frame": "frames", "window": "windows"}
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        ev = json.loads(line)
        kind = ev.get("type")
        if kind in kinds:
            out[kinds[kind]].append(ev)
        elif kind == "end":
            out["end"] = ev
    for key in ("cursor", "clicks", "frames", "windows"):
        out[key].sort(key=lambda e: e["t"])
    return out


def compile_session(session_dir: Path, cfg: Config, stt: str | None = None,
                    smart: str | None = None) -> CompileResult:
    session_dir = session_dir.resolve()
    events = load_events(S.events_path(session_dir))
    transcript = _get_transcript(session_dir, stt or cfg.stt)
    gestures = detect_gestures(events["cursor"])
    (session_dir / "raw" / "gestures.json").write_text(
        json.dumps([dataclasses.asdict(g) for g in gestures], indent=1)
    )

    mode = smart or cfg.smart
    if mode == "on" or (mode == "auto" and os.environ.get("ANTHROPIC_API_KEY")):
        try:
            return _compile_smart(session_dir, cfg, transcript, events, gestures)
        except Exception as exc:
            print(f"smart compile failed ({exc}); falling back to basic mode.", file=sys.stderr)
    return _compile_basic(session_dir, cfg, transcript, events, gestures)


def _get_transcript(session_dir: Path, choice: str) -> dict:
    tj = S.transcript_json_path(session_dir)
    if choice in ("auto", "json") and tj.exists():
        return load_transcript(tj)
    if choice == "json":
        raise SystemExit(f"--stt json requested but {tj} does not exist.")
    audio = S.audio_path(session_dir)
    if not audio.exists():
        # a session left behind incomplete — recording interrupted before the
        # audio was saved (e.g. the app was quit mid-recording). Nothing to
        # transcribe; say so plainly rather than letting open() blow up.
        raise SystemExit(
            f"This recording is incomplete — no audio was saved ({audio.name} is "
            "missing), so it was probably interrupted before it finished. "
            "Make a fresh recording and try again."
        )
    backend = pick_backend(choice)
    transcript = transcribe(audio, backend)
    tj.write_text(json.dumps(transcript, indent=1))
    return transcript


def _session_duration(transcript: dict, events: dict) -> float:
    return max(
        transcript.get("duration") or 0.0,
        events["end"]["t"] if events.get("end") else 0.0,
        events["frames"][-1]["t"] if events["frames"] else 0.0,
    )


def _compile_smart(session_dir: Path, cfg: Config, transcript: dict,
                   events: dict, gestures: list[Gesture]) -> CompileResult:
    from .understand import plan_session

    plan, frames = plan_session(session_dir, transcript, events, gestures, cfg)
    (session_dir / "raw" / "plan.json").write_text(
        json.dumps({"model": cfg.llm_model,
                    "frames": [{"index": i, "t": sf.ev["t"], "path": sf.ev["path"]}
                               for i, sf in enumerate(frames)],
                    "plan": plan.model_dump()}, indent=1)
    )

    S.images_dir(session_dir).mkdir(exist_ok=True)
    ordered = sorted(plan.figures, key=lambda f: (f.paragraph, frames[f.frame].ev["t"]))
    placed: list[tuple[int, str, str]] = []
    figures: list[FigureOut] = []
    for n, fig in enumerate(ordered, start=1):
        sf = frames[fig.frame]
        fig_rel = f"images/fig-{n:02d}.jpg"
        h = fig.highlight
        point = (h.x, h.y) if h and h.kind == "point" else None
        region = (h.x, h.y, h.width or 60, h.height or 60) if h and h.kind == "region" else None
        if point is None and region is None:
            point = (sf.model_width / 2, sf.model_width / 2)  # centre fallback, rare
        annotate_frame(
            session_dir / sf.ev["path"], sf.ev, session_dir / fig_rel,
            point=point, region=region, image_space_width=sf.model_width,
            crop=cfg.crop, quality=cfg.figure_quality,
        )
        caption = f"{fig.caption.strip()} ({fmt_clock(sf.ev['t'])})"
        placed.append((fig.paragraph, fig_rel, caption))
        figures.append(FigureOut(path=fig_rel, t=sf.ev["t"], label=fig.caption.strip(), via="claude"))

    md = render_plan_markdown(plan.title, plan.paragraphs, placed,
                              started=S.started_at(session_dir),
                              duration=_session_duration(transcript, events))
    S.transcript_md_path(session_dir).write_text(md)
    return CompileResult(session_dir=session_dir, md_path=S.transcript_md_path(session_dir),
                         mode="smart", words=len(transcript["words"]),
                         segments=len(transcript["segments"]), figures=figures, anchors=[])


def _compile_basic(session_dir: Path, cfg: Config, transcript: dict,
                   events: dict, gestures: list[Gesture]) -> CompileResult:
    phrases = list(cfg.trigger_phrases or anchor_mod.DEFAULT_TRIGGER_PHRASES)
    phrases += list(cfg.extra_trigger_phrases)
    found = anchor_mod.detect(transcript, events, phrases)
    circles = [g for g in gestures if g.kind == "circle"]

    S.images_dir(session_dir).mkdir(exist_ok=True)
    figures: list[FigureOut] = []
    for n, anchor in enumerate(found, start=1):
        fig_rel = f"images/fig-{n:02d}.jpg"
        # a circle gesture around the same moment upgrades the point to a region
        circled = next((g for g in circles if g.overlaps(anchor.t - 0.75, anchor.t_point + 0.75)), None)
        anchor.region = circled.region if circled else None
        anchor.ring = annotate_frame(
            session_dir / anchor.frame["path"], anchor.frame, session_dir / fig_rel,
            point=None if anchor.region else anchor.cursor, region=anchor.region,
            crop=cfg.crop, quality=cfg.figure_quality,
        )
        anchor.figure = fig_rel
        figures.append(FigureOut(path=fig_rel, t=anchor.t, label=f"“{anchor.phrase}”",
                                 via="click" if anchor.clicked else "phrase"))

    md = render_markdown(transcript, found, started=S.started_at(session_dir),
                         duration=_session_duration(transcript, events))
    S.transcript_md_path(session_dir).write_text(md)
    S.anchors_json_path(session_dir).write_text(
        json.dumps([_anchor_as_dict(a) for a in found], indent=1)
    )
    return CompileResult(session_dir=session_dir, md_path=S.transcript_md_path(session_dir),
                         mode="basic", words=len(transcript["words"]),
                         segments=len(transcript["segments"]), figures=figures, anchors=found)


def _anchor_as_dict(anchor: anchor_mod.Anchor) -> dict:
    d = dataclasses.asdict(anchor)
    d["frame"] = anchor.frame["path"]
    d["time"] = fmt_clock(anchor.t)
    return d
