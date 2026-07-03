"""End-to-end: synthetic session -> compile -> verify figures, ring placement, markdown."""

from PIL import Image

from screenjarvis.compiler.compile import compile_session
from screenjarvis.config import Config
from screenjarvis.devtools.synth import CARD_TARGET, RULE_TARGET, make_synthetic_session


def _has_red_ring(img: Image.Image, cx: int, cy: int, window: int = 50) -> bool:
    """A red-dominant pixel within `window` px of (cx, cy) — the drawn ring."""
    for x in range(max(cx - window, 0), min(cx + window, img.width - 1)):
        for y in range(max(cy - window, 0), min(cy + window, img.height - 1)):
            p = img.getpixel((x, y))
            if p[0] > 170 and p[1] < 120 and p[2] < 120:
                return True
    return False


def test_end_to_end(tmp_path):
    sdir = tmp_path / "2026-07-03_14-22-05"
    result = compile_session(
        make_synthetic_session(sdir), Config(sessions_dir=tmp_path), stt="json"
    )

    assert [a.phrase for a in result.anchors] == ["look at this", "right here"]
    assert not result.anchors[0].clicked
    assert result.anchors[1].clicked
    assert result.anchors[1].frame["reason"] == "click"

    md = (sdir / "transcript.md").read_text()
    assert md.startswith("## Session — 2026-07-03 14:22 (44s)")
    assert "“look at this”" in md and "“right here”" in md

    # figures land right after the sentence that pointed at them
    fig1, fig2 = md.index("images/fig-01.jpg"), md.index("images/fig-02.jpg")
    seg2, seg3 = md.index("middle card overflows"), md.index("flex rule right here")
    assert seg2 < fig1 < seg3 < fig2
    # and the decoy sentence produced no figure
    assert len(result.anchors) == 2

    # the ring is drawn where the cursor actually was
    fig1_img = Image.open(sdir / "images" / "fig-01.jpg")
    fig2_img = Image.open(sdir / "images" / "fig-02.jpg")
    assert _has_red_ring(fig1_img, *CARD_TARGET)
    assert _has_red_ring(fig2_img, *RULE_TARGET)

    # bundle metadata for phase 2
    assert (sdir / "raw" / "anchors.json").exists()


def test_recompile_is_idempotent(tmp_path):
    sdir = make_synthetic_session(tmp_path / "2026-07-03_15-00-00")
    cfg = Config(sessions_dir=tmp_path)
    first = compile_session(sdir, cfg, stt="json").md_path.read_text()
    second = compile_session(sdir, cfg, stt="json").md_path.read_text()
    assert first == second


def test_region_crop_keeps_ring_visible(tmp_path):
    sdir = make_synthetic_session(tmp_path / "2026-07-03_16-00-00")
    cfg = Config(sessions_dir=tmp_path, crop="region")
    result = compile_session(sdir, cfg, stt="json")
    img = Image.open(sdir / "images" / "fig-01.jpg")
    assert img.width <= 1280 and img.height <= 820
    ring_x, ring_y = result.anchors[0].ring
    assert _has_red_ring(img, round(ring_x), round(ring_y))
