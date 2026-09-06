"""Live bus countdown for one stop. Fetches on its own thread, yields when it has nothing."""

import logging
import threading
import time
from collections.abc import Callable, Sequence

from ledboard import fonts
from ledboard.canvas import Canvas, Color, parse_color, text_width
from ledboard.schedule import Windows
from ledboard.tfl import BASE, ArrivalsClient, Departure

log = logging.getLogger(__name__)

DUE_S = 30.0  # under this, a bus is "due" rather than a number of minutes
GAP = 2  # pixels between the route, destination and countdown columns
ROUTE_COLS = 4  # fixed so destinations line up; "N171" is as long as they get


class BusApp:
    name = "bus"
    priority = 20  # above the clock, below a message someone actually sent

    def __init__(
        self,
        width: int,
        height: int,
        stop_id: str = "59378",
        routes: Sequence[str] = (),
        windows: Windows | None = None,
        refresh_s: float = 30.0,
        stale_s: float = 120.0,
        color: str | Color = "#FF8C00",
        font: str = "5x7",
        api_key: str = "",
        api_url: str = "",
        fetch: Callable[[], list[Departure]] | None = None,
    ) -> None:
        self.width = width
        self.height = height
        self.windows = windows or Windows()
        self.refresh_s = refresh_s
        self.stale_s = stale_s
        self.color = parse_color(color)
        self.font = font
        self._fw, self._fh = fonts.size(font)
        self.rows = max(1, height // (self._fh + 1))
        if fetch is None:
            client = ArrivalsClient(stop_id, routes, api_key=api_key, base_url=api_url or BASE)
            fetch = client.fetch
        self._fetch = fetch
        self._lock = threading.Lock()
        self._departures: list[Departure] = []
        self._fetched_at: float = 0.0
        self._stop_evt = threading.Event()
        self._thread: threading.Thread | None = None

    # -- polling -------------------------------------------------------------

    def _poll_once(self, now: float | None = None) -> None:
        try:
            departures = self._fetch()
        except Exception:
            # A blip must never kill the poll thread; going stale hands over to the clock.
            log.warning("bus fetch failed", exc_info=True)
            return
        with self._lock:
            self._departures = departures
            self._fetched_at = time.time() if now is None else now

    def _poll(self) -> None:
        while not self._stop_evt.is_set():
            if self.windows.contains(time.time()):
                self._poll_once()
            self._stop_evt.wait(self.refresh_s)

    def snapshot(self, now: float) -> list[Departure]:
        """Departures still in the future, soonest first. Empty if the last fetch went stale."""
        with self._lock:
            if now - self._fetched_at > self.stale_s:
                return []
            departures = self._departures
        return [d for d in departures if d.eta > now]

    # -- App protocol --------------------------------------------------------

    def start(self) -> None:
        self._stop_evt.clear()
        self._thread = threading.Thread(target=self._poll, name="bus-poll", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop_evt.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
            self._thread = None

    def wants_display(self, now: float) -> bool:
        return self.windows.contains(now) and bool(self.snapshot(now))

    def render(self, canvas: Canvas, now: float) -> None:
        canvas.clear()
        for i, dep in enumerate(self.snapshot(now)[: self.rows]):
            self._row(canvas, i * (self._fh + 1), dep, now)

    # -- drawing -------------------------------------------------------------

    def _row(self, canvas: Canvas, y: int, dep: Departure, now: float) -> None:
        eta = countdown(dep.eta - now)
        eta_w = text_width(eta, self.font)
        dest_x = ROUTE_COLS * self._fw + GAP
        room = self.width - eta_w - GAP - dest_x

        canvas.text(0, y, dep.line[:ROUTE_COLS], self.color, self.font)
        canvas.text(dest_x, y, self._fit(dep.destination, room), self.color, self.font)
        canvas.text(self.width - eta_w, y, eta, self.color, self.font)

    def _fit(self, text: str, room: int) -> str:
        """Longest prefix that fits in `room` pixels. Fixed-width font, so it's just division."""
        if room <= 0:
            return ""
        return text[: room // self._fw]


def countdown(seconds: float) -> str:
    """TfL's own wording: anything closer than half a minute is due, otherwise whole minutes."""
    if seconds < DUE_S:
        return "due"
    return str(int(seconds // 60))
