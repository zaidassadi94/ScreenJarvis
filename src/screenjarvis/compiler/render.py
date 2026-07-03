"""Render transcript + anchors into transcript.md (figures land right after the
sentence that pointed at them)."""

from __future__ import annotations

import datetime as dt

from .anchors import Anchor


def fmt_clock(t: float) -> str:
    m, s = divmod(int(round(t)), 60)
    return f"{m:02d}:{s:02d}"


def fmt_duration(seconds: float) -> str:
    m, s = divmod(int(round(seconds)), 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"


def _segment_index_for(anchor: Anchor, segments: list[dict]) -> int:
    for idx, seg in enumerate(segments):
        if seg["start"] <= anchor.word_start < seg["end"]:
            return idx
    return min(range(len(segments)), key=lambda idx: abs(segments[idx]["start"] - anchor.word_start))


def render_markdown(transcript: dict, anchors: list[Anchor], *,
                    started: dt.datetime, duration: float) -> str:
    segments = transcript["segments"]
    by_segment: dict[int, list[tuple[int, Anchor]]] = {}
    for n, anchor in enumerate(anchors, start=1):
        by_segment.setdefault(_segment_index_for(anchor, segments), []).append((n, anchor))

    lines = [f"## Session — {started:%Y-%m-%d %H:%M} ({fmt_duration(duration)})", ""]
    buffer: list[str] = []

    def flush():
        if buffer:
            lines.append(" ".join(buffer))
            lines.append("")
            buffer.clear()

    for idx, seg in enumerate(segments):
        if text := seg["text"].strip():
            buffer.append(text)
        for n, anchor in by_segment.get(idx, ()):
            flush()
            lines.append(f"![Fig {n} — “{anchor.phrase}” at {fmt_clock(anchor.t)}]({anchor.figure})")
            lines.append("")
    flush()
    return "\n".join(lines).rstrip() + "\n"
