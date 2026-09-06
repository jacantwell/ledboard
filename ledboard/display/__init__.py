from ledboard.config import Settings
from ledboard.display.base import Display, FrameStore


def make_display(settings: Settings) -> Display:
    w, h = settings.width, settings.height
    match settings.display:
        case "hw":
            from ledboard.display.hw import HardwareDisplay

            return HardwareDisplay(w, h)
        case "png":
            from ledboard.display.png import PngDisplay

            return PngDisplay(w, h, settings.png_path, settings.png_scale)
        case "array":
            from ledboard.display.array import ArrayDisplay

            return ArrayDisplay(w, h)
        case "web":
            from ledboard.display.array import ArrayDisplay

            # The web sim reads from the FrameStore the scheduler publishes to,
            # so "web" is just "no physical output".
            return ArrayDisplay(w, h)
    raise ValueError(f"unknown display {settings.display!r}")


__all__ = ["Display", "FrameStore", "make_display"]
