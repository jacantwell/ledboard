"""Picks the highest-priority app that wants the screen, renders it, pushes the frame."""

import logging
import threading
import time
from collections.abc import Iterable

import numpy as np

from ledboard.app import App
from ledboard.canvas import Canvas
from ledboard.display.base import Display, FrameStore

log = logging.getLogger(__name__)


def brightness_lut(level: float, gamma: float = 2.2) -> np.ndarray:
    """Scale in linear light so 0.5 looks half as bright, not a quarter."""
    level = min(max(level, 0.0), 1.0)
    i = np.arange(256, dtype=np.float64) / 255.0
    out = (i**gamma * level) ** (1.0 / gamma) * 255.0
    return np.round(out).astype(np.uint8)


class Scheduler:
    def __init__(
        self,
        display: Display,
        apps: Iterable[App],
        store: FrameStore | None = None,
        fps: int = 30,
        brightness: float = 1.0,
        stop_when_idle: bool = False,
    ) -> None:
        self.display = display
        self.apps = sorted(apps, key=lambda a: a.priority, reverse=True)
        self.store = store
        self.fps = fps
        self.stop_when_idle = stop_when_idle
        self.canvas = Canvas(display.width, display.height)
        self._lut = brightness_lut(brightness)
        self._out = np.zeros_like(self.canvas.fb)
        self.active: str | None = None
        self.ticks = 0

    def set_brightness(self, level: float) -> None:
        self._lut = brightness_lut(level)

    def pick(self, now: float) -> App | None:
        for app in self.apps:
            if app.wants_display(now):
                return app
        return None

    def tick(self, now: float | None = None) -> str | None:
        now = time.time() if now is None else now
        app = self.pick(now)
        if app is None:
            self.canvas.clear()
        else:
            try:
                app.render(self.canvas, now)
            except Exception:  # noqa: BLE001 - one bad app must not kill the panel
                log.exception("%s.render failed, blanking this frame", app.name)
                self.canvas.clear()
        np.take(self._lut, self.canvas.fb, out=self._out)
        self.display.show(self._out)
        if self.store is not None:
            self.store.publish(self._out, app.name if app else None, now)
        self.active = app.name if app else None
        self.ticks += 1
        return self.active

    def run(self, stop: threading.Event) -> None:
        for app in self.apps:
            app.start()
        period = 1.0 / self.fps
        log.info("scheduler running at %d fps with apps %s", self.fps, [a.name for a in self.apps])
        try:
            while not stop.is_set():
                t0 = time.time()
                if self.stop_when_idle and self.pick(t0) is None:
                    break
                self.tick(t0)
                stop.wait(max(0.0, period - (time.time() - t0)))
        finally:
            for app in self.apps:
                app.stop()
            self.display.close()
            log.info("scheduler stopped, display blanked")
