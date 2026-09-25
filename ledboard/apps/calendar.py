"""Next few events on the house calendar. Fetches on its own thread, yields when there are none."""

import logging
import threading
import time
from collections.abc import Callable
from datetime import date, datetime

from ledboard import fonts
from ledboard.canvas import Canvas, Color, parse_color
from ledboard.gcal import Event

log = logging.getLogger(__name__)


class CalendarApp:
    name = "calendar"
    priority = 15  # under bus (20) so departures win in the morning, over etch and the clock

    def __init__(
        self,
        width: int,
        height: int,
        fetch: Callable[[], list[Event]],
        count: int = 2,
        refresh_s: float = 300.0,
        stale_s: float = 3600.0,
        color: str | Color = "#FF8C00",
        font: str = "5x7",
    ) -> None:
        self.width = width
        self.height = height
        self.count = count
        self.refresh_s = refresh_s
        self.stale_s = stale_s
        self.color = parse_color(color)
        self.date_color = tuple(c // 2 for c in self.color)
        self.font = font
        self._fw, self._fh = fonts.size(font)
        self._fetch = fetch
        self._lock = threading.Lock()
        self._events: list[Event] = []
        self._fetched_at: float = 0.0
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None

    # -- polling -------------------------------------------------------------

    def _poll_once(self, now: float | None = None) -> None:
        try:
            events = self._fetch()
        except Exception:
            # A blip must never kill the poll thread; going stale hands over to the clock.
            log.warning("calendar fetch failed", exc_info=True)
            return
        with self._lock:
            self._events = events
            self._fetched_at = time.time() if now is None else now

    def _poll(self) -> None:
        while not self._stop_evt.is_set():
            self._poll_once()
            self._stop_evt.wait(self.refresh_s)

    def snapshot(self, now: float) -> list[Event]:
        """Events that haven't finished, soonest first. Empty if the last fetch went stale."""
        with self._lock:
            if now - self._fetched_at > self.stale_s:
                return []
            events = self._events
        return [e for e in events if e.end > now][: self.count]

    # -- App protocol --------------------------------------------------------

    def start(self) -> None:
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._poll, name="calendar-poll", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_evt.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def wants_display(self, now: float) -> bool:
        return bool(self.snapshot(now))

    def render(self, canvas: Canvas, now: float) -> None:
        canvas.clear()
        pitch = self._fh + 1
        cols = self.width // self._fw
        for i, event in enumerate(self.snapshot(now)):
            y = i * 2 * pitch
            canvas.text(0, y, when(event, now)[:cols], self.date_color, self.font)
            canvas.text(0, y + pitch, event.title[:cols], self.color, self.font)


def when(event: Event, now: float) -> str:
    """'Today 19:30', 'Tmrw', 'Fri 19:30', 'Sat 10 Oct 19:30'. Local time."""
    start = datetime.fromtimestamp(event.start)
    days = (start.date() - date.fromtimestamp(now)).days
    if days <= 0:
        day = "Today"
    elif days == 1:
        day = "Tmrw"
    elif days < 7:
        day = start.strftime("%a")
    else:
        day = f"{start.strftime('%a')} {start.day} {start.strftime('%b')}"
    return day if event.all_day else f"{day} {start.strftime('%H:%M')}"
