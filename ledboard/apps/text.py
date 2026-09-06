"""Show queued text messages. Short ones sit centred; long ones scroll through once."""

import threading
from collections import deque
from dataclasses import dataclass

from ledboard import fonts
from ledboard.canvas import Canvas, Color, parse_color, text_width


@dataclass(frozen=True)
class Message:
    text: str
    color: Color
    font: str = fonts.DEFAULT


class TextApp:
    name = "text"
    priority = 50

    def __init__(
        self,
        width: int,
        height: int,
        dwell_s: float = 4.0,
        scroll_pps: float = 40.0,
        default_color: str | Color = "#FF8C00",
        font: str = fonts.DEFAULT,
    ) -> None:
        self.width = width
        self.height = height
        self.dwell_s = dwell_s
        self.scroll_pps = scroll_pps
        self.default_color = parse_color(default_color)
        self.font = font
        self._queue: deque[Message] = deque()
        self._lock = threading.Lock()
        self._current: Message | None = None
        self._started: float = 0.0

    # -- input ---------------------------------------------------------------

    def submit(self, text: str, color: str | Color | None = None) -> int:
        """Queue a message. Returns its position (1 = showing next)."""
        msg = Message(text=text, color=parse_color(color, self.default_color), font=self.font)
        with self._lock:
            self._queue.append(msg)
            return len(self._queue)

    def clear(self) -> None:
        with self._lock:
            self._queue.clear()
            self._current = None

    @property
    def pending(self) -> int:
        with self._lock:
            return len(self._queue) + (1 if self._current else 0)

    # -- App protocol --------------------------------------------------------

    def start(self) -> None:
        pass

    def stop(self) -> None:
        self.clear()

    def wants_display(self, now: float) -> bool:
        return self.pending > 0

    def render(self, canvas: Canvas, now: float) -> None:
        with self._lock:
            if self._current is None:
                if not self._queue:
                    canvas.clear()
                    return
                self._current = self._queue.popleft()
                self._started = now
            msg = self._current
            started = self._started

        canvas.clear()
        w = text_width(msg.text, msg.font)
        _, fh = fonts.size(msg.font)
        y = (self.height - fh) // 2
        elapsed = now - started

        if w <= self.width:
            canvas.text((self.width - w) // 2, y, msg.text, msg.color, msg.font)
            done = elapsed >= self.dwell_s
        else:
            x = int(round(self.width - elapsed * self.scroll_pps))
            canvas.text(x, y, msg.text, msg.color, msg.font)
            done = x + w < 0

        if done:
            with self._lock:
                if self._current is msg:
                    self._current = None
