import pytest

from ledboard.apps import ClockApp, TextApp, build_apps
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
    "name,cls", [("text", TextApp), ("clock", ClockApp), ("testpattern", PatternApp)]
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


def test_build_apps_rejects_an_unknown_app():
    with pytest.raises(ValueError, match="unknown app"):
        build_apps(Settings(_env_file=None, apps="disco"))
