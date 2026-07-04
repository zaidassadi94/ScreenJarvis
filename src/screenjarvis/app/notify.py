"""macOS user feedback via stock CLI tools (osascript, afplay, pbcopy, open).

No rumps here: these are plain subprocess calls, safe from any thread, so the
platform-free controller can use them and tests can monkeypatch them.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

_SOUNDS = {"start": "Pop", "stop": "Bottle", "done": "Glass", "error": "Basso"}


def _escape(s: str) -> str:
    # backslashes first, then quotes — safe to embed in an AppleScript literal
    return s.replace("\\", "\\\\").replace('"', '\\"')


def notify(title: str, message: str) -> None:
    script = f'display notification "{_escape(message)}" with title "{_escape(title)}"'
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


def play(event: str, *, enabled: bool = True) -> None:
    name = _SOUNDS.get(event)
    if not enabled or name is None:
        return
    path = Path(f"/System/Library/Sounds/{name}.aiff")
    if path.exists():
        subprocess.Popen(["afplay", str(path)])  # fire-and-forget; never block recording


def copy_to_clipboard(text: str) -> None:
    subprocess.run(["pbcopy"], input=text.encode(), check=False)


def open_path(path) -> None:
    subprocess.run(["open", str(path)], check=False)
