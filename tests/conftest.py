"""Shared fixtures and fakes. Nothing here touches the network or real hardware."""

import os

import numpy as np
import pytest

from ledboard.canvas import Canvas, text_width
from ledboard.config import Settings
from ledboard.display.array import ArrayDisplay
from ledboard.display.base import FrameStore

WIDTH = 128
HEIGHT = 32


class FakeApp:
    """Minimal App with a controllable priority and willingness."""

    def __init__(
        self,
        name: str = "fake",
        priority: int = 10,
        wants: bool = True,
        color: tuple[int, int, int] = (10, 20, 30),
        wants_for: int | None = None,
    ) -> None:
        self.name = name
        self.priority = priority
        self.wants = wants
        self.color = color
        # None = follow `wants`; an int = willing until that many renders happened.
        self.wants_for = wants_for
        self.starts = 0
        self.stops = 0
        self.renders = 0
        self.last_now: float | None = None

    def start(self) -> None:
        self.starts += 1

    def stop(self) -> None:
        self.stops += 1

    def wants_display(self, now: float) -> bool:
        if self.wants_for is not None:
            return self.renders < self.wants_for
        return self.wants

    def render(self, canvas: Canvas, now: float) -> None:
        canvas.fb[:] = self.color
        self.renders += 1
        self.last_now = now


def lit(fb: np.ndarray) -> np.ndarray:
    """Boolean (h, w) mask of non-black pixels."""
    return fb.any(axis=2)


def lit_bbox(fb: np.ndarray) -> tuple[int, int, int, int] | None:
    """(x0, y0, x1, y1) half-open box around non-black pixels, or None if blank."""
    m = lit(fb)
    if not m.any():
        return None
    ys, xs = np.where(m)
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def lit_colors(fb: np.ndarray) -> set[tuple[int, int, int]]:
    """Distinct non-black colours present in the frame."""
    pix = fb.reshape(-1, 3)
    pix = pix[pix.any(axis=1)]
    return {tuple(int(c) for c in p) for p in np.unique(pix, axis=0)}


def text_box(width: int, text: str, font: str = "6x10") -> tuple[int, int]:
    """(x0, x1) of the box a centred string is drawn into, ignoring glyph bearings."""
    w = text_width(text, font)
    x0 = (width - w) // 2
    return x0, x0 + w


@pytest.fixture(autouse=True)
def _no_ledboard_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep the developer's own LEDBOARD_* vars out of the tests."""
    for key in list(os.environ):
        if key.startswith("LEDBOARD_"):
            monkeypatch.delenv(key, raising=False)


@pytest.fixture
def canvas() -> Canvas:
    return Canvas(WIDTH, HEIGHT)


@pytest.fixture
def small_canvas() -> Canvas:
    return Canvas(8, 8)


@pytest.fixture
def display() -> ArrayDisplay:
    return ArrayDisplay(WIDTH, HEIGHT)


@pytest.fixture
def store() -> FrameStore:
    return FrameStore(WIDTH, HEIGHT)


@pytest.fixture
def settings(tmp_path) -> Settings:
    """Settings with no env or .env leaking in, and a throwaway png path."""
    return Settings(
        _env_file=None,
        display="array",
        width=WIDTH,
        height=HEIGHT,
        png_path=str(tmp_path / "frame.png"),
    )
