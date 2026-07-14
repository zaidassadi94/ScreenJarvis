"""Turn a compiled session into the things you actually consume.

Compilation produces one canonical artifact — `transcript.md` + `images/`.
Everything a user wants to *do* with a session is a projection of that:

- **text** — the cleaned narration with the figures stripped out. This is the
  Wispr-style payload: paste it straight into whatever text box has focus.
- **html** — a single self-contained web page (images embedded as data URIs, so
  it needs no `images/` folder beside it). Opens in any browser, prints to PDF,
  and is the source the macOS rich-clipboard path converts to RTF so pasting
  into Notion / Docs / Mail carries the screenshots along.

This module is platform-agnostic and dependency-free (stdlib + the markdown we
wrote ourselves), so it is fully testable headless. The macOS delivery verbs —
auto-paste, rich clipboard, open — live in app/notify.py and consume what this
produces.

Images are embedded today. Hosting them (upload → URL) is a deferred option; the
single seam is `_image_src`, and `Config.image_hosting` reserves the switch. See
DECISIONS.md.
"""

from __future__ import annotations

import base64
import html
import re
from dataclasses import dataclass
from pathlib import Path

from .. import session as S

_FIGURE_RE = re.compile(r"^!\[(?P<alt>.*)\]\((?P<path>[^)]*)\)\s*$")
_FIG_PREFIX_RE = re.compile(r"^Fig\s+\d+\s+[—-]\s*")
_MIME_BY_SUFFIX = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                   ".gif": "image/gif", ".webp": "image/webp"}


@dataclass
class Figure:
    path: str      # relative to the session dir, e.g. images/fig-01.jpg
    caption: str   # figure label without the "Fig N —" prefix


@dataclass
class Document:
    """A compiled session parsed back out of transcript.md.

    blocks preserve document order: a paragraph is a `str`, a figure is a
    `Figure`. Parsing our own markdown (rather than re-deriving from the plan)
    means the exact same source feeds every output — text, html, and clipboard
    can never drift from what `transcript.md` shows.
    """

    title: str
    subtitle: str            # the "date · duration" meta line ("" if none)
    blocks: list[str | Figure]

    @property
    def paragraphs(self) -> list[str]:
        return [b for b in self.blocks if isinstance(b, str)]

    @property
    def figures(self) -> list[Figure]:
        return [b for b in self.blocks if isinstance(b, Figure)]


def parse_document(session_dir: Path) -> Document:
    md_path = S.transcript_md_path(session_dir)
    if not md_path.exists():
        raise SystemExit(
            f"no compiled document at {md_path} — run `sj compile {session_dir}` first."
        )
    return parse_markdown(md_path.read_text())


def parse_markdown(md: str) -> Document:
    title = ""
    subtitle = ""
    blocks: list[str | Figure] = []
    for raw in md.splitlines():
        line = raw.strip()
        if not line:
            continue
        if not title and line.startswith("## "):
            title = line[3:].strip()
            continue
        if not blocks and not subtitle and line.startswith("*") and line.endswith("*"):
            subtitle = line.strip("*").strip()
            continue
        if m := _FIGURE_RE.match(line):
            caption = _FIG_PREFIX_RE.sub("", m["alt"]).strip()
            blocks.append(Figure(path=m["path"].strip(), caption=caption))
            continue
        blocks.append(line)
    return Document(title=title, subtitle=subtitle, blocks=blocks)


# -- text (Wispr-style paste) -------------------------------------------------

def session_text(session_dir: Path) -> str:
    """Just the spoken narration, cleaned, figures removed — for paste into a
    text box. No title or meta line: those are document furniture, not dictation.
    """
    return "\n\n".join(parse_document(session_dir).paragraphs).strip()


# -- html (self-contained document) -------------------------------------------

_CSS = """\
:root { color-scheme: light dark; }
* { box-sizing: border-box; }
body {
  font: 16px/1.65 -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
  max-width: 720px; margin: 0 auto; padding: 3rem 1.25rem 5rem;
  color: #1a1a1a; background: #fff;
}
h1 { font-size: 1.7rem; line-height: 1.25; margin: 0 0 .25rem; }
.meta { color: #6a6a6a; font-size: .85rem; margin: 0 0 2rem; }
p { margin: 0 0 1.15rem; }
figure { margin: 1.75rem 0; }
figure img {
  width: 100%; height: auto; border-radius: 10px;
  border: 1px solid rgba(0,0,0,.12); box-shadow: 0 2px 14px rgba(0,0,0,.08);
}
figcaption { color: #6a6a6a; font-size: .82rem; margin-top: .5rem; text-align: center; }
@media (prefers-color-scheme: dark) {
  body { color: #e8e8e8; background: #1a1a1a; }
  .meta, figcaption { color: #9a9a9a; }
  figure img { border-color: rgba(255,255,255,.14); box-shadow: 0 2px 18px rgba(0,0,0,.5); }
}
@media print {
  body { max-width: none; padding: 0; color: #000; background: #fff; }
  figure img { box-shadow: none; }
}
"""


def session_html(session_dir: Path, *, embed: bool = True) -> str:
    """A single self-contained HTML document for the session.

    embed=True inlines every figure as a data URI (portable, offline). embed=False
    keeps relative `images/…` refs — used by the rich-clipboard path, where the
    HTML is written into the session dir so a converter can resolve the files.
    """
    doc = parse_document(session_dir)
    title = doc.title or "ScreenJarvis session"
    parts = [
        "<!doctype html>",
        '<html lang="en"><head><meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        f"<title>{html.escape(title)}</title>",
        f"<style>{_CSS}</style></head><body>",
        f"<h1>{html.escape(title)}</h1>",
    ]
    if doc.subtitle:
        parts.append(f'<p class="meta">{html.escape(doc.subtitle)}</p>')
    for block in doc.blocks:
        if isinstance(block, str):
            parts.append(f"<p>{html.escape(block)}</p>")
        else:
            src = _image_src(session_dir, block.path, embed=embed)
            fig = [f'<figure><img src="{src}" alt="{html.escape(block.caption)}">']
            if block.caption:
                fig.append(f"<figcaption>{html.escape(block.caption)}</figcaption>")
            fig.append("</figure>")
            parts.append("".join(fig))
    parts.append("</body></html>")
    return "\n".join(parts) + "\n"


def write_html(session_dir: Path, *, embed: bool = True, name: str = "session.html") -> Path:
    out = session_dir / name
    out.write_text(session_html(session_dir, embed=embed))
    return out


def _image_src(session_dir: Path, rel_path: str, *, embed: bool) -> str:
    """The single seam between embedded and (future) hosted images.

    Today: a data URI when embedding, else the relative path verbatim. A hosting
    backend would slot in here, returning an uploaded URL — see DECISIONS.md.
    """
    if not embed:
        return rel_path
    img = (session_dir / rel_path)
    if not img.exists():
        return rel_path  # missing figure: leave the ref rather than crash the doc
    mime = _MIME_BY_SUFFIX.get(img.suffix.lower(), "image/jpeg")
    data = base64.standard_b64encode(img.read_bytes()).decode()
    return f"data:{mime};base64,{data}"
