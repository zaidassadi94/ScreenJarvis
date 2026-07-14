"""Output projections: parse transcript.md back out, then render text / HTML."""

import base64

import pytest
from PIL import Image

from screenjarvis.compiler import deliver

SMART_MD = """\
## Fixing the pricing layout

*2026-07-14 14:22 · 1m 43s*

We need to fix the layout bug on the pricing page. The middle card overflows.

![Fig 1 — pricing page, middle card overflowing (00:12)](images/fig-01.png)

The problem is this flex rule; min-width is fighting the gap.

![Fig 2 — devtools, .price-card rule highlighted (00:31)](images/fig-02.png)
"""

# basic-mode markdown puts date/duration in the heading and has no *meta* line
BASIC_MD = """\
## Session — 2026-07-03 14:22 (44s)

Look at this card overflowing.

![Fig 1 — “look at this” at 00:12](images/fig-01.jpg)
"""


def _session(tmp_path, md, images=("fig-01.png",)):
    (tmp_path / "raw").mkdir()
    (tmp_path / "images").mkdir()
    (tmp_path / "transcript.md").write_text(md)
    for name in images:
        Image.new("RGB", (8, 8), (200, 30, 30)).save(tmp_path / "images" / name)
    return tmp_path


def test_parse_pulls_title_subtitle_paragraphs_and_figures(tmp_path):
    doc = deliver.parse_markdown(SMART_MD)
    assert doc.title == "Fixing the pricing layout"
    assert doc.subtitle == "2026-07-14 14:22 · 1m 43s"
    assert doc.paragraphs == [
        "We need to fix the layout bug on the pricing page. The middle card overflows.",
        "The problem is this flex rule; min-width is fighting the gap.",
    ]
    assert [f.path for f in doc.figures] == ["images/fig-01.png", "images/fig-02.png"]
    # the "Fig N —" prefix is stripped from captions
    assert doc.figures[0].caption == "pricing page, middle card overflowing (00:12)"


def test_basic_mode_heading_has_no_meta_line(tmp_path):
    doc = deliver.parse_markdown(BASIC_MD)
    assert doc.title == "Session — 2026-07-03 14:22 (44s)"
    assert doc.subtitle == ""
    assert doc.paragraphs == ["Look at this card overflowing."]


def test_session_text_is_prose_only(tmp_path):
    s = _session(tmp_path, SMART_MD, images=("fig-01.png", "fig-02.png"))
    text = deliver.session_text(s)
    assert text.startswith("We need to fix the layout bug")
    assert "flex rule" in text
    # no document furniture, no figures
    assert "##" not in text and "![" not in text and "1m 43s" not in text


def test_session_html_embeds_images_as_data_uris(tmp_path):
    s = _session(tmp_path, SMART_MD, images=("fig-01.png", "fig-02.png"))
    html = deliver.session_html(s, embed=True)
    assert "<h1>Fixing the pricing layout</h1>" in html
    assert "data:image/png;base64," in html
    assert "images/fig-01.png" not in html  # embedded, not linked
    # the embedded bytes are the real figure
    raw = (s / "images" / "fig-01.png").read_bytes()
    assert base64.standard_b64encode(raw).decode() in html
    assert "<figcaption>pricing page, middle card overflowing (00:12)</figcaption>" in html


def test_session_html_embed_false_keeps_relative_links(tmp_path):
    s = _session(tmp_path, SMART_MD, images=("fig-01.png", "fig-02.png"))
    html = deliver.session_html(s, embed=False)
    assert 'src="images/fig-01.png"' in html
    assert "data:image" not in html


def test_write_html_writes_beside_images(tmp_path):
    s = _session(tmp_path, SMART_MD, images=("fig-01.png", "fig-02.png"))
    out = deliver.write_html(s)
    assert out == s / "session.html"
    assert out.read_text().startswith("<!doctype html>")


def test_missing_transcript_is_a_clean_error(tmp_path):
    (tmp_path / "raw").mkdir()
    with pytest.raises(SystemExit, match="run `sj compile"):
        deliver.session_text(tmp_path)
