"""Figure rendering: pointer rings, region highlights, and cursor-trail
overlays.

Coordinate spaces: cursor/gesture data lives in global (logical) screen
coordinates; figures are drawn in frame pixels. Each frame event records its
monitor rectangle, so:

    scale   = image_width / monitor_logical_width
    frame_x = (global_x - monitor_left) * scale

The understanding stage works in a third space — the downscaled image the
model was shown — handled via `image_space_width`.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

RING_COLOR = (255, 59, 48)
HALO_COLOR = (255, 255, 255)
TRAIL_COLOR = (255, 0, 190)
CROP_BOX = (1280, 820)


def ring_radius(image_width: int) -> int:
    return max(22, round(image_width * 0.024))


def map_to_frame(frame_ev: dict, image_width: int, x: float, y: float) -> tuple[float, float]:
    """Global screen coordinates -> frame pixel coordinates."""
    mon = frame_ev.get("mon") or {}
    scale = image_width / (mon.get("width") or image_width)
    return ((x - mon.get("left", 0)) * scale, (y - mon.get("top", 0)) * scale)


def annotate_frame(frame_file: Path, frame_ev: dict, out_path: Path, *,
                   point: tuple[float, float] | None = None,
                   region: tuple[float, float, float, float] | None = None,
                   image_space_width: int | None = None,
                   crop: str = "none", quality: int = 90) -> tuple[float, float]:
    """Draw a point ring or a region highlight; return its centre in figure px.

    `point`/`region` are global screen coordinates by default; pass
    `image_space_width` when they are pixels in a downscaled copy of this frame
    (e.g. coordinates chosen by the model).
    """
    img = Image.open(frame_file).convert("RGB")

    def to_px(x: float, y: float) -> tuple[float, float]:
        if image_space_width:
            s = img.width / image_space_width
            return (x * s, y * s)
        return map_to_frame(frame_ev, img.width, x, y)

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    def ellipse(bbox: list[float], color: tuple, width: int) -> None:
        draw.ellipse(bbox, outline=color, width=width)

    if region is not None:
        x0, y0 = to_px(region[0], region[1])
        x1, y1 = to_px(region[0] + region[2], region[1] + region[3])
        x0 = max(x0, 2.0); y0 = max(y0, 2.0)
        x1 = min(max(x1, x0 + 24), img.width - 2.0)
        y1 = min(max(y1, y0 + 24), img.height - 2.0)
        # an ellipse enclosing the box reads as a hand-drawn circle around it
        pad_x, pad_y = 0.21 * (x1 - x0), 0.21 * (y1 - y0)
        bbox = [x0 - pad_x, y0 - pad_y, x1 + pad_x, y1 + pad_y]
        stroke = max(4, round(img.width * 0.004))
        ellipse([bbox[0] - 6, bbox[1] - 6, bbox[2] + 6, bbox[3] + 6], (*HALO_COLOR, 235), stroke + 3)
        ellipse(bbox, (*RING_COLOR, 255), stroke)
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
    else:
        cx, cy = to_px(*point)
        cx = min(max(cx, 0.0), img.width - 1.0)
        cy = min(max(cy, 0.0), img.height - 1.0)
        r = ring_radius(img.width)
        ellipse([cx - r - 14, cy - r - 14, cx + r + 14, cy + r + 14], (*RING_COLOR, 70), max(2, r // 8))
        ellipse([cx - r - 6, cy - r - 6, cx + r + 6, cy + r + 6], (*HALO_COLOR, 235), max(3, r // 5))
        ellipse([cx - r, cy - r, cx + r, cy + r], (*RING_COLOR, 255), max(4, r // 6))

    img = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")

    if crop == "region":
        box_w = min(img.width, CROP_BOX[0])
        box_h = min(img.height, CROP_BOX[1])
        left = int(min(max(cx - box_w / 2, 0), img.width - box_w))
        top = int(min(max(cy - box_h / 2, 0), img.height - box_h))
        img = img.crop((left, top, left + box_w, top + box_h))
        cx, cy = cx - left, cy - top

    img.save(out_path, "JPEG", quality=quality)
    return (cx, cy)


def render_trail_frame(frame_file: Path, frame_ev: dict, cursor_samples: list[dict],
                       t: float, *, width: int = 1024,
                       window: tuple[float, float] = (2.5, 1.0)) -> Image.Image:
    """A downscaled copy of the frame with the recent cursor path overlaid —
    how a still-image model gets to *see* pointing and circling gestures.

    The trail fades in over `window` = (seconds before, seconds after) t and
    ends in a dot at the cursor's position at t.
    """
    img = Image.open(frame_file).convert("RGB")
    if img.width > width:
        img = img.resize((width, round(img.height * width / img.width)), Image.LANCZOS)

    pts = [
        (s["t"], map_to_frame(frame_ev, img.width, s["x"], s["y"]))
        for s in cursor_samples
        if t - window[0] <= s["t"] <= t + window[1]
    ]
    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    if len(pts) >= 2:
        n = len(pts) - 1
        for k, ((_, a), (_, b)) in enumerate(zip(pts, pts[1:])):
            alpha = 70 + round(185 * k / n)
            draw.line([a, b], fill=(*HALO_COLOR, alpha), width=5)
            draw.line([a, b], fill=(*TRAIL_COLOR, alpha), width=3)
    if pts:
        _, (dx, dy) = min(pts, key=lambda p: abs(p[0] - t))
        draw.ellipse([dx - 9, dy - 9, dx + 9, dy + 9], outline=(*HALO_COLOR, 255), width=3)
        draw.ellipse([dx - 6, dy - 6, dx + 6, dy + 6], fill=(*TRAIL_COLOR, 255))

    return Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
