import pytest
from fastapi.testclient import TestClient

from ledboard.api import create_api
from ledboard.apps import build_apps
from ledboard.apps.etch import EtchApp
from ledboard.config import Settings
from ledboard.display.base import FrameStore

WIDTH = 128
HEIGHT = 32


@pytest.fixture
def etch_app() -> EtchApp:
    return EtchApp(WIDTH, HEIGHT)


@pytest.fixture
def client(store: FrameStore, etch_app: EtchApp) -> TestClient:
    settings = Settings(_env_file=None, width=WIDTH, height=HEIGHT)
    return TestClient(create_api(settings, store, None, etch_app=etch_app))


def test_get_etch_returns_state(client: TestClient, etch_app: EtchApp):
    body = client.get("/etch").json()
    assert (body["w"], body["h"]) == (WIDTH, HEIGHT), "size is reported"
    assert (body["x"], body["y"]) == etch_app.cursor, "cursor is reported"
    assert body["lit"] == 1, "fresh board has one pixel"
    assert body["pixels_b64"], "the bitmap rides along"


def test_post_move_draws(client: TestClient, etch_app: EtchApp):
    x0, y0 = etch_app.cursor
    r = client.post("/etch/move", json={"dx": 4, "dy": 0})
    assert r.status_code == 200, r.text
    assert r.json() == {"x": x0 + 4, "y": y0}, "the new cursor is echoed"
    assert etch_app.lit_count == 5, "the line reached the app"


def test_post_move_rejects_zero_step(client: TestClient):
    assert client.post("/etch/move", json={"dx": 0, "dy": 0}).status_code == 422


@pytest.mark.parametrize("payload", [{"dx": 33}, {"dy": -33}, {"dx": "far"}])
def test_post_move_rejects_absurd_steps(client: TestClient, payload):
    r = client.post("/etch/move", json={"dx": 0, "dy": 0, **payload})
    assert r.status_code == 422, f"{payload!r} is not a knob nudge"


def test_post_clear_shakes_clean(client: TestClient, etch_app: EtchApp):
    client.post("/etch/move", json={"dx": 5, "dy": 0})
    pos = etch_app.cursor
    r = client.post("/etch/clear")
    assert r.status_code == 200, r.text
    assert r.json() == {"cleared": True, "x": pos[0], "y": pos[1]}, "shake keeps the stylus"
    assert etch_app.lit_count == 1, "the screen is wiped"


def test_etch_endpoints_are_disabled_without_the_app(store: FrameStore):
    settings = Settings(_env_file=None)
    client = TestClient(create_api(settings, store, None))
    assert client.get("/etch").status_code == 503, "no etch app, no state"
    assert client.post("/etch/move", json={"dx": 1}).status_code == 503
    assert client.post("/etch/clear").status_code == 503


def test_build_apps_makes_etch():
    apps = build_apps(Settings(_env_file=None, apps="etch", width=64, height=16))
    assert isinstance(apps["etch"], EtchApp), "etch builds like every other app"
    assert (apps["etch"].width, apps["etch"].height) == (64, 16)


def test_build_apps_passes_etch_settings_through():
    apps = build_apps(Settings(_env_file=None, apps="etch", etch_color="#00ff00"))
    assert apps["etch"].color == (0, 255, 0), "the colour comes from settings"


def test_sim_page_has_the_etch_tab(client: TestClient):
    html = client.get("/sim").text
    assert "etch-a-sketch" in html, "the tab is there"
    assert "knob-x" in html and "knob-y" in html, "both knobs are there"
    assert "shake" in html.lower(), "shake-to-clear is there"


FRONTEND_ORIGIN = "https://home-dash.example"


@pytest.fixture
def gated_client(store: FrameStore, etch_app: EtchApp) -> TestClient:
    settings = Settings(
        _env_file=None,
        width=WIDTH,
        height=HEIGHT,
        auth_authorized_parties=f"{FRONTEND_ORIGIN},http://localhost:3000",
    )
    return TestClient(create_api(settings, store, None, etch_app=etch_app))


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("GET", "/etch", None),
        ("POST", "/etch/move", {"dx": 1}),
        ("POST", "/etch/clear", None),
    ],
)
def test_etch_is_open_without_configured_parties(
    client: TestClient, method: str, path: str, payload
):
    assert client.request(method, path, json=payload).status_code == 200


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("GET", "/etch", None),
        ("POST", "/etch/move", {"dx": 1}),
        ("POST", "/etch/clear", None),
    ],
)
def test_etch_rejects_requests_without_a_frontend_origin(
    gated_client: TestClient, method: str, path: str, payload
):
    r = gated_client.request(method, path, json=payload)
    assert r.status_code == 403, f"{method} {path} needs a frontend Origin"
    assert "home-dash frontend" in r.json()["detail"]


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("GET", "/etch", None),
        ("POST", "/etch/move", {"dx": 1}),
        ("POST", "/etch/clear", None),
    ],
)
def test_etch_rejects_a_foreign_origin(gated_client: TestClient, method: str, path: str, payload):
    r = gated_client.request(method, path, json=payload, headers={"Origin": "https://evil.example"})
    assert r.status_code == 403


def test_etch_accepts_the_frontend_origin(gated_client: TestClient):
    assert gated_client.get("/etch", headers={"Origin": FRONTEND_ORIGIN}).status_code == 200
    assert (
        gated_client.post(
            "/etch/move", json={"dx": 1}, headers={"Origin": FRONTEND_ORIGIN}
        ).status_code
        == 200
    )


def test_etch_accepts_a_frontend_referer(gated_client: TestClient):
    r = gated_client.get("/etch", headers={"Referer": f"{FRONTEND_ORIGIN}/etch"})
    assert r.status_code == 200, "the page path on the referer is fine"
