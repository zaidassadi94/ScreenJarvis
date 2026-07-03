"""Gesture detection over the cursor log — pure geometry, no ML.

The 15 Hz cursor track preserves motion at higher fidelity than 2 fps frames
ever could: a circled region is literally a loop of coordinates in
events.jsonl. This module turns the raw track into gesture events for the
understanding stage (and for upgrading heuristic anchors from a point ring to
a region highlight).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

MOVE_EPS = 3.0            # px: below this, a sample is "stationary"
BURST_GAP = 0.4           # s: a larger gap in the log splits movement bursts
MIN_BURST_POINTS = 8
DWELL_MIN_S = 0.6
CIRCLE_MIN_TURN = 300.0   # degrees of accumulated signed rotation
CIRCLE_MIN_SIZE = 30.0    # px: minimum bbox side for a circle
WIGGLE_MIN_TOTAL = 540.0  # degrees of total (unsigned) rotation
WIGGLE_MAX_SIZE = 140.0   # px: a wiggle is emphasis in place, not a tour
REGION_PAD = 16


@dataclass
class Gesture:
    kind: str             # "circle" | "wiggle" | "dwell"
    t_start: float
    t_end: float
    cx: float
    cy: float
    region: tuple[int, int, int, int] | None = None  # x, y, w, h — global px, circles only

    def overlaps(self, t0: float, t1: float) -> bool:
        return self.t_start <= t1 and t0 <= self.t_end


def detect_gestures(samples: list[dict]) -> list[Gesture]:
    if len(samples) < 3:
        return []
    gestures = _dwells(samples)
    for burst in _movement_bursts(samples):
        if g := _classify_burst(burst):
            gestures.append(g)
    gestures.sort(key=lambda g: g.t_start)
    return gestures


def _dist(a: dict, b: dict) -> float:
    return math.hypot(a["x"] - b["x"], a["y"] - b["y"])


def _dwells(samples: list[dict]) -> list[Gesture]:
    out: list[Gesture] = []
    run: list[dict] = [samples[0]]
    for prev, cur in zip(samples, samples[1:]):
        if _dist(prev, cur) < MOVE_EPS:
            run.append(cur)
            continue
        out.extend(_finish_dwell(run))
        run = [cur]
    out.extend(_finish_dwell(run))
    return out


def _finish_dwell(run: list[dict]) -> list[Gesture]:
    if len(run) < 2 or run[-1]["t"] - run[0]["t"] < DWELL_MIN_S:
        return []
    cx = sum(s["x"] for s in run) / len(run)
    cy = sum(s["y"] for s in run) / len(run)
    return [Gesture("dwell", run[0]["t"], run[-1]["t"], cx, cy)]


def _movement_bursts(samples: list[dict]) -> list[list[dict]]:
    bursts: list[list[dict]] = []
    current: list[dict] = []
    for prev, cur in zip(samples, samples[1:]):
        moving = _dist(prev, cur) >= MOVE_EPS and (cur["t"] - prev["t"]) <= BURST_GAP
        if moving:
            if not current:
                current = [prev]
            current.append(cur)
        elif current:
            bursts.append(current)
            current = []
    if current:
        bursts.append(current)
    return [b for b in bursts if len(b) >= MIN_BURST_POINTS]


def _classify_burst(points: list[dict]) -> Gesture | None:
    vecs = []
    for a, b in zip(points, points[1:]):
        dx, dy = b["x"] - a["x"], b["y"] - a["y"]
        if math.hypot(dx, dy) >= 1.0:
            vecs.append((dx, dy))
    if len(vecs) < 3:
        return None

    signed = total = 0.0
    for (ax, ay), (bx, by) in zip(vecs, vecs[1:]):
        angle = math.degrees(math.atan2(ax * by - ay * bx, ax * bx + ay * by))
        signed += angle
        total += abs(angle)

    xs = [p["x"] for p in points]
    ys = [p["y"] for p in points]
    w, h = max(xs) - min(xs), max(ys) - min(ys)
    cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
    t0, t1 = points[0]["t"], points[-1]["t"]

    if abs(signed) >= CIRCLE_MIN_TURN and min(w, h) >= CIRCLE_MIN_SIZE:
        region = (int(min(xs)) - REGION_PAD, int(min(ys)) - REGION_PAD,
                  int(w) + 2 * REGION_PAD, int(h) + 2 * REGION_PAD)
        return Gesture("circle", t0, t1, cx, cy, region=region)
    if total >= WIGGLE_MIN_TOTAL and max(w, h) <= WIGGLE_MAX_SIZE:
        return Gesture("wiggle", t0, t1, cx, cy)
    return None
