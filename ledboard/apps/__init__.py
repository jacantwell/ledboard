from ledboard.app import App
from ledboard.apps.bus import BusApp
from ledboard.apps.calendar import CalendarApp
from ledboard.apps.clock import ClockApp
from ledboard.apps.etch import EtchApp
from ledboard.apps.testpattern import TestPatternApp
from ledboard.apps.text import TextApp
from ledboard.config import Settings
from ledboard.gcal import CalendarClient
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
        "etch": lambda: EtchApp(w, h, color=settings.etch_color),
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
        "calendar": lambda: _calendar(settings),
    }
    apps: dict[str, App] = {}
    for name in settings.app_names:
        if name not in factories:
            raise ValueError(f"unknown app {name!r}, known: {sorted(factories)}")
        apps[name] = factories[name]()
    return apps


def _calendar(settings: Settings) -> CalendarApp:
    if not (settings.calendar_id and settings.calendar_credentials):
        raise ValueError("calendar needs LEDBOARD_CALENDAR_ID and LEDBOARD_CALENDAR_CREDENTIALS")
    client = CalendarClient(settings.calendar_id, settings.calendar_credentials)
    return CalendarApp(
        settings.width,
        settings.height,
        fetch=client.fetch,
        count=settings.calendar_count,
        refresh_s=settings.calendar_refresh_s,
        stale_s=settings.calendar_stale_s,
        color=settings.calendar_color,
    )


__all__ = [
    "BusApp",
    "CalendarApp",
    "ClockApp",
    "EtchApp",
    "TestPatternApp",
    "TextApp",
    "build_apps",
]
