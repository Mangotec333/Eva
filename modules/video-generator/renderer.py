"""
EVA Video Generator — scene visual renderer (Pillow only, fully offline).

Renders each storyboard scene to a branded 1080x1920 vertical slide, reusing
postcards' card aesthetic (soft profile header, rounded card, DejaVu fonts +
text-wrap/measurement helpers) and media-editor's lower-third branding
("Eva-acquisition" left, "eva-acquisition.mangotec.ai" right in teal 0x2dd4a7).

The renderer sits behind the ``SceneVisualRenderer`` Protocol, mirroring the
Speaker Protocol pattern in ``services/tts``:

  * ``PillowSceneRenderer`` — the real implementation, Pillow only, no paid API.
  * ``StubSceneRenderer``   — a deterministic blank PNG for offline tests.

A paid text-to-image / AI-video API could later be wired behind this same
Protocol without touching callers.
"""

from __future__ import annotations

import os
from typing import Optional, Protocol, runtime_checkable

from PIL import Image, ImageDraw, ImageFont

# Vertical marketing-video canvas.
W, H = 1080, 1920

# postcards-derived palette + media-editor teal accent.
BG_TOP = (24, 26, 32)        # near-black gradient top
BG_BOTTOM = (44, 40, 52)     # deep plum gradient bottom
CARD = (252, 244, 246)       # postcards soft card
TEXT = (40, 38, 45)          # charcoal body
NAME = (20, 20, 25)
SUB = (110, 105, 115)
TEAL = (45, 212, 167)        # 0x2dd4a7 — media-editor lower-third accent
WHITE = (255, 255, 255)

_ASSETS = os.path.join(os.path.dirname(__file__), "assets")
F_BOLD = os.environ.get("FONT_BOLD", os.path.join(_ASSETS, "DejaVuSans-Bold.ttf"))
F_REG = os.environ.get("FONT_REG", os.path.join(_ASSETS, "DejaVuSans.ttf"))

# Dummy draw surface used only for text measurement (postcards pattern).
_MEASURE = ImageDraw.Draw(Image.new("RGB", (1, 1)))


@runtime_checkable
class SceneVisualRenderer(Protocol):
    """Render one scene's text to an image file. Returns the image path."""

    def render(self, text: str, index: int, style: Optional[dict] = None) -> str:
        ...


def font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(F_BOLD if bold else F_REG, size)


def _wrap(text: str, f: ImageFont.FreeTypeFont, max_w: int) -> list[str]:
    """Greedy word-wrap using Pillow text measurement (ported from postcards)."""
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


def _vertical_gradient(top: tuple, bottom: tuple) -> Image.Image:
    base = Image.new("RGB", (W, H), top)
    d = ImageDraw.Draw(base)
    for y in range(H):
        t = y / max(H - 1, 1)
        d.line(
            [(0, y), (W, y)],
            fill=(
                int(top[0] + (bottom[0] - top[0]) * t),
                int(top[1] + (bottom[1] - top[1]) * t),
                int(top[2] + (bottom[2] - top[2]) * t),
            ),
        )
    return base


def _draw_lower_third(d: ImageDraw.ImageDraw, style: dict) -> None:
    """media-editor branded lower-third: black bar + left/teal-right captions."""
    bar_h = 96
    d.rectangle([0, H - bar_h, W, H], fill=(0, 0, 0))
    left = style.get("caption_left", "Eva-acquisition")
    right = style.get("caption_right", "eva-acquisition.mangotec.ai")
    f_left = font(40, bold=True)
    f_right = font(34, bold=False)
    d.text((40, H - bar_h + 26), left, font=f_left, fill=WHITE)
    rw = _MEASURE.textlength(right, font=f_right)
    d.text((W - rw - 40, H - bar_h + 30), right, font=f_right, fill=TEAL)


def _draw_scene_card(d: ImageDraw.ImageDraw, text: str, index: int) -> None:
    # Rounded content card (postcards aesthetic), centered in the vertical frame.
    margin = 72
    card_top, card_bottom = 300, H - 300
    d.rounded_rectangle(
        [margin, card_top, W - margin, card_bottom], radius=48, fill=CARD
    )

    # Scene index chip in teal.
    chip = f"SCENE {index + 1}"
    f_chip = font(34, bold=True)
    d.rounded_rectangle(
        [margin + 48, card_top + 48, margin + 48 + 200, card_top + 48 + 56],
        radius=18, fill=TEAL,
    )
    d.text((margin + 48 + 24, card_top + 48 + 10), chip, font=f_chip, fill=(10, 20, 18))

    # Scene text — wrapped, sized down to fit the card height if long.
    max_w = W - 2 * margin - 96
    for size in (72, 64, 56, 48, 40, 34, 28):
        f_body = font(size, bold=True)
        lines = _wrap(text, f_body, max_w)
        line_h = int(size * 1.35)
        block_h = len(lines) * line_h
        if card_top + 180 + block_h <= card_bottom - 60:
            break
    y = card_top + 180
    for line in lines:
        d.text((margin + 48, y), line, font=f_body, fill=TEXT)
        y += line_h


class PillowSceneRenderer:
    """Real renderer — a branded vertical slide per scene, Pillow only."""

    name = "pillow"

    def __init__(self, out_dir: str, style: Optional[dict] = None) -> None:
        self.out_dir = out_dir
        self.style = style or {}
        os.makedirs(self.out_dir, exist_ok=True)

    def render(self, text: str, index: int, style: Optional[dict] = None) -> str:
        merged = {**self.style, **(style or {})}
        img = _vertical_gradient(BG_TOP, BG_BOTTOM)
        d = ImageDraw.Draw(img)
        _draw_scene_card(d, text.strip() or f"Scene {index + 1}", index)
        _draw_lower_third(d, merged)
        out_path = os.path.join(self.out_dir, f"scene_{index:03d}.png")
        img.save(out_path, "PNG")
        return out_path


class StubSceneRenderer:
    """Offline test renderer — a deterministic solid-colour PNG, no fonts."""

    name = "stub"

    def __init__(self, out_dir: str, style: Optional[dict] = None) -> None:
        self.out_dir = out_dir
        self.style = style or {}
        os.makedirs(self.out_dir, exist_ok=True)

    def render(self, text: str, index: int, style: Optional[dict] = None) -> str:
        # Deterministic: colour is a pure function of the scene index.
        shade = (30 + (index * 20) % 180, 40, 60)
        img = Image.new("RGB", (W, H), shade)
        out_path = os.path.join(self.out_dir, f"scene_{index:03d}.png")
        img.save(out_path, "PNG")
        return out_path


def build_renderer(out_dir: str, stub: bool = False,
                   style: Optional[dict] = None) -> SceneVisualRenderer:
    if stub:
        return StubSceneRenderer(out_dir, style)
    return PillowSceneRenderer(out_dir, style)


__all__ = [
    "SceneVisualRenderer",
    "PillowSceneRenderer",
    "StubSceneRenderer",
    "build_renderer",
    "W",
    "H",
]
