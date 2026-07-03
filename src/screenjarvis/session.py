"""Session bundle layout and helpers.

A session is a directory:

    sessions/2026-07-03_14-22-05/
      transcript.md      # the deliverable
      images/            # annotated figures
      raw/
        audio.wav
        events.jsonl     # cursor track, clicks, frames, active app
        frames/          # captured screenshots
        transcript.json  # word-level STT output
        anchors.json     # detected pointing moments
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

STAMP_FMT = "%Y-%m-%d_%H-%M-%S"


def new_session_dir(sessions_dir: Path) -> Path:
    stamp = dt.datetime.now().strftime(STAMP_FMT)
    d = sessions_dir / stamp
    n = 2
    while d.exists():
        d = sessions_dir / f"{stamp}-{n}"
        n += 1
    (d / "raw" / "frames").mkdir(parents=True)
    (d / "images").mkdir()
    return d


def audio_path(d: Path) -> Path:
    return d / "raw" / "audio.wav"


def events_path(d: Path) -> Path:
    return d / "raw" / "events.jsonl"


def frames_dir(d: Path) -> Path:
    return d / "raw" / "frames"


def transcript_json_path(d: Path) -> Path:
    return d / "raw" / "transcript.json"


def anchors_json_path(d: Path) -> Path:
    return d / "raw" / "anchors.json"


def images_dir(d: Path) -> Path:
    return d / "images"


def transcript_md_path(d: Path) -> Path:
    return d / "transcript.md"


def is_session_dir(d: Path) -> bool:
    return (d / "raw").is_dir()


def latest_session(sessions_dir: Path) -> Path | None:
    if not sessions_dir.is_dir():
        return None
    candidates = sorted(p for p in sessions_dir.iterdir() if p.is_dir() and is_session_dir(p))
    return candidates[-1] if candidates else None


def started_at(d: Path) -> dt.datetime:
    try:
        return dt.datetime.strptime(d.name[:19], STAMP_FMT)
    except ValueError:
        return dt.datetime.fromtimestamp(d.stat().st_mtime)
