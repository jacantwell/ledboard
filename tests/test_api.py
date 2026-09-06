import time

import numpy as np
import pytest
from fastapi.testclient import TestClient

from ledboard import __version__
from ledboard.api import RateLimiter, create_api
from ledboard.apps.text import TextApp
from ledboard.config import Settings
from ledboard.display.base import FrameStore

WIDTH = 128
HEIGHT = 32


@pytest.fixture
def text_app() -> TextApp:
    return TextApp(WIDTH, HEIGHT)


@pytest.fixture
def api_settings() -> Settings:
    return Settings(_env_file=None, width=WIDTH, height=HEIGHT, text_max_len=20)


@pytest.fixture
def client(api_settings: Settings, store: FrameStore, text_app: TextApp) -> TestClient:
    return TestClient(create_api(api_settings, store, text_app))


def publish_a_frame(store: FrameStore, app: str = "text") -> None:
    store.publish(np.zeros((store.height, store.width, 3), dtype=np.uint8), app, now=time.time())


# -- POST /text ----------------------------------------------------------------


def test_post_text_queues_a_plain_body(client: TestClient, text_app: TextApp):
    r = client.post("/text", content="hello wall")

    assert r.status_code == 202, r.text
    assert r.json() == {
        "queued": True,
        "position": 1,
        "text": "hello wall",
        "duration_s": None,
    }, "echoes what queued"
    assert text_app.pending == 1, "the message reached the app"


def test_post_text_accepts_a_json_body_with_a_colour(client: TestClient, text_app: TextApp):
    r = client.post("/text", json={"text": "hi", "color": "#00ff00"})

    assert r.status_code == 202, r.text
    assert text_app.pending == 1, "the message reached the app"


@pytest.mark.parametrize("color", ["nope", "#12345", "#gg0000", "1234"])
def test_post_text_rejects_a_bad_colour(client: TestClient, text_app: TextApp, color):
    r = client.post("/text", json={"text": "hi", "color": color})

    assert r.status_code == 422, f"{color!r} is not a colour"
    assert text_app.pending == 0, "nothing is queued"


@pytest.mark.parametrize(
    "body",
    ['{"color": "#fff"}', '{"text": ""}', '{"text": 5}', "[]", "not json at all"],
)
def test_post_text_rejects_a_bad_json_body(client: TestClient, body):
    r = client.post("/text", content=body, headers={"content-type": "application/json"})
    assert r.status_code == 422, f"{body!r} is not a valid payload"


@pytest.mark.parametrize("raw", ["   ", "\n\n", "\t", "\x00\x01"])
def test_post_text_rejects_text_that_cleans_away_to_nothing(client: TestClient, raw):
    r = client.post("/text", content=raw)
    assert r.status_code == 400, f"{raw!r} has no visible characters"


def test_post_text_rejects_text_over_the_limit(client: TestClient, api_settings: Settings):
    r = client.post("/text", content="x" * (api_settings.text_max_len + 1))
    assert r.status_code == 413, "over-long messages are refused"


@pytest.mark.parametrize(
    "raw,cleaned",
    [
        ("  hi  ", "hi"),
        ("a\tb", "a b"),
        ("a\nb", "a b"),
        ("a\r\nb", "a b"),
        ("a     b", "a b"),
        ("he\x00ll\x07o", "hello"),
        ("\x1bok\x7f", "ok"),
    ],
)
def test_post_text_cleans_the_message(client: TestClient, raw, cleaned):
    r = client.post("/text", content=raw.encode())
    assert r.status_code == 202, r.text
    assert r.json()["text"] == cleaned, f"{raw!r} should clean to {cleaned!r}"


@pytest.mark.parametrize("color", [None, ""])
def test_post_text_falls_back_to_the_default_colour(client: TestClient, color):
    r = client.post("/text", json={"text": "hi", "color": color})
    assert r.status_code == 202, f"{color!r} means 'use the board default'"


@pytest.mark.parametrize("duration", [1, 30.5, 60])
def test_post_text_accepts_a_duration(client: TestClient, text_app: TextApp, duration):
    r = client.post("/text", json={"text": "hi", "duration_s": duration})

    assert r.status_code == 202, r.text
    assert r.json()["duration_s"] == duration, "the duration is echoed back"
    assert text_app.pending == 1, "the message reached the app"


@pytest.mark.parametrize("duration", [60.01, 61, 100000])
def test_post_text_rejects_a_duration_over_the_max(client: TestClient, text_app: TextApp, duration):
    r = client.post("/text", json={"text": "hi", "duration_s": duration})

    assert r.status_code == 422, f"{duration}s is over the 60s cap"
    assert "60" in r.json()["detail"], "the cap is named"
    assert text_app.pending == 0, "nothing is queued"


@pytest.mark.parametrize("duration", [0, -5, "ten", "10s"])
def test_post_text_rejects_a_bad_duration(client: TestClient, text_app: TextApp, duration):
    r = client.post("/text", json={"text": "hi", "duration_s": duration})

    assert r.status_code == 422, f"{duration!r} is not a valid duration"
    assert text_app.pending == 0, "nothing is queued"


def test_post_text_max_duration_comes_from_settings(store: FrameStore, text_app: TextApp):
    settings = Settings(_env_file=None, text_max_duration_s=10)
    client = TestClient(create_api(settings, store, text_app))

    assert client.post("/text", json={"text": "hi", "duration_s": 10}).status_code == 202
    assert client.post("/text", json={"text": "hi", "duration_s": 11}).status_code == 422


def test_post_text_reports_the_queue_position(client: TestClient):
    positions = [client.post("/text", content=f"msg {i}").json()["position"] for i in range(3)]
    assert positions == [1, 2, 3], "each message reports where it landed"


def test_post_text_is_disabled_without_a_text_app(api_settings: Settings, store: FrameStore):
    client = TestClient(create_api(api_settings, store, None))
    assert client.post("/text", content="hi").status_code == 503, "no text app, no posting"


# -- DELETE /text --------------------------------------------------------------


def test_delete_text_clears_the_queue(client: TestClient, text_app: TextApp):
    client.post("/text", content="one")
    client.post("/text", content="two")

    r = client.delete("/text")

    assert r.status_code == 200 and r.json() == {"cleared": True}, r.text
    assert text_app.pending == 0, "the queue is empty"


def test_delete_text_is_disabled_without_a_text_app(api_settings: Settings, store: FrameStore):
    client = TestClient(create_api(api_settings, store, None))
    assert client.delete("/text").status_code == 503, "no text app, nothing to clear"


# -- rate limiting -------------------------------------------------------------


def test_rate_limit_kicks_in_after_the_allowance(store: FrameStore, text_app: TextApp):
    settings = Settings(_env_file=None, rate_limit_per_min=3)
    client = TestClient(create_api(settings, store, text_app))

    codes = [client.post("/text", content="hi").status_code for _ in range(4)]

    assert codes == [202, 202, 202, 429], "the fourth message in a minute is refused"


def test_rate_limit_is_per_client(store: FrameStore, text_app: TextApp):
    settings = Settings(_env_file=None, rate_limit_per_min=2)
    client = TestClient(create_api(settings, store, text_app))
    mine = {"x-forwarded-for": "10.0.0.1"}
    theirs = {"x-forwarded-for": "10.0.0.2"}

    for _ in range(2):
        client.post("/text", content="hi", headers=mine)

    assert client.post("/text", content="hi", headers=mine).status_code == 429, "I am capped"
    assert client.post("/text", content="hi", headers=theirs).status_code == 202, "they are not"


@pytest.mark.parametrize("per_minute", [0, -1])
def test_rate_limiter_disabled_allows_everything(per_minute):
    limiter = RateLimiter(per_minute)
    assert all(limiter.allow("a", now=0.0) for _ in range(50)), "a limit of 0 means no limit"


def test_rate_limiter_counts_within_the_window():
    limiter = RateLimiter(2)
    assert limiter.allow("a", now=100.0) is True, "first is fine"
    assert limiter.allow("a", now=130.0) is True, "second is fine"
    assert limiter.allow("a", now=150.0) is False, "third within the minute is refused"


def test_rate_limiter_window_expires():
    limiter = RateLimiter(2)
    limiter.allow("a", now=100.0)
    limiter.allow("a", now=101.0)
    assert limiter.allow("a", now=140.0) is False, "still inside the window"
    assert limiter.allow("a", now=161.1) is True, "the oldest hit has aged out"


def test_rate_limiter_keys_are_independent():
    limiter = RateLimiter(1)
    assert limiter.allow("a", now=0.0) is True, "first client gets its one hit"
    assert limiter.allow("a", now=1.0) is False, "and no more"
    assert limiter.allow("b", now=1.0) is True, "a second client is unaffected"


# -- GET /healthz, /, /sim -----------------------------------------------------


def test_healthz_is_not_ok_before_any_frame(client: TestClient):
    body = client.get("/healthz").json()

    assert body["ok"] is False, "no frame has been shown yet"
    assert body["last_frame_age_s"] is None, "so there is no frame age"
    assert body["version"] == __version__, "the version is reported"
    assert body["size"] == [WIDTH, HEIGHT], "the panel size is reported"


def test_healthz_is_ok_after_a_frame(client: TestClient, store: FrameStore):
    publish_a_frame(store, app="clock")
    body = client.get("/healthz").json()

    assert body["ok"] is True, "a fresh frame means healthy"
    assert body["active_app"] == "clock", "the active app is reported"
    assert body["last_frame_age_s"] < 5.0, "the frame is recent"


def test_healthz_is_not_ok_when_the_frame_is_stale(client: TestClient, store: FrameStore):
    store.publish(np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8), "clock", now=time.time() - 60)
    assert client.get("/healthz").json()["ok"] is False, "an old frame means unhealthy"


def test_healthz_reports_pending_text(client: TestClient):
    client.post("/text", content="hi")
    assert client.get("/healthz").json()["pending_text"] == 1, "queued messages are visible"


def test_healthz_reports_no_pending_text_without_a_text_app(
    api_settings: Settings, store: FrameStore
):
    client = TestClient(create_api(api_settings, store, None))
    assert client.get("/healthz").json()["pending_text"] is None, "no text app, no count"


def test_root_describes_the_api(client: TestClient):
    r = client.get("/")

    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/plain"), "the index is plain text"
    assert __version__ in r.text and "/text" in r.text, "it names the version and the endpoints"


def test_sim_serves_the_simulator_page(client: TestClient):
    r = client.get("/sim")

    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("text/html"), "the simulator is html"
    assert "<canvas" in r.text, "the simulator draws into a canvas element"
