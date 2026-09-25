import pytest

from ledboard.apps import BusApp, CalendarApp, ClockApp, TextApp, build_apps
from ledboard.apps import TestPatternApp as PatternApp
from ledboard.config import Settings


@pytest.mark.parametrize(
    "apps,expected",
    [
        ("text,clock", ["text", "clock"]),
        (" text , clock ", ["text", "clock"]),
        ("text,,clock", ["text", "clock"]),
        ("", []),
        ("clock", ["clock"]),
    ],
)
def test_app_names_splits_the_comma_list(apps, expected):
    assert Settings(_env_file=None, apps=apps).app_names == expected, "whitespace and gaps ignored"


@pytest.mark.parametrize("prefix", ["LEDBOARD_"])
def test_settings_read_the_env(monkeypatch: pytest.MonkeyPatch, prefix):
    monkeypatch.setenv(f"{prefix}WIDTH", "64")
    monkeypatch.setenv(f"{prefix}DISPLAY", "array")
    settings = Settings(_env_file=None)
    assert (settings.width, settings.display) == (64, "array"), "env vars win over defaults"


@pytest.mark.parametrize(
    "name,cls",
    [("text", TextApp), ("clock", ClockApp), ("testpattern", PatternApp), ("bus", BusApp)],
)
def test_build_apps_makes_each_known_app(name, cls):
    settings = Settings(_env_file=None, apps=name, width=64, height=16)
    apps = build_apps(settings)
    assert list(apps) == [name], "only the named apps are built"
    assert isinstance(apps[name], cls), f"{name} builds a {cls.__name__}"
    assert (apps[name].width, apps[name].height) == (64, 16), "the panel size is passed down"


def test_build_apps_passes_text_settings_through():
    settings = Settings(
        _env_file=None,
        apps="text",
        text_dwell_s=1.5,
        text_scroll_pps=99.0,
        text_color="#00ff00",
    )
    app = build_apps(settings)["text"]
    assert app.dwell_s == 1.5, "dwell comes from settings"
    assert app.scroll_pps == 99.0, "scroll speed comes from settings"
    assert app.default_color == (0, 255, 0), "the default colour comes from settings"


@pytest.mark.parametrize(
    "routes,expected",
    [("", []), ("12", ["12"]), (" 12 , 36 ", ["12", "36"]), ("12,,36", ["12", "36"])],
)
def test_bus_route_names_splits_the_comma_list(routes, expected):
    settings = Settings(_env_file=None, bus_routes=routes)
    assert settings.bus_route_names == expected, "whitespace and gaps ignored"


def test_build_apps_passes_bus_settings_through():
    settings = Settings(
        _env_file=None,
        apps="bus",
        bus_routes="12,36",
        bus_windows="07:00-10:00",
        bus_refresh_s=15.0,
        bus_stale_s=90.0,
        bus_color="#00ff00",
    )
    app = build_apps(settings)["bus"]
    assert app.refresh_s == 15.0, "the refresh interval comes from settings"
    assert app.stale_s == 90.0, "the staleness cutoff comes from settings"
    assert app.color == (0, 255, 0), "the colour comes from settings"
    assert app.windows.spans == ((420, 600),), "the windows spec is parsed at build time"


def test_build_apps_rejects_a_bad_bus_window():
    settings = Settings(_env_file=None, apps="bus", bus_windows="breakfast")
    with pytest.raises(ValueError, match="bad window"):
        build_apps(settings)


def test_build_apps_rejects_an_unknown_app():
    with pytest.raises(ValueError, match="unknown app"):
        build_apps(Settings(_env_file=None, apps="disco"))


def calendar_settings(**kwargs) -> Settings:
    kwargs.setdefault("calendar_id", "family@group.calendar.google.com")
    kwargs.setdefault("calendar_credentials", "/etc/ledboard/sa.json")
    return Settings(_env_file=None, apps="calendar", width=64, height=16, **kwargs)


def test_build_apps_makes_a_calendar_when_configured():
    apps = build_apps(calendar_settings())
    assert list(apps) == ["calendar"], "only the named apps are built"
    assert isinstance(apps["calendar"], CalendarApp), "calendar builds a CalendarApp"
    assert (apps["calendar"].width, apps["calendar"].height) == (64, 16), "panel size passed down"


def test_build_apps_does_not_touch_the_network_or_key_file():
    app = build_apps(calendar_settings(calendar_credentials="/nope/missing.json"))["calendar"]
    assert app.snapshot(0.0) == [], "nothing is fetched until the poll thread starts"


def test_build_apps_wires_the_calendar_client():
    client = build_apps(calendar_settings())["calendar"]._fetch.__self__
    assert client.calendar_id == "family@group.calendar.google.com", "the id reaches the client"
    assert client.credentials_path == "/etc/ledboard/sa.json", "and so does the key file path"


@pytest.mark.parametrize(
    "overrides",
    [
        {"calendar_id": ""},
        {"calendar_credentials": ""},
        {"calendar_id": "", "calendar_credentials": ""},
    ],
    ids=["no-id", "no-creds", "neither"],
)
def test_build_apps_rejects_a_half_configured_calendar(overrides):
    with pytest.raises(ValueError, match="calendar needs"):
        build_apps(calendar_settings(**overrides))


def test_build_apps_passes_calendar_settings_through():
    app = build_apps(
        calendar_settings(
            calendar_count=3,
            calendar_refresh_s=60.0,
            calendar_stale_s=900.0,
            calendar_color="#00ff00",
        )
    )["calendar"]
    assert app.count == 3, "the event count comes from settings"
    assert app.refresh_s == 60.0, "the refresh interval comes from settings"
    assert app.stale_s == 900.0, "the staleness cutoff comes from settings"
    assert app.color == (0, 255, 0), "the colour comes from settings"


@pytest.mark.parametrize(
    "field,env,expected",
    [
        ("calendar_id", "abc@group.calendar.google.com", "abc@group.calendar.google.com"),
        ("calendar_credentials", "/etc/sa.json", "/etc/sa.json"),
        ("calendar_count", "3", 3),
        ("calendar_refresh_s", "60", 60.0),
        ("calendar_stale_s", "900", 900.0),
        ("calendar_color", "#00ff00", "#00ff00"),
    ],
)
def test_calendar_settings_read_the_env(monkeypatch: pytest.MonkeyPatch, field, env, expected):
    monkeypatch.setenv(f"LEDBOARD_{field.upper()}", env)
    assert getattr(Settings(_env_file=None), field) == expected, f"{field} comes from the env"


@pytest.mark.parametrize(
    "field,expected",
    [
        ("calendar_id", ""),
        ("calendar_credentials", ""),
        ("calendar_count", 2),
        ("calendar_refresh_s", 300.0),
        ("calendar_stale_s", 3600.0),
        ("calendar_color", "#FF8C00"),
    ],
)
def test_calendar_setting_defaults(field, expected):
    assert getattr(Settings(_env_file=None), field) == expected, f"{field} defaults sensibly"
