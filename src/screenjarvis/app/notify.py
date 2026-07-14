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


def paste_text_into_frontmost(text: str) -> None:
    """Wispr-style: put the text on the clipboard, then Cmd-V into whatever app
    has focus. ScreenJarvis is a menu-bar accessory (LSUIElement) so it never
    steals focus — the keystroke lands in the text box the user was in. Needs
    Accessibility + Automation (System Events) permission."""
    copy_to_clipboard(text)
    subprocess.run(
        ["osascript", "-e",
         'tell application "System Events" to keystroke "v" using command down'],
        check=False, capture_output=True,
    )


def copy_rich(html_path) -> None:
    """Put text + screenshots on the clipboard so a paste into Notion / Google
    Docs / Mail carries the figures inline. macOS has no rich-text pipe, so we
    convert the HTML to RTF with `textutil` (which embeds the referenced images)
    and load that onto the pasteboard. Relative image paths in the HTML resolve
    against its own directory, so the doc is written beside images/."""
    html_path = Path(html_path)
    rtf_path = html_path.with_suffix(".rtf")
    conv = subprocess.run(
        ["textutil", "-convert", "rtf", "-output", str(rtf_path), str(html_path)],
        check=False, capture_output=True,
    )
    if conv.returncode != 0 or not rtf_path.exists():
        copy_to_clipboard(html_path.read_text())  # degrade to plain text
        return
    script = f'set the clipboard to (read (POSIX file "{_escape(str(rtf_path))}") as «class RTF »)'
    subprocess.run(["osascript", "-e", script], check=False, capture_output=True)


def prompt_secret(title: str, message: str, default: str = "") -> str | None:
    """A native password-style dialog (osascript) so keys can be entered without
    a Terminal. Returns the text, or None if the user cancels."""
    script = (
        f'display dialog "{_escape(message)}" with title "{_escape(title)}" '
        f'default answer "{_escape(default)}" with hidden answer '
        f'buttons {{"Cancel", "Save"}} default button "Save"'
    )
    result = subprocess.run(["osascript", "-e", script], capture_output=True, text=True)
    if result.returncode != 0:
        return None  # Cancel makes osascript exit non-zero
    marker = "text returned:"
    idx = result.stdout.find(marker)
    return result.stdout[idx + len(marker):].strip() if idx != -1 else ""


def open_path(path) -> None:
    subprocess.run(["open", str(path)], check=False)
