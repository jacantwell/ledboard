"""Etch-a-sketch background. Knob moves draw a persistent line; shake clears it.

The lowest thing above the clock: text (50) and bus (20) overwrite it whenever
they want the screen, then the sketch comes back. The buffer lives here, not on
the shared Canvas, so preemption never wipes it.
"""

import base64
import threading

import numpy as np

from ledboard.canvas import Canvas, Color, parse_color

# Clamp a single move so one request can't scribble across the whole board.
MAX_STEP = 32


class EtchApp:
    name = "etch"
    priority = 10  # above the clock (0), below bus (20) and text (50)

    def __init__(
        self,
        width: int,
        height: int,
        color: str | Color = "#FFFFFF",
    ) -> None:
        self.width = width
        self.height = height
        self.color = parse_color(color)
        self._lock = threading.Lock()
        self._lit = np.zeros((height, width), dtype=bool)
        self._x = width // 2
        self._y = height // 2
        self._lit[self._y, self._x] = True

    # -- input ---------------------------------------------------------------

    @property
    def cursor(self) -> tuple[int, int]:
        with self._lock:
            return self._x, self._y

    @property
    def lit_count(self) -> int:
        with self._lock:
            return int(self._lit.sum())

    def move(self, dx: int, dy: int) -> tuple[int, int]:
        """Step the stylus, drawing through every pixel on the way. Clamped."""
        dx = max(-MAX_STEP, min(MAX_STEP, int(dx)))
        dy = max(-MAX_STEP, min(MAX_STEP, int(dy)))
        with self._lock:
            nx = max(0, min(self.width - 1, self._x + dx))
            ny = max(0, min(self.height - 1, self._y + dy))
            steps = max(abs(nx - self._x), abs(ny - self._y))
            if steps:
                xs = np.linspace(self._x, nx, steps + 1).round().astype(int)
                ys = np.linspace(self._y, ny, steps + 1).round().astype(int)
                self._lit[ys, xs] = True
                self._x, self._y = nx, ny
            return self._x, self._y

    def clear(self) -> tuple[int, int]:
        """Shake: wipe the screen, stylus stays where it was."""
        with self._lock:
            self._lit[:] = False
            self._lit[self._y, self._x] = True
            return self._x, self._y

    def snapshot(self) -> bytes:
        """Packed-bits copy of the buffer for GET /etch."""
        with self._lock:
            return np.packbits(self._lit).tobytes()

    def state(self) -> dict:
        x, y = self.cursor
        return {
            "w": self.width,
            "h": self.height,
            "x": x,
            "y": y,
            "lit": self.lit_count,
            "pixels_b64": base64.b64encode(self.snapshot()).decode("ascii"),
        }

    # -- App protocol --------------------------------------------------------

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def wants_display(self, now: float) -> bool:
        return True

    def render(self, canvas: Canvas, now: float) -> None:
        canvas.clear()
        with self._lock:
            ys, xs = np.where(self._lit)
            color = self.color
        # vectorised paint, clipped by construction
        canvas.fb[ys, xs] = color
