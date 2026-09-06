from ledboard.app import App
from ledboard.apps.clock import ClockApp
from ledboard.apps.testpattern import TestPatternApp
from ledboard.apps.text import TextApp
from ledboard.config import Settings


def build_apps(settings: Settings) -> dict[str, App]:
    """Instantiate the apps named in LEDBOARD_APPS, keyed by name."""
    w, h = settings.width, settings.height
    factories = {
        "text": lambda: TextApp(
            w,
            h,
            dwell_s=settings.text_dwell_s,
            scroll_pps=settings.text_scroll_pps,
            default_color=settings.text_color,
        ),
        "clock": lambda: ClockApp(w, h),
        "testpattern": lambda: TestPatternApp(w, h),
    }
    apps: dict[str, App] = {}
    for name in settings.app_names:
        if name not in factories:
            raise ValueError(f"unknown app {name!r}, known: {sorted(factories)}")
        apps[name] = factories[name]()
    return apps


__all__ = ["ClockApp", "TestPatternApp", "TextApp", "build_apps"]
