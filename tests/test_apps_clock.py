import time

import pytest
from conftest import lit, lit_bbox, text_box

from ledboard.apps.clock import ClockApp
from ledboard.canvas import Canvas

WIDTH = 128
HEIGHT = 32

# Two consecutive seconds inside the same minute: one even, one odd.
EVEN_SECOND = time.mktime((2026, 1, 1, 12, 30, 10, 0, 1, -1))
ODD_SECOND = EVEN_SECOND + 1


@pytest.fixture
def app() -> ClockApp:
    return ClockApp(WIDTH, HEIGHT)


@pytest.fixture
def board() -> Canvas:
    return Canvas(WIDTH, HEIGHT)


@pytest.mark.parametrize("now", [0.0, EVEN_SECOND, ODD_SECOND, 2e9])
def test_clock_always_wants_the_screen(app: ClockApp, now):
    assert app.wants_display(now) is True, "the clock is the idle app, it always draws"


def test_clock_draws_something(app: ClockApp, board: Canvas):
    app.render(board, EVEN_SECOND)
    assert lit(board.fb).any(), "the time should be visible"


def test_clock_is_centred(app: ClockApp, board: Canvas):
    app.render(board, EVEN_SECOND)
    stamp = time.strftime("%H:%M", time.localtime(EVEN_SECOND))
    box0, box1 = text_box(WIDTH, stamp, "7x13")
    x0, _, x1, _ = lit_bbox(board.fb)
    assert box0 <= x0 and x1 <= box1, "the time stays inside the centred text box"


def test_colon_blinks_between_seconds(app: ClockApp, board: Canvas):
    app.render(board, EVEN_SECOND)
    with_colon = board.fb.copy()
    board.clear()
    app.render(board, ODD_SECOND)
    without_colon = board.fb.copy()

    assert not (with_colon == without_colon).all(), "the two frames should differ"
    assert lit(with_colon).sum() > lit(without_colon).sum(), "the colon adds lit pixels"


def test_clock_clears_before_drawing(app: ClockApp, board: Canvas):
    board.fb[:] = (255, 255, 255)
    app.render(board, EVEN_SECOND)
    assert not lit(board.fb).all(), "old pixels are wiped, not drawn over"


def test_app_identity_matches_the_protocol(app: ClockApp):
    assert app.name == "clock", "the scheduler looks the app up by name"
    assert app.priority == 0, "the clock yields to everything else"
