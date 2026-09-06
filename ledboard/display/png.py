from pathlib import Path

import numpy as np
from PIL import Image


class PngDisplay:
    """Writes every frame to a scaled PNG. Handy for screenshots in PRs."""

    def __init__(self, width: int, height: int, path: str, scale: int = 8) -> None:
        self.width = width
        self.height = height
        self.path = Path(path)
        self.scale = scale
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def show(self, fb: np.ndarray) -> None:
        img = Image.fromarray(fb, "RGB")
        img = img.resize((self.width * self.scale, self.height * self.scale), Image.NEAREST)
        tmp = self.path.with_suffix(".tmp.png")
        img.save(tmp)
        tmp.replace(self.path)

    def close(self) -> None:
        pass
