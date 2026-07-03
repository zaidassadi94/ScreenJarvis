import math

from screenjarvis.compiler.gestures import detect_gestures


def _track(points):  # [(t, x, y)] -> cursor samples
    return [{"t": t, "x": x, "y": y} for t, x, y in points]


def _circle_track(cx, cy, r, *, t0=0.0, loops=2.0, hz=15, seconds=3.0):
    pts = []
    steps = int(seconds * hz)
    for k in range(steps + 1):
        angle = loops * 2 * math.pi * k / steps
        pts.append((t0 + k / hz, cx + r * math.cos(angle), cy + r * math.sin(angle)))
    return _track(pts)


def test_circle_is_detected_with_region():
    gestures = detect_gestures(_circle_track(500, 400, 120))
    circles = [g for g in gestures if g.kind == "circle"]
    assert len(circles) == 1
    g = circles[0]
    assert abs(g.cx - 500) < 25 and abs(g.cy - 400) < 25
    x, y, w, h = g.region
    assert x < 500 - 100 and x + w > 500 + 100  # region encloses the loop
    assert y < 400 - 100 and y + h > 400 + 100


def test_straight_line_is_not_a_gesture():
    line = _track([(k / 15, 100 + 12 * k, 200 + 5 * k) for k in range(40)])
    assert detect_gestures(line) == []


def test_wiggle_is_detected():
    pts = []
    for k in range(40):  # rapid horizontal shake in place
        pts.append((k / 15, 300 + (30 if k % 2 else -30), 300 + (k % 3)))
    gestures = detect_gestures(_track(pts))
    assert any(g.kind == "wiggle" and abs(g.cx - 300) < 40 for g in gestures)


def test_parked_cursor_is_a_dwell():
    # heartbeat-style sparse samples at one spot
    parked = _track([(float(k), 640, 360) for k in range(5)])
    gestures = detect_gestures(parked)
    assert [g.kind for g in gestures] == ["dwell"]
    assert gestures[0].t_end - gestures[0].t_start >= 3.9


def test_dwell_then_circle_are_both_found():
    samples = _track([(float(k) * 0.5, 200, 200) for k in range(6)])  # 2.5s dwell
    samples += _circle_track(500, 400, 100, t0=4.0)
    kinds = [g.kind for g in detect_gestures(samples)]
    assert "dwell" in kinds and "circle" in kinds
