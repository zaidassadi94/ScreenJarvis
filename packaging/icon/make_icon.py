"""Draw the ScreenJarvis app icon and emit a macOS .iconset.

Programmatic so the icon lives in source, not a binary blob: a rounded-square
gradient tile (the app's colour), a white microphone (voice), and a cursor arrow
(the screen it can see). Rendered at 4x and downscaled for clean edges.

    python packaging/icon/make_icon.py
    iconutil -c icns packaging/icon/ScreenJarvis.iconset -o packaging/icon/ScreenJarvis.icns  # macOS

The .icns is a build artifact (see scripts/build_app.sh); the .iconset PNGs and
this script are the source of truth.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
BASE = 1024
SS = 4  # supersample factor

TOP = (108, 92, 231)     # indigo
BOTTOM = (72, 52, 212)   # deeper violet
WHITE = (255, 255, 255)


def _rounded_mask(size: int, radius: int) -> Image.Image:
    m = Image.new("L", (size, size), 0)
    ImageDraw.Draw(m).rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def _gradient(size: int) -> Image.Image:
    g = Image.new("RGB", (1, size))
    for y in range(size):
        t = y / (size - 1)
        g.putpixel((0, y), tuple(round(TOP[i] + (BOTTOM[i] - TOP[i]) * t) for i in range(3)))
    return g.resize((size, size))


def render(size: int) -> Image.Image:
    s = size * SS
    tile = _gradient(s)
    tile.putalpha(_rounded_mask(s, radius=int(s * 0.225)))  # macOS "squircle"-ish

    d = ImageDraw.Draw(tile)
    cx = s // 2

    # microphone: capsule body, a U-shaped cradle, stand, and base
    body_w, body_h = s * 0.24, s * 0.40
    body_top = s * 0.20
    d.rounded_rectangle(
        [cx - body_w / 2, body_top, cx + body_w / 2, body_top + body_h],
        radius=body_w / 2, fill=WHITE,
    )
    cradle_r = body_w * 0.92
    cradle_cy = body_top + body_h * 0.62
    lw = int(s * 0.028)
    d.arc([cx - cradle_r, cradle_cy - cradle_r, cx + cradle_r, cradle_cy + cradle_r],
          start=20, end=160, fill=WHITE, width=lw)
    stand_top = cradle_cy + cradle_r
    stand_bot = s * 0.78
    d.line([cx, stand_top, cx, stand_bot], fill=WHITE, width=lw)
    base_w = s * 0.18
    d.line([cx - base_w / 2, stand_bot, cx + base_w / 2, stand_bot], fill=WHITE, width=lw)

    # cursor arrow, lower-right — the "screen it can see"
    ax, ay = s * 0.66, s * 0.60
    k = s * 0.16
    arrow = [(ax, ay), (ax, ay + k * 1.32), (ax + k * 0.34, ay + k * 0.98),
             (ax + k * 0.56, ay + k * 1.5), (ax + k * 0.76, ay + k * 1.4),
             (ax + k * 0.54, ay + k * 0.9), (ax + k * 0.96, ay + k * 0.86)]
    d.polygon(arrow, fill=WHITE)
    d.line(arrow + [arrow[0]], fill=BOTTOM, width=int(s * 0.012), joint="curve")

    return tile.resize((size, size), Image.LANCZOS)


def main() -> None:
    iconset = HERE / "ScreenJarvis.iconset"
    iconset.mkdir(exist_ok=True)
    master = render(BASE)
    master.save(HERE / "icon-1024.png")
    # the exact filenames `iconutil` expects
    for px, name in [
        (16, "icon_16x16.png"), (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"), (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"), (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"), (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"), (1024, "icon_512x512@2x.png"),
    ]:
        master.resize((px, px), Image.LANCZOS).save(iconset / name)
    print(f"wrote {iconset} and icon-1024.png")


if __name__ == "__main__":
    main()
