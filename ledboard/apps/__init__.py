from ledboard.app import App
from ledboard.apps.bus import BusApp
from ledboard.apps.clock import ClockApp
from ledboard.apps.testpattern import TestPatternApp
from ledboard.apps.text import TextApp
from ledboard.config import Settings
from ledboard.schedule import Windows


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
        "bus": lambda: BusApp(
            w,
            h,
            stop_id=settings.bus_stop_id,
            routes=settings.bus_route_names,
            windows=Windows.parse(settings.bus_windows),
            refresh_s=settings.bus_refresh_s,
            stale_s=settings.bus_stale_s,
            color=settings.bus_color,
            font=settings.bus_font,
            api_key=settings.bus_api_key,
            api_url=settings.bus_api_url,
        ),
    }
    apps: dict[str, App] = {}
    for name in settings.app_names:
        if name not in factories:
            raise ValueError(f"unknown app {name!r}, known: {sorted(factories)}")
        apps[name] = factories[name]()
    return apps


__all__ = ["BusApp", "ClockApp", "TestPatternApp", "TextApp", "build_apps"]
