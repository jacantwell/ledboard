import importlib.util

import numpy as np
import pytest
from PIL import Image

from ledboard.display import make_display
from ledboard.display.array import ArrayDisplay
from ledboard.display.png import PngDisplay


def test_array_display_keeps_the_last_frame():
    d = ArrayDisplay(4, 3)
    d.show(np.full((3, 4, 3), 9, dtype=np.uint8))
    assert (d.frame == 9).all(), "the frame is stored"
    assert d.shows == 1, "shows are counted"


def test_array_display_close_blanks_the_frame():
    d = ArrayDisplay(4, 3)
    d.show(np.full((3, 4, 3), 9, dtype=np.uint8))
    d.close()
    assert not d.frame.any(), "close blanks the frame"


@pytest.mark.parametrize("width,height,scale", [(8, 4, 1), (16, 8, 3), (128, 32, 8)])
def test_png_display_writes_a_scaled_image(tmp_path, width, height, scale):
    path = tmp_path / "nested" / "frame.png"
    d = PngDisplay(width, height, str(path), scale=scale)
    d.show(np.full((height, width, 3), 200, dtype=np.uint8))

    assert path.exists(), "the png is written, parent directories included"
    with Image.open(path) as img:
        assert img.size == (width * scale, height * scale), "the image is scaled up"
        assert img.convert("RGB").getpixel((0, 0)) == (200, 200, 200), "pixel colours survive"


def test_png_display_overwrites_atomically(tmp_path):
    path = tmp_path / "frame.png"
    d = PngDisplay(4, 4, str(path), scale=2)
    d.show(np.full((4, 4, 3), 10, dtype=np.uint8))
    d.show(np.full((4, 4, 3), 250, dtype=np.uint8))

    with Image.open(path) as img:
        assert img.convert("RGB").getpixel((0, 0)) == (250, 250, 250), "the newest frame wins"
    leftovers = [p.name for p in tmp_path.iterdir() if p.name != "frame.png"]
    assert leftovers == [], f"no temp files left behind, found {leftovers}"
    d.close()


@pytest.mark.parametrize("kind,expected", [("array", ArrayDisplay), ("web", ArrayDisplay)])
def test_make_display_builds_the_requested_display(settings, kind, expected):
    settings.display = kind
    d = make_display(settings)
    assert isinstance(d, expected), f"{kind} maps to {expected.__name__}"
    assert (d.width, d.height) == (settings.width, settings.height), "size comes from settings"


def test_make_display_builds_a_png_display(settings):
    settings.display = "png"
    assert isinstance(make_display(settings), PngDisplay), "png maps to PngDisplay"


def test_make_display_rejects_unknown_kinds(settings):
    settings.display = "hologram"
    with pytest.raises(ValueError, match="unknown display"):
        make_display(settings)


@pytest.mark.skipif(
    importlib.util.find_spec("adafruit_blinka_raspberry_pi5_piomatter") is not None,
    reason="the piomatter library is installed, so the import does not fail",
)
def test_hardware_display_explains_the_missing_library():
    from ledboard.display.hw import HardwareDisplay

    with pytest.raises(RuntimeError, match="piomatter"):
        HardwareDisplay(128, 32)
