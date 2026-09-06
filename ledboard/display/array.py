import numpy as np


class ArrayDisplay:
    """Keeps the last frame in memory. Used by tests and by the web sim."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.frame = np.zeros((height, width, 3), dtype=np.uint8)
        self.shows = 0

    def show(self, fb: np.ndarray) -> None:
        self.frame[:] = fb
        self.shows += 1

    def close(self) -> None:
        self.frame[:] = 0
