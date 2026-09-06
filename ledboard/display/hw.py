import numpy as np


class HardwareDisplay:
    """Adafruit Piomatter on a Pi 5. Import is lazy so laptops never need the lib."""

    def __init__(self, width: int, height: int) -> None:
        try:
            import adafruit_blinka_raspberry_pi5_piomatter as pm
        except ImportError as e:
            raise RuntimeError(
                "LEDBOARD_DISPLAY=hw needs adafruit-blinka-raspberry-pi5-piomatter "
                "(install with the 'hw' extra on a Pi 5)"
            ) from e
        self.width = width
        self.height = height
        geo = pm.Geometry(width=width, height=height, n_addr_lines=5 if height >= 64 else 4)
        self._fb = np.zeros((height, width, 3), dtype=np.uint8)
        self._m = pm.PioMatter(
            colorspace=pm.Colorspace.RGB888Packed,
            pinout=pm.Pinout.AdafruitMatrixBonnet,
            framebuffer=self._fb,
            geometry=geo,
        )

    def show(self, fb: np.ndarray) -> None:
        self._fb[:] = fb
        self._m.show()

    @property
    def fps(self) -> float:
        return float(self._m.fps)

    def close(self) -> None:
        self._fb[:] = 0
        self._m.show()
