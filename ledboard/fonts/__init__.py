"""X11 misc-fixed bitmap fonts (public domain), compiled from BDF on first use."""

import tempfile
from functools import lru_cache
from pathlib import Path

from PIL import BdfFontFile, ImageFont

FONT_DIR = Path(__file__).parent
NAMES = ("4x6", "5x7", "6x10", "7x13")
DEFAULT = "6x10"


def size(name: str) -> tuple[int, int]:
    w, h = name.split("x")
    return int(w), int(h)


@lru_cache
def load(name: str = DEFAULT) -> ImageFont.ImageFont:
    if name not in NAMES:
        raise ValueError(f"unknown font {name!r}, pick one of {NAMES}")
    cache = Path(tempfile.gettempdir()) / "ledboard-fonts"
    cache.mkdir(exist_ok=True)
    pil = cache / f"{name}.pil"
    if not pil.exists():
        with open(FONT_DIR / f"{name}.bdf", "rb") as fp:
            BdfFontFile.BdfFontFile(fp).save(str(cache / name))
    return ImageFont.load(str(pil))
