"""The pipeline: events + audio -> transcript -> anchors -> figures -> transcript.md."""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass
from pathlib import Path

from .. import session as S
from ..config import Config
from . import anchors as anchor_mod
from .annotate import annotate_frame
from .render import fmt_clock, render_markdown
from .stt import load_transcript, pick_backend, transcribe


@dataclass
class CompileResult:
    session_dir: Path
    md_path: Path
    words: int
    segments: int
    anchors: list[anchor_mod.Anchor]


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


def _get_transcript(session_dir: Path, choice: str) -> dict:
    tj = S.transcript_json_path(session_dir)
    if choice in ("auto", "json") and tj.exists():
        return load_transcript(tj)
    if choice == "json":
        raise SystemExit(f"--stt json requested but {tj} does not exist.")
    backend = pick_backend(choice)
    transcript = transcribe(S.audio_path(session_dir), backend)
    tj.write_text(json.dumps(transcript, indent=1))
    return transcript


def compile_session(session_dir: Path, cfg: Config, stt: str | None = None) -> CompileResult:
    session_dir = session_dir.resolve()
    events = load_events(S.events_path(session_dir))
    transcript = _get_transcript(session_dir, stt or cfg.stt)

    phrases = list(cfg.trigger_phrases or anchor_mod.DEFAULT_TRIGGER_PHRASES)
    phrases += list(cfg.extra_trigger_phrases)
    found = anchor_mod.detect(transcript, events, phrases)

    S.images_dir(session_dir).mkdir(exist_ok=True)
    for n, anchor in enumerate(found, start=1):
        fig_rel = f"images/fig-{n:02d}.jpg"
        anchor.ring = annotate_frame(
            session_dir / anchor.frame["path"], anchor.frame, anchor.cursor,
            session_dir / fig_rel, crop=cfg.crop, quality=cfg.figure_quality,
        )
        anchor.figure = fig_rel

    duration = max(
        transcript.get("duration") or 0.0,
        events["end"]["t"] if events.get("end") else 0.0,
        events["frames"][-1]["t"] if events["frames"] else 0.0,
    )
    md = render_markdown(transcript, found, started=S.started_at(session_dir), duration=duration)
    S.transcript_md_path(session_dir).write_text(md)
    S.anchors_json_path(session_dir).write_text(
        json.dumps([_anchor_as_dict(a) for a in found], indent=1)
    )
    return CompileResult(
        session_dir=session_dir, md_path=S.transcript_md_path(session_dir),
        words=len(transcript["words"]), segments=len(transcript["segments"]), anchors=found,
    )


def _anchor_as_dict(anchor: anchor_mod.Anchor) -> dict:
    d = dataclasses.asdict(anchor)
    d["frame"] = anchor.frame["path"]
    d["time"] = fmt_clock(anchor.t)
    return d
