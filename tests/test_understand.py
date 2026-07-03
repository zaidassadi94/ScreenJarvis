"""Smart-mode plumbing, with the Claude call stubbed out (no network in tests)."""

import json

from PIL import Image

from screenjarvis.compiler import understand
from screenjarvis.compiler.compile import compile_session
from screenjarvis.compiler.understand import Figure, Highlight, SessionPlan
from screenjarvis.config import Config
from screenjarvis.devtools.synth import make_synthetic_session


def _red_near(img, cx, cy, window=60):
    for x in range(max(cx - window, 0), min(cx + window, img.width - 1)):
        for y in range(max(cy - window, 0), min(cy + window, img.height - 1)):
            p = img.getpixel((x, y))
            if p[0] > 170 and p[1] < 120 and p[2] < 120:
                return True
    return False


def _fake_plan(frame_count: int) -> SessionPlan:
    return SessionPlan(
        title="Pricing page overflow bug",
        paragraphs=[
            "We found a layout bug on the pricing page.",
            "The middle card overflows its container when billing is set to annual.",
            "The culprit is the min-width in the .price-card rule.",
        ],
        figures=[
            Figure(frame=0, paragraph=1,
                   highlight=Highlight(kind="point", x=512, y=490), caption="The overflowing Pro card"),
            Figure(frame=min(1, frame_count - 1), paragraph=2,
                   highlight=Highlight(kind="region", x=110, y=280, width=210, height=180),
                   caption="The .price-card rule block"),
            Figure(frame=99, paragraph=0, highlight=None, caption="bogus frame index — dropped"),
        ],
    )


def test_smart_compile_with_stubbed_model(tmp_path, monkeypatch):
    sdir = make_synthetic_session(tmp_path / "2026-07-03_17-00-00")
    captured = {}

    def fake_call(system, content, cfg):
        captured["system"] = system
        captured["images"] = [b for b in content if b.get("type") == "image"]
        captured["text"] = "\n".join(b["text"] for b in content if b.get("type") == "text")
        return _fake_plan(frame_count=len(captured["images"]))

    monkeypatch.setattr(understand, "_call_claude", fake_call)
    cfg = Config(sessions_dir=tmp_path)
    result = compile_session(sdir, cfg, stt="json", smart="on")

    assert result.mode == "smart"
    assert len(result.figures) == 2  # the bogus frame index was dropped
    assert all(f.via == "claude" for f in result.figures)

    # the model was shown real context: timeline, transcript, trail frames
    assert "TRANSCRIPT" in captured["text"]
    assert "cursor circles an area" in captured["text"]
    assert "mouse click" in captured["text"]
    assert 2 <= len(captured["images"]) <= cfg.max_llm_frames

    md = (sdir / "transcript.md").read_text()
    assert md.startswith("## Pricing page overflow bug")
    assert "min-width" in md
    fig1, fig2 = md.index("fig-01.jpg"), md.index("fig-02.jpg")
    para2, para3 = md.index("middle card overflows"), md.index("culprit")
    assert para2 < fig1 < para3 < fig2

    # region highlight rendered (in model-image space, mapped back to the frame)
    plan = json.loads((sdir / "raw" / "plan.json").read_text())
    assert plan["model"] == cfg.llm_model
    img2 = Image.open(sdir / "images" / "fig-02.jpg")
    scale = img2.width / 1024  # model saw a 1024-wide image
    assert _red_near(img2, round((110 + 210 / 2) * scale), round((280 + 180 / 2) * scale), window=260)


def test_smart_failure_falls_back_to_basic(tmp_path, monkeypatch, capsys):
    sdir = make_synthetic_session(tmp_path / "2026-07-03_18-00-00")

    def broken_call(system, content, cfg):
        raise RuntimeError("api unreachable")

    monkeypatch.setattr(understand, "_call_claude", broken_call)
    result = compile_session(sdir, Config(sessions_dir=tmp_path), stt="json", smart="on")

    assert result.mode == "basic"
    assert len(result.figures) == 2  # the heuristic path still delivered
    assert "falling back to basic mode" in capsys.readouterr().err


def test_smart_off_never_touches_the_model(tmp_path, monkeypatch):
    sdir = make_synthetic_session(tmp_path / "2026-07-03_19-00-00")

    def must_not_run(system, content, cfg):
        raise AssertionError("model called despite smart=off")

    monkeypatch.setattr(understand, "_call_claude", must_not_run)
    result = compile_session(sdir, Config(sessions_dir=tmp_path), stt="json", smart="off")
    assert result.mode == "basic"
