import pytest
from conftest import lit, lit_bbox, lit_colors, text_box

from ledboard.apps.text import TextApp
from ledboard.canvas import Canvas, text_width

WIDTH = 64
HEIGHT = 32
PPS = 40.0
RED = (255, 0, 0)
GREEN = (0, 255, 0)
T0 = 1000.0


def make_app(**kwargs) -> TextApp:
    kwargs.setdefault("dwell_s", 2.0)
    kwargs.setdefault("scroll_pps", PPS)
    return TextApp(WIDTH, HEIGHT, **kwargs)


@pytest.fixture
def app() -> TextApp:
    return make_app()


@pytest.fixture
def board() -> Canvas:
    return Canvas(WIDTH, HEIGHT)


def long_text(chars: int = 20) -> str:
    """A string wider than the board. 'H' lights its leftmost column, so x is measurable."""
    return "H" * chars


@pytest.mark.parametrize("count,expected", [(1, 1), (2, 2), (3, 3)])
def test_submit_returns_the_queue_position(app: TextApp, count, expected):
    for _ in range(count - 1):
        app.submit("x")
    assert app.submit("x") == expected, "position counts the messages waiting"


def test_wants_display_only_while_something_is_pending(app: TextApp):
    assert app.wants_display(T0) is False, "an empty queue does not want the screen"
    app.submit("hi")
    assert app.wants_display(T0) is True, "a queued message wants the screen"


def test_pending_counts_the_current_message_and_the_queue(app: TextApp, board: Canvas):
    app.submit("one")
    app.submit("two")
    assert app.pending == 2, "both queued messages count"
    app.render(board, T0)
    assert app.pending == 2, "the showing message still counts"


def test_clear_empties_the_queue_and_the_current_message(app: TextApp, board: Canvas):
    app.submit("one")
    app.submit("two")
    app.render(board, T0)
    app.clear()
    assert app.pending == 0, "nothing is left"
    assert app.wants_display(T0) is False, "and the app gives up the screen"


def test_stop_clears_pending_messages(app: TextApp):
    app.submit("one")
    app.stop()
    assert app.pending == 0, "stopping drops queued messages"


def test_render_with_nothing_queued_blanks_the_canvas(app: TextApp, board: Canvas):
    board.fb[:] = 255
    app.render(board, T0)
    assert not lit(board.fb).any(), "an idle text app leaves a black frame"


@pytest.mark.parametrize("text", ["hi", "hello", "short one"])
def test_short_text_is_centred(app: TextApp, board: Canvas, text):
    app.submit(text, RED)
    app.render(board, T0)

    box0, box1 = text_box(WIDTH, text)
    assert abs(box0 - (WIDTH - box1)) <= 1, "the text box sits in the middle"
    x0, _, x1, _ = lit_bbox(board.fb)
    assert box0 <= x0 and x1 <= box1, "the glyphs stay inside the centred text box"


@pytest.mark.parametrize("dwell", [0.5, 2.0, 5.0])
def test_short_text_is_held_for_the_dwell_then_released(board: Canvas, dwell):
    app = make_app(dwell_s=dwell)
    app.submit("hi")

    app.render(board, T0)
    app.render(board, T0 + dwell - 0.01)
    assert app.wants_display(T0) is True, "the message is still up just before the dwell ends"

    app.render(board, T0 + dwell)
    assert app.wants_display(T0) is False, "the message is dropped once the dwell elapses"


@pytest.mark.parametrize("elapsed", [0.5, 0.8, 1.0, 1.2])
def test_long_text_scrolls_in_from_the_right(app: TextApp, board: Canvas, elapsed):
    app.submit(long_text(), RED)
    app.render(board, T0)

    board.clear()
    app.render(board, T0 + elapsed)
    expected_x = round(WIDTH - elapsed * PPS)
    assert lit_bbox(board.fb)[0] == expected_x, f"the text should sit at x={expected_x}"


def test_long_text_x_decreases_over_time(app: TextApp, board: Canvas):
    app.submit(long_text(), RED)
    app.render(board, T0)

    lefts = []
    for elapsed in (0.4, 0.6, 0.8, 1.0):
        board.clear()
        app.render(board, T0 + elapsed)
        lefts.append(lit_bbox(board.fb)[0])
    assert lefts == sorted(lefts, reverse=True), f"x should only decrease, got {lefts}"
    assert len(set(lefts)) == len(lefts), "x should actually move between samples"


@pytest.mark.parametrize("chars", [15, 20, 30])
def test_long_text_finishes_once_it_is_off_the_left_edge(board: Canvas, chars):
    app = make_app()
    text = long_text(chars)
    app.submit(text)
    app.render(board, T0)

    duration = (WIDTH + text_width(text)) / PPS
    app.render(board, T0 + duration - 0.1)
    assert app.pending == 1, f"still scrolling just before {duration:.2f}s"

    app.render(board, T0 + duration + 0.1)
    assert app.pending == 0, f"finished just after {duration:.2f}s"


def test_messages_are_shown_in_submission_order(app: TextApp, board: Canvas):
    app.submit("aaa", RED)
    app.submit("bbb", GREEN)

    app.render(board, T0)
    assert lit_colors(board.fb) == {RED}, "the first message shows first"

    app.render(board, T0 + app.dwell_s)
    board.clear()
    app.render(board, T0 + app.dwell_s + 0.1)
    assert lit_colors(board.fb) == {GREEN}, "the second message follows"


@pytest.mark.parametrize(
    "color,expected", [("#ff0000", RED), ("0f0", GREEN), ((1, 2, 3), (1, 2, 3))]
)
def test_submitted_colour_is_used(app: TextApp, board: Canvas, color, expected):
    app.submit("hi", color)
    app.render(board, T0)
    assert lit_colors(board.fb) == {expected}, "every lit pixel uses the submitted colour"


def test_default_colour_comes_from_the_constructor(board: Canvas):
    app = make_app(default_color="#00ff00")
    app.submit("hi")
    app.render(board, T0)
    assert lit_colors(board.fb) == {GREEN}, "no colour given means the app default"


def test_invalid_colour_is_rejected_at_submit_time(app: TextApp):
    with pytest.raises(ValueError):
        app.submit("hi", "not-a-colour")


def test_app_identity_matches_the_protocol(app: TextApp):
    assert app.name == "text", "the scheduler looks the app up by name"
    assert app.priority == 50, "text outranks the clock"


# -- duration ---------------------------------------------------------------


@pytest.mark.parametrize("duration", [0.5, 3.0, 10.0])
def test_short_text_with_a_duration_ignores_the_dwell(board: Canvas, duration):
    app = make_app(dwell_s=2.0)
    app.submit("hi", duration_s=duration)

    app.render(board, T0)
    app.render(board, T0 + duration - 0.01)
    assert app.pending == 1, "the message is still up just before its duration ends"

    app.render(board, T0 + duration)
    assert app.pending == 0, "and dropped once the chosen duration elapses"


@pytest.mark.parametrize("duration", [3.0, 30.0])
def test_long_text_with_a_duration_keeps_scrolling_until_it_elapses(board: Canvas, duration):
    app = make_app()
    text = long_text()
    one_pass = (WIDTH + text_width(text)) / PPS
    app.submit(text, duration_s=duration)
    app.render(board, T0)

    app.render(board, T0 + duration - 0.01)
    assert app.pending == 1, (
        f"still showing at {duration - 0.01:.2f}s (one pass is {one_pass:.2f}s)"
    )

    app.render(board, T0 + duration)
    assert app.pending == 0, "dropped once the duration elapses, mid-scroll or not"


@pytest.mark.parametrize("passes", [1, 2, 3])
def test_long_text_loops_back_in_from_the_right(board: Canvas, passes):
    app = make_app()
    text = long_text()
    period = (WIDTH + text_width(text)) / PPS
    app.submit(text, RED, duration_s=period * 10)
    app.render(board, T0)

    elapsed = passes * period + 0.5
    board.clear()
    app.render(board, T0 + elapsed)
    expected_x = round(WIDTH - 0.5 * PPS)
    assert lit_bbox(board.fb)[0] == expected_x, f"pass {passes + 1} re-enters at x={expected_x}"


def test_long_text_wraps_rather_than_going_blank(board: Canvas):
    app = make_app()
    text = long_text()
    period = (WIDTH + text_width(text)) / PPS
    app.submit(text, RED, duration_s=period * 5)
    app.render(board, T0)

    for elapsed in (period * 0.25, period * 1.25, period * 2.25, period * 3.9):
        board.clear()
        app.render(board, T0 + elapsed)
        assert lit(board.fb).any(), f"pixels lit at {elapsed:.2f}s while looping"


@pytest.mark.parametrize("duration", [0, -1.0])
def test_non_positive_duration_is_rejected_at_submit_time(app: TextApp, duration):
    with pytest.raises(ValueError):
        app.submit("hi", duration_s=duration)
