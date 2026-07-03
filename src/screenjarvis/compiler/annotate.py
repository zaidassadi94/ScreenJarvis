"""Figure rendering: draw a pointer ring on the chosen frame, optionally crop."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

RING_COLOR = (255, 59, 48)
HALO_COLOR = (255, 255, 255)
CROP_BOX = (1280, 820)


def ring_radius(image_width: int) -> int:
    return max(22, round(image_width * 0.024))


def annotate_frame(frame_file: Path, frame_ev: dict, cursor: tuple[int, int], out_path: Path,
                   *, crop: str = "none", quality: int = 90) -> tuple[float, float]:
    """Draw the ring where the cursor was; return the ring centre in figure pixels."""
    img = Image.open(frame_file).convert("RGB")
    mon = frame_ev.get("mon") or {}
    mon_w = mon.get("width") or img.width
    scale = img.width / mon_w
    cx = (cursor[0] - mon.get("left", 0)) * scale
    cy = (cursor[1] - mon.get("top", 0)) * scale
    cx = min(max(cx, 0.0), img.width - 1.0)
    cy = min(max(cy, 0.0), img.height - 1.0)
    r = ring_radius(img.width)

    overlay = Image.new("RGBA", img.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    def ellipse(radius: float, color: tuple, width: int) -> None:
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius],
                     outline=color, width=width)

    ellipse(r + 14, (*RING_COLOR, 70), max(2, r // 8))   # faint outer glow
    ellipse(r + 6, (*HALO_COLOR, 235), max(3, r // 5))   # white halo: visible on dark UIs
    ellipse(r, (*RING_COLOR, 255), max(4, r // 6))       # the ring itself
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
