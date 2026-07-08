"""
EVA Postcards — quote-card renderer (Adam Grant style, fully offline).

Ported directly from the proven ``render_cards.py`` prototype: a 1200x1200 PNG
with a soft-pink rounded card, a profile header ("VR" avatar + "Vineet Ravi" +
blue verified badge + "@vineetRavi" handle), and the two-paragraph reframe body.

Uses only Pillow + the DejaVu fonts shipped with the system, so it runs with no
network access.
"""

from __future__ import annotations

from PIL import Image, ImageDraw, ImageFont

# Dummy draw surface used only for text measurement in wrap().
_MEASURE = ImageDraw.Draw(Image.new("RGB", (1, 1)))

W, H = 1200, 1200
BG = (244, 219, 224)        # soft pink #F4DBE0
TEXT = (40, 38, 45)         # near-black charcoal
NAME = (20, 20, 25)
SUB = (110, 105, 115)       # handle grey
ACCENT = (29, 155, 240)     # verified blue
CARD = (252, 244, 246)
RADIUS = 36

F_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
F_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(F_BOLD if bold else F_REG, size)


def _rounded_card(bg, radius: int) -> Image.Image:
    base = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(base)
    d.rounded_rectangle([0, 0, W - 1, H - 1], radius=radius, fill=bg)
    return base


def _draw_header(d: ImageDraw.ImageDraw) -> None:
    # avatar circle with initials "VR"
    cx, cy, r = 96, 96, 52
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(120, 90, 130))
    f_initial = font(40)
    bbox = d.textbbox((0, 0), "VR", font=f_initial)
    d.text(
        (cx - (bbox[2] - bbox[0]) / 2, cy - (bbox[3] - bbox[1]) / 2 - 2),
        "VR",
        font=f_initial,
        fill=(255, 255, 255),
    )
    # name
    f_name = font(38)
    d.text((cx + r + 24, 56), "Vineet Ravi", font=f_name, fill=NAME)
    # verified badge (blue circle with check)
    nb = d.textbbox((0, 0), "Vineet Ravi", font=f_name)
    bx = cx + r + 24 + (nb[2] - nb[0]) + 14
    by = 56 + 6
    d.ellipse([bx, by, bx + 30, by + 30], fill=ACCENT)
    d.text((bx + 8, by + 4), "✓", font=font(22), fill=(255, 255, 255))
    # handle
    f_handle = font(28, bold=False)
    d.text((cx + r + 24, 104), "@vineetRavi", font=f_handle, fill=SUB)


def _wrap(text: str, f: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    words = text.split()
    lines, cur = [], ""
    for w in words:
        test = (cur + " " + w).strip()
        if _MEASURE.textlength(test, font=f) <= max_w:
            cur = test
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def render_card(para1: str, para2: str, out_path: str) -> str:
    """Render a two-paragraph quote card to ``out_path`` and return that path."""
    img = _rounded_card(CARD, RADIUS).copy()
    d = ImageDraw.Draw(img)
    _draw_header(d)

    max_w = W - 160
    y = 230
    f_body = font(40)
    for para, first in [(para1, True), (para2, False)]:
        if not first:
            y += 34
        for line in _wrap(para, f_body, max_w):
            d.text((80, y), line, font=f_body, fill=TEXT)
            y += 56
    img.save(out_path, "PNG")
    return out_path
