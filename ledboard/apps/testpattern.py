"""Solid colours, a gradient, then a frame with a diagonal. Proves wiring and geometry."""

import numpy as np

from ledboard.canvas import Canvas

STEPS: list[tuple[str, float]] = [
    ("red", 1.5),
    ("green", 1.5),
    ("blue", 1.5),
    ("white", 1.5),
    ("gradient", 3.0),
    ("frame", 4.0),
]
TOTAL = sum(d for _, d in STEPS)


class TestPatternApp:
    name = "testpattern"
    priority = 90

    def __init__(self, width: int, height: int, loop: bool = False) -> None:
        self.width = width
        self.height = height
        self.loop = loop
        self._started: float | None = None

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def wants_display(self, now: float) -> bool:
        if self._started is None:
            return True
        return self.loop or (now - self._started) < TOTAL

    def step_at(self, elapsed: float) -> str:
        if self.loop:
            elapsed %= TOTAL
        t = 0.0
        for name, dur in STEPS:
            t += dur
            if elapsed < t:
                return name
        return STEPS[-1][0]

    def render(self, canvas: Canvas, now: float) -> None:
        if self._started is None:
            self._started = now
        step = self.step_at(now - self._started)
        fb = canvas.fb
        match step:
            case "red":
                fb[:] = (255, 0, 0)
            case "green":
                fb[:] = (0, 255, 0)
            case "blue":
                fb[:] = (0, 0, 255)
            case "white":
                fb[:] = (255, 255, 255)
            case "gradient":
                x = np.linspace(0, 255, self.width, dtype=np.uint8)
                y = np.linspace(0, 255, self.height, dtype=np.uint8)
                fb[..., 0] = x[None, :]
                fb[..., 1] = y[:, None]
                fb[..., 2] = 128
            case "frame":
                canvas.clear()
                fb[0, :] = (255, 0, 0)
                fb[-1, :] = (0, 255, 0)
                fb[:, 0] = (0, 0, 255)
                fb[:, -1] = (255, 255, 0)
                for i in range(min(self.width, self.height)):
                    fb[i, i] = (255, 255, 255)
