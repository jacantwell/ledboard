import io
import json
import urllib.error
import urllib.request

import pytest

from ledboard import __version__
from ledboard.cli import build_parser, main


def parse(argv: list[str]):
    return build_parser().parse_args(argv)


def test_text_command_parses_words_and_options():
    args = parse(["text", "hello", "world", "--color", "#fff", "--display", "array"])

    assert args.cmd == "text", "the subcommand is recorded"
    assert args.text == ["hello", "world"], "free words become the message"
    assert args.color == "#fff", "the colour is passed through"
    assert args.display == "array", "the display override is passed through"
    assert args.dwell == 4.0, "dwell defaults to four seconds"


def test_send_command_parses_the_url():
    args = parse(["send", "yo", "--url", "http://box:9999", "--color", "#f00"])

    assert args.text == ["yo"] and args.url == "http://box:9999", "url and text are parsed"


def test_send_command_has_a_default_url():
    assert parse(["send", "yo"]).url == "http://jasperpi.local:8080", "defaults to the Pi"


@pytest.mark.parametrize(
    "argv,expected",
    [
        (["daemon"], "daemon"),
        (["text", "hi"], "text"),
        (["testpattern"], "testpattern"),
        (["send", "hi"], "send"),
    ],
)
def test_every_subcommand_is_wired_to_a_handler(argv, expected):
    args = parse(argv)
    assert args.cmd == expected, "the subcommand name is recorded"
    assert callable(args.fn), "every subcommand has a handler"


@pytest.mark.parametrize("size,expected", [("128x32", (128, 32)), ("64X16", (64, 16))])
def test_size_option_overrides_the_panel_size(size, expected):
    from ledboard.cli import _settings

    settings = _settings(parse(["text", "hi", "--size", size, "--display", "array"]))
    assert (settings.width, settings.height) == expected, f"--size {size} sets the panel size"


def test_no_subcommand_is_an_error():
    with pytest.raises(SystemExit):
        parse([])


def test_version_flag_prints_the_version(capsys: pytest.CaptureFixture):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])

    assert exc.value.code == 0, "--version exits cleanly"
    assert capsys.readouterr().out.strip() == __version__, "it prints just the version"


def test_text_command_runs_to_completion_on_the_array_display():
    code = main(["text", "hi", "--display", "array", "--dwell", "0.05"])
    assert code == 0, "showing a short message finishes on its own"


def test_testpattern_command_stops_when_it_is_told_to(monkeypatch: pytest.MonkeyPatch):
    # The pattern runs for 13s, so cut it short rather than waiting.
    import ledboard.cli as cli

    calls = {}

    def fake_run_until_done(settings, app, timeout=None):
        calls["app"] = app
        return 0

    monkeypatch.setattr(cli, "_run_until_done", fake_run_until_done)
    assert main(["testpattern", "--loop", "--display", "array"]) == 0, "it returns success"
    assert calls["app"].loop is True, "--loop is passed to the app"


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def test_send_posts_json_to_the_daemon(monkeypatch: pytest.MonkeyPatch, capsys):
    sent = {}

    def fake_urlopen(req, timeout=None):
        sent["url"] = req.full_url
        sent["body"] = json.loads(req.data)
        sent["method"] = req.get_method()
        return FakeResponse(b'{"queued": true}')

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    code = main(["send", "hello", "there", "--url", "http://box:8080/", "--color", "#fff"])

    assert code == 0, "a successful post returns zero"
    assert sent["url"] == "http://box:8080/text", "the trailing slash is handled"
    assert sent["method"] == "POST", "it posts"
    assert sent["body"] == {"text": "hello there", "color": "#fff"}, "the payload is json"
    assert "queued" in capsys.readouterr().out, "the response is printed"


def test_send_reports_an_http_error(monkeypatch: pytest.MonkeyPatch, capsys):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 429, "Too Many", {}, io.BytesIO(b"slow down"))

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert main(["send", "hi", "--url", "http://box:8080"]) == 1, "an http error is a failure"
    assert "429" in capsys.readouterr().err, "the status code is reported"


def test_send_reports_an_unreachable_daemon(monkeypatch: pytest.MonkeyPatch, capsys):
    def fake_urlopen(req, timeout=None):
        raise urllib.error.URLError("connection refused")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert main(["send", "hi", "--url", "http://box:8080"]) == 1, "an unreachable box is a failure"
    assert "could not reach" in capsys.readouterr().err, "the failure is explained"
