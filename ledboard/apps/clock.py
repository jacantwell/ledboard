"""Idle app: dim clock so you can tell the board is alive."""

import time

from ledboard.canvas import Canvas


class ClockApp:
    name = "clock"
    priority = 0

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def wants_display(self, now: float) -> bool:
        return True

    def render(self, canvas: Canvas, now: float) -> None:
        canvas.clear()
        t = time.localtime(now)
        colon = ":" if int(now) % 2 == 0 else " "
        hhmm = f"{t.tm_hour:02d}{colon}{t.tm_min:02d}"
        canvas.text_centered(hhmm, color=(90, 50, 0), font="7x13")
