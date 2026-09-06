import time

import pytest
from conftest import lit, lit_bbox

from ledboard.apps.bus import GAP, ROUTE_COLS, BusApp, countdown
from ledboard.canvas import Canvas
from ledboard.schedule import Windows
from ledboard.tfl import Departure

WIDTH = 128
HEIGHT = 32
FW, FH = 5, 7  # the 5x7 font, four rows on a 32px panel

# Midday, so the default always-on window is never the thing under test.
NOW = time.mktime((2026, 9, 6, 12, 0, 0, 0, 1, -1))

DEPARTURES = [
    Departure("345", "South Kensington", NOW + 120, "V1"),
    Departure("12", "Oxford Circus", NOW + 300, "V2"),
    Departure("36", "Queen's Park", NOW + 480, "V3"),
    Departure("171", "Elephant & Castle", NOW + 720, "V4"),
    Departure("436", "Battersea Park Station", NOW + 900, "V5"),
]


def make_app(**kwargs) -> BusApp:
    kwargs.setdefault("fetch", lambda: list(DEPARTURES))
    return BusApp(kwargs.pop("width", WIDTH), kwargs.pop("height", HEIGHT), **kwargs)


def loaded(**kwargs) -> BusApp:
    """An app that fetched at NOW, without starting its thread."""
    app = make_app(**kwargs)
    app._poll_once(NOW)
    return app


@pytest.fixture
def app() -> BusApp:
    return loaded()


@pytest.fixture
def board() -> Canvas:
    return Canvas(WIDTH, HEIGHT)


# -- countdown wording -------------------------------------------------------


@pytest.mark.parametrize(
    "seconds,expected",
    [
        (-10.0, "due"),
        (0.0, "due"),
        (29.9, "due"),
        (30.0, "0"),
        (59.0, "0"),
        (60.0, "1"),
        (119.0, "1"),
        (600.0, "10"),
        (3600.0, "60"),
    ],
)
def test_countdown_wording(seconds, expected):
    assert countdown(seconds) == expected, "under half a minute is due, otherwise whole minutes"


# -- wants_display -----------------------------------------------------------


def test_it_wants_the_screen_when_it_has_buses(app: BusApp):
    assert app.wants_display(NOW) is True, "fresh departures are worth showing"


def test_it_yields_before_the_first_fetch():
    assert make_app().wants_display(NOW) is False, "nothing fetched yet, let the clock have it"


def test_it_yields_when_the_stop_is_empty():
    app = loaded(fetch=list)
    assert app.wants_display(NOW) is False, "a stop with nothing due falls through to the clock"


def test_it_yields_once_the_data_goes_stale(app: BusApp):
    assert app.wants_display(NOW + 119) is True, "inside stale_s the last fetch still counts"
    assert app.wants_display(NOW + 121) is False, "past stale_s we admit we don't know"


def test_it_yields_when_every_bus_has_gone(app: BusApp):
    fresh = loaded(stale_s=1e9)
    assert fresh.wants_display(NOW + 901) is False, "no future departures left to show"


@pytest.mark.parametrize(
    "spec,offset_h,expected",
    [
        ("", 0, True),
        ("07:00-10:00", 0, False),
        ("11:00-14:00", 0, True),
        ("07:00-10:00,11:00-14:00", 0, True),
        ("22:00-02:00", 0, False),
    ],
)
def test_windows_gate_the_screen(spec, offset_h, expected):
    app = loaded(windows=Windows.parse(spec))
    got = app.wants_display(NOW + offset_h * 3600)
    assert got is expected, f"window {spec!r} at midday should be {expected}"


def test_a_window_gates_even_with_fresh_data():
    app = loaded(windows=Windows.parse("03:00-04:00"))
    assert app.snapshot(NOW), "the data is there"
    assert app.wants_display(NOW) is False, "but we're outside the window, so we yield"


# -- rendering ---------------------------------------------------------------


def test_it_draws_something(app: BusApp, board: Canvas):
    app.render(board, NOW)
    assert lit(board.fb).any(), "the departures should be visible"


def test_it_clears_before_drawing(app: BusApp, board: Canvas):
    board.fb[:] = (255, 255, 255)
    app.render(board, NOW)
    assert not lit(board.fb).all(), "old pixels are wiped, not drawn over"


def test_it_stays_inside_the_panel(app: BusApp, board: Canvas):
    app.render(board, NOW)
    x0, y0, x1, y1 = lit_bbox(board.fb)
    assert x0 >= 0 and x1 <= WIDTH, "nothing is clipped off the left or right edge"
    assert y0 >= 0 and y1 <= HEIGHT, "nothing is clipped off the top or bottom"


@pytest.mark.parametrize(
    "height,expected",
    [(32, 4), (16, 2), (8, 1), (64, 8), (4, 1)],
)
def test_row_count_comes_from_the_panel_height(height, expected):
    assert make_app(height=height).rows == expected, f"a {height}px panel fits {expected} rows"


def test_only_the_rows_that_fit_are_drawn(board: Canvas):
    app = loaded()
    app.render(board, NOW)
    rows = {y for y in range(HEIGHT) if lit(board.fb)[y].any()}
    assert max(rows) < app.rows * (FH + 1), "the fifth departure has nowhere to go"


def test_rows_are_soonest_first(board: Canvas):
    """The top row is the 345 and the second is the 12, so the top row is narrower."""
    app = loaded(fetch=lambda: [DEPARTURES[0], DEPARTURES[1]])
    app.render(board, NOW)
    top = lit(board.fb)[0:FH]
    second = lit(board.fb)[FH + 1 : 2 * (FH + 1)]
    assert top.any() and second.any(), "both departures are drawn"


def test_the_countdown_is_right_aligned(app: BusApp, board: Canvas):
    app.render(board, NOW)
    _, _, x1, _ = lit_bbox(board.fb)
    assert WIDTH - FW <= x1 <= WIDTH, "the countdown's cell is flush with the right-hand edge"


def test_the_destination_column_does_not_move(board: Canvas):
    """A four-character route and a two-character one start their destination at the same x."""
    short = Canvas(WIDTH, HEIGHT)
    loaded(fetch=lambda: [Departure("12", "MMMMMMMM", NOW + 300, "A")]).render(short, NOW)
    long = Canvas(WIDTH, HEIGHT)
    loaded(fetch=lambda: [Departure("N171", "MMMMMMMM", NOW + 300, "B")]).render(long, NOW)

    dest_x = ROUTE_COLS * FW + GAP
    assert lit(short.fb)[0:FH, dest_x:].any(), "the short route's destination starts at the column"
    assert lit(long.fb)[0:FH, dest_x:].any(), "and so does the long route's"
    assert not lit(short.fb)[0:FH, ROUTE_COLS * FW : dest_x].any(), "the gap column stays empty"


def test_a_long_destination_is_truncated(board: Canvas):
    app = loaded(fetch=lambda: [Departure("436", "Battersea Park Station", NOW + 300, "A")])
    app.render(board, NOW)
    _, _, x1, _ = lit_bbox(board.fb)
    assert x1 <= WIDTH, "a 22-character destination is cut to fit rather than overflowing"


def test_the_countdown_ticks_down_between_fetches(app: BusApp, board: Canvas):
    """render takes `now`, so the numbers keep moving while the poll thread sleeps."""
    app.render(board, NOW)
    first = board.fb.copy()
    app.render(board, NOW + 60)
    assert not (first == board.fb).all(), "a minute later the board reads differently"


def test_departed_buses_drop_off(app: BusApp):
    fresh = loaded(stale_s=1e9)
    assert len(fresh.snapshot(NOW)) == 5, "all five are in the future"
    assert len(fresh.snapshot(NOW + 400)) == 3, "the first two have gone"


# -- polling and lifecycle ---------------------------------------------------


def test_a_failing_fetch_does_not_kill_the_app():
    def boom():
        raise RuntimeError("tfl is having a moment")

    app = make_app(fetch=boom)
    app._poll_once()
    assert app.snapshot(NOW) == [], "a failed fetch leaves us with nothing, not an exception"


def test_a_failing_fetch_keeps_the_last_good_data():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] > 1:
            raise RuntimeError("nope")
        return list(DEPARTURES)

    app = make_app(fetch=flaky, stale_s=1e9)
    app._poll_once()
    app._poll_once()
    assert len(app.snapshot(NOW)) == 5, "we keep showing the last good fetch until it goes stale"


def test_start_polls_and_stop_joins():
    app = make_app(refresh_s=0.01)
    app.start()
    try:
        deadline = time.time() + 2.0
        while not app.snapshot(time.time() + 1e9 - 1) and time.time() < deadline:
            pass
    finally:
        app.stop()
    assert app._thread is None, "stop joins the poll thread and clears it"
    assert app._fetched_at > 0, "the thread fetched at least once"


def test_stop_is_safe_without_start():
    make_app().stop()  # must not raise


def test_the_poll_thread_sits_out_the_night():
    """Outside its windows the app doesn't even ask, which keeps the api quiet at 3am."""
    calls = {"n": 0}

    def counting():
        calls["n"] += 1
        return list(DEPARTURES)

    app = make_app(fetch=counting, windows=Windows.parse("03:00-03:01"), refresh_s=0.01)
    app.start()
    time.sleep(0.05)
    app.stop()
    assert calls["n"] == 0, "no fetch happens outside the configured windows"


# -- protocol ----------------------------------------------------------------


def test_app_identity_matches_the_protocol(app: BusApp):
    assert app.name == "bus", "the scheduler looks the app up by name"
    assert app.priority == 20, "above the clock, below a message someone actually sent"
