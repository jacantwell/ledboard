import threading
from typing import Protocol

import numpy as np


class Display(Protocol):
    width: int
    height: int

    def show(self, fb: np.ndarray) -> None: ...

    def close(self) -> None: ...


class FrameStore:
    """Latest frame, shared between the scheduler thread and the web sim / health API."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self._frame = np.zeros((height, width, 3), dtype=np.uint8)
        self._version = 0
        self._lock = threading.Lock()
        self.active_app: str | None = None
        self.last_show: float = 0.0

    def publish(self, fb: np.ndarray, app: str | None, now: float) -> None:
        with self._lock:
            self._frame[:] = fb
            self._version += 1
            self.active_app = app
            self.last_show = now

    def snapshot(self) -> tuple[int, bytes]:
        with self._lock:
            return self._version, self._frame.tobytes()

    @property
    def version(self) -> int:
        return self._version
