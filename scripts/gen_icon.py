#!/usr/bin/env python3
"""Generate LanCaster app icons from scratch using Pillow.

Output:
  assets/icon-512.png   (512x512 master)
  assets/icon-256.png
  assets/icon-128.png
  assets/icon-64.png
  assets/icon-32.png
  assets/icon-16.png
  assets/icon.ico       (Windows, multi-size)
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SIZES = [512, 256, 128, 64, 32, 16]
OUT_DIR = Path(__file__).resolve().parent.parent / "assets"

PRIMARY = (108, 92, 231)
PRIMARY_DARK = (80, 66, 190)
WHITE = (255, 255, 255)
BG_GRADIENT_TOP = (108, 92, 231)
BG_GRADIENT_BOT = (78, 62, 190)


def _draw_rounded_rect(draw, bbox, radius, fill):
    draw.rounded_rectangle(bbox, radius=radius, fill=fill)


def _render_icon(size: int) -> Image.Image:
    """Render a single icon at the given size."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    pad = max(1, size // 32)
    corner_r = max(4, size // 4)

    for y in range(pad, size - pad):
        frac = (y - pad) / max(1, (size - 2 * pad))
        r = int(BG_GRADIENT_TOP[0] + (BG_GRADIENT_BOT[0] - BG_GRADIENT_TOP[0]) * frac)
        g = int(BG_GRADIENT_TOP[1] + (BG_GRADIENT_BOT[1] - BG_GRADIENT_TOP[1]) * frac)
        b = int(BG_GRADIENT_TOP[2] + (BG_GRADIENT_BOT[2] - BG_GRADIENT_TOP[2]) * frac)
        draw.line([(pad, y), (size - pad - 1, y)], fill=(r, g, b, 255))

    _draw_rounded_rect(draw, [pad, pad, size - pad, size - pad], corner_r, None)

    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.rounded_rectangle([pad, pad, size - pad, size - pad], radius=corner_r, fill=255)

    bg = img.copy()
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    img.paste(bg, mask=mask)
    draw = ImageDraw.Draw(img)

    font_size = int(size * 0.45)
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", font_size)
    except (OSError, IOError):
        try:
            font = ImageFont.truetype("Arial Bold", font_size)
        except (OSError, IOError):
            font = ImageFont.load_default()

    text = "L"
    bbox_text = draw.textbbox((0, 0), text, font=font)
    tw = bbox_text[2] - bbox_text[0]
    th = bbox_text[3] - bbox_text[1]
    tx = (size - tw) // 2
    ty = (size - th) // 2 - int(size * 0.04)
    draw.text((tx, ty), text, fill=WHITE, font=font)

    if size >= 64:
        cx = size * 0.7
        cy = size * 0.35
        for i in range(3):
            r_inner = int(size * (0.08 + i * 0.06))
            r_outer = r_inner + max(2, size // 60)
            arc_bbox = [cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer]
            alpha = 255 - i * 60
            draw.arc(arc_bbox, start=-60, end=60, fill=(*WHITE, alpha), width=max(1, size // 80))

    return img


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    images = {}
    for s in SIZES:
        img = _render_icon(s)
        out = OUT_DIR / f"icon-{s}.png"
        img.save(out, "PNG")
        images[s] = img
        print(f"  -> {out}")

    ico_sizes = [s for s in [256, 128, 64, 48, 32, 16] if s in images]
    ico_images = []
    for s in ico_sizes:
        if s in images:
            ico_images.append(images[s])
        else:
            ico_images.append(images[512].resize((s, s), Image.LANCZOS))

    if 48 not in images:
        ico_images.insert(2, images[64].resize((48, 48), Image.LANCZOS))

    ico_path = OUT_DIR / "icon.ico"
    ico_images[0].save(ico_path, format="ICO", sizes=[(im.width, im.height) for im in ico_images])
    print(f"  -> {ico_path}")
    print("Done!")


if __name__ == "__main__":
    main()
