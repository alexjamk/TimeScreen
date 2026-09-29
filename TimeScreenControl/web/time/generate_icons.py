"""Generate deterministic PNG icons matching icon.svg for PWA manifests."""

from pathlib import Path

from PIL import Image, ImageDraw


ROOT = Path(__file__).parent


def create_icon(size: int, *, maskable: bool = False) -> Image.Image:
    scale = size / 512
    image = Image.new("RGB", (size, size), "#172554")
    draw = ImageDraw.Draw(image)
    if not maskable:
        radius = round(112 * scale)
        # The canvas is already navy; rounding is represented by transparent
        # corners in the regular icon and a full-bleed canvas in maskable form.
        alpha = Image.new("L", (size, size), 0)
        ImageDraw.Draw(alpha).rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
        image.putalpha(alpha)
    width = max(1, round(42 * scale))
    draw = ImageDraw.Draw(image)
    draw.ellipse((102 * scale, 102 * scale, 410 * scale, 410 * scale), outline="#60a5fa", width=width)
    hand_width = max(1, round(40 * scale))
    draw.line((256 * scale, 144 * scale, 256 * scale, 270 * scale, 344 * scale, 322 * scale), fill="white", width=hand_width, joint="curve")
    return image


create_icon(192).save(ROOT / "icon-192.png", optimize=True)
create_icon(512).save(ROOT / "icon-512.png", optimize=True)
create_icon(512, maskable=True).save(ROOT / "icon-maskable-512.png", optimize=True)
