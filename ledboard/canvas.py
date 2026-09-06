"""Drawing helpers over a (H, W, 3) uint8 framebuffer. Apps draw here, never on hardware."""

from functools import lru_cache

import numpy as np
from PIL import Image, ImageDraw

from ledboard import fonts

Color = tuple[int, int, int]

AMBER: Color = (255, 140, 0)
WHITE: Color = (255, 255, 255)
BLACK: Color = (0, 0, 0)


def parse_color(s: str | Color | None, default: Color = AMBER) -> Color:
    if s is None:
        return default
    if isinstance(s, tuple):
        return s
    h = s.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    if len(h) != 6:
        raise ValueError(f"bad colour {s!r}")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


@lru_cache(maxsize=256)
def text_mask(text: str, font: str = fonts.DEFAULT) -> np.ndarray:
    """Boolean (h, w) mask of rendered text. Cached so scrolling is cheap."""
    f = fonts.load(font)
    _, fh = fonts.size(font)
    w = text_width(text, font)
    img = Image.new("L", (max(w, 1), fh), 0)
    ImageDraw.Draw(img).text((0, 0), text, font=f, fill=255)
    return np.asarray(img) > 0


def text_width(text: str, font: str = fonts.DEFAULT) -> int:
    if not text:
        return 0
    left, _, right, _ = fonts.load(font).getbbox(text)
    return int(right - left)


class Canvas:
    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.fb = np.zeros((height, width, 3), dtype=np.uint8)

    def clear(self, color: Color = BLACK) -> None:
        self.fb[:] = color

    def pixel(self, x: int, y: int, color: Color) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            self.fb[y, x] = color

    def rect(self, x: int, y: int, w: int, h: int, color: Color) -> None:
        x0, y0 = max(x, 0), max(y, 0)
        x1, y1 = min(x + w, self.width), min(y + h, self.height)
        if x1 > x0 and y1 > y0:
            self.fb[y0:y1, x0:x1] = color

    def blit_mask(self, mask: np.ndarray, x: int, y: int, color: Color) -> None:
        """Paint `color` wherever mask is true, clipped to the canvas. x/y may be negative."""
        mh, mw = mask.shape
        x0, y0 = max(x, 0), max(y, 0)
        x1, y1 = min(x + mw, self.width), min(y + mh, self.height)
        if x1 <= x0 or y1 <= y0:
            return
        sub = mask[y0 - y : y1 - y, x0 - x : x1 - x]
        self.fb[y0:y1, x0:x1][sub] = color

    def text(self, x: int, y: int, s: str, color: Color = AMBER, font: str = fonts.DEFAULT) -> int:
        """Draw text with its top-left at (x, y). Returns the text's pixel width."""
        if not s:
            return 0
        mask = text_mask(s, font)
        self.blit_mask(mask, x, y, color)
        return mask.shape[1]

    def text_centered(self, s: str, color: Color = AMBER, font: str = fonts.DEFAULT) -> None:
        w = text_width(s, font)
        _, fh = fonts.size(font)
        self.text((self.width - w) // 2, (self.height - fh) // 2, s, color, font)
