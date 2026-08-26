"""Make near-black IRIS icon background transparent; rewrite png + multi-size ico."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "iris" / "assets"
PNG_PATH = ASSETS / "iris_icon.png"
ICO_PATH = ASSETS / "iris_icon.ico"


def _matte(im: Image.Image) -> Image.Image:
    """Soft-cut pure black bg; keep cyan glow."""
    rgba = im.convert("RGBA")
    px = rgba.load()
    w, h = rgba.size
    for y in range(h):
        for x in range(w):
            r, g, b, _a = px[x, y]
            vmax = max(r, g, b)
            if vmax <= 6:
                alpha = 0
            elif vmax < 36:
                alpha = int(255 * (vmax - 6) / 30)
            else:
                alpha = 255
            if alpha == 0:
                px[x, y] = (0, 0, 0, 0)
            elif alpha < 255:
                px[x, y] = (
                    r * alpha // 255,
                    g * alpha // 255,
                    b * alpha // 255,
                    alpha,
                )
            else:
                px[x, y] = (r, g, b, 255)
    return rgba


def _square_crop(im: Image.Image, pad: int = 24) -> Image.Image:
    bbox = im.getchannel("A").getbbox()
    if not bbox:
        return im
    x0, y0, x1, y1 = bbox
    x0 = max(0, x0 - pad)
    y0 = max(0, y0 - pad)
    x1 = min(im.width, x1 + pad)
    y1 = min(im.height, y1 + pad)
    side = max(x1 - x0, y1 - y0)
    cx = (x0 + x1) // 2
    cy = (y0 + y1) // 2
    x0 = max(0, cx - side // 2)
    y0 = max(0, cy - side // 2)
    x1 = min(im.width, x0 + side)
    y1 = min(im.height, y0 + side)
    return im.crop((x0, y0, x1, y1))


def main() -> None:
    matted = _square_crop(_matte(Image.open(PNG_PATH)))
    master = matted.resize((1024, 1024), Image.Resampling.LANCZOS)
    master.save(PNG_PATH, optimize=True)

    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    master.save(ICO_PATH, format="ICO", sizes=sizes)

    a = master.getchannel("A")
    zero = sum(1 for p in a.get_flattened_data() if p == 0)
    print("png", master.size, "alpha", a.getextrema(), "transparent", zero)
    print("corner", master.getpixel((0, 0)), "center", master.getpixel((512, 512)))
    print("ico", ICO_PATH, ICO_PATH.stat().st_size)


if __name__ == "__main__":
    main()
