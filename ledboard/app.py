from typing import Protocol

from ledboard.canvas import Canvas


class App(Protocol):
    """Something that can draw on the board. Highest priority that wants the screen wins."""

    name: str
    priority: int

    def start(self) -> None: ...

    def stop(self) -> None: ...

    def wants_display(self, now: float) -> bool: ...

    def render(self, canvas: Canvas, now: float) -> None: ...
