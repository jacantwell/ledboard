import pytest
from conftest import lit

from ledboard.apps.testpattern import STEPS, TOTAL
from ledboard.apps.testpattern import TestPatternApp as PatternApp
from ledboard.canvas import Canvas

WIDTH = 128
HEIGHT = 32
T0 = 500.0


@pytest.fixture
def board() -> Canvas:
    return Canvas(WIDTH, HEIGHT)


def test_steps_add_up_to_the_total():
    assert sum(d for _, d in STEPS) == TOTAL, "TOTAL is the sum of the step durations"


@pytest.mark.parametrize(
    "elapsed,expected",
    [
        (0.0, "red"),
        (1.49, "red"),
        (1.5, "green"),
        (2.99, "green"),
        (3.0, "blue"),
        (4.49, "blue"),
        (4.5, "white"),
        (5.99, "white"),
        (6.0, "gradient"),
        (8.99, "gradient"),
        (9.0, "frame"),
        (12.99, "frame"),
        (TOTAL, "frame"),
        (100.0, "frame"),
    ],
)
def test_step_at_boundaries(elapsed, expected):
    assert PatternApp(WIDTH, HEIGHT).step_at(elapsed) == expected, f"{elapsed}s is {expected}"


@pytest.mark.parametrize(
    "elapsed,expected", [(TOTAL, "red"), (TOTAL + 1.6, "green"), (2 * TOTAL + 3.1, "blue")]
)
def test_step_at_wraps_when_looping(elapsed, expected):
    app = PatternApp(WIDTH, HEIGHT, loop=True)
    assert app.step_at(elapsed) == expected, "looping restarts the sequence"


def test_wants_display_before_the_first_render():
    assert PatternApp(WIDTH, HEIGHT).wants_display(T0) is True, "it starts on the first tick"


@pytest.mark.parametrize("elapsed,expected", [(0.0, True), (TOTAL - 0.1, True), (TOTAL, False)])
def test_wants_display_ends_after_one_pass(board: Canvas, elapsed, expected):
    app = PatternApp(WIDTH, HEIGHT)
    app.render(board, T0)
    assert app.wants_display(T0 + elapsed) is expected, f"at {elapsed}s past start"


@pytest.mark.parametrize("elapsed", [0.0, TOTAL, 10 * TOTAL])
def test_looping_never_gives_up_the_screen(board: Canvas, elapsed):
    app = PatternApp(WIDTH, HEIGHT, loop=True)
    app.render(board, T0)
    assert app.wants_display(T0 + elapsed) is True, "loop=True runs forever"


@pytest.mark.parametrize(
    "elapsed,color",
    [
        (0.2, (255, 0, 0)),
        (1.6, (0, 255, 0)),
        (3.2, (0, 0, 255)),
        (4.8, (255, 255, 255)),
    ],
)
def test_solid_steps_fill_the_board(board: Canvas, elapsed, color):
    app = PatternApp(WIDTH, HEIGHT)
    app.render(board, T0)
    app.render(board, T0 + elapsed)
    assert (board.fb == list(color)).all(), f"the whole board should be {color}"


def test_gradient_step_ramps_across_both_axes(board: Canvas):
    app = PatternApp(WIDTH, HEIGHT)
    app.render(board, T0)
    app.render(board, T0 + 7.0)

    assert board.fb[0, 0, 0] < board.fb[0, -1, 0], "red ramps left to right"
    assert board.fb[0, 0, 1] < board.fb[-1, 0, 1], "green ramps top to bottom"
    assert (board.fb[..., 2] == 128).all(), "blue is flat"


@pytest.mark.parametrize(
    "y,x,color,why",
    [
        (0, 5, (255, 0, 0), "top edge is red"),
        (-1, 5, (0, 255, 0), "bottom edge is green"),
        (5, 0, (0, 0, 255), "left edge is blue"),
        (5, -1, (255, 255, 0), "right edge is yellow"),
        (0, 0, (255, 255, 255), "the diagonal wins the top-left corner"),
        (HEIGHT - 1, HEIGHT - 1, (255, 255, 255), "the diagonal runs to the shorter side"),
    ],
)
def test_frame_step_draws_edges_and_a_diagonal(board: Canvas, y, x, color, why):
    app = PatternApp(WIDTH, HEIGHT)
    app.render(board, T0)
    app.render(board, T0 + 10.0)
    assert tuple(board.fb[y, x]) == color, why


def test_frame_step_leaves_the_middle_dark(board: Canvas):
    app = PatternApp(WIDTH, HEIGHT)
    app.render(board, T0)
    app.render(board, T0 + 10.0)
    assert not lit(board.fb[10:20, 60:100]).any(), "the inside of the frame stays black"


def test_app_identity_matches_the_protocol():
    app = PatternApp(WIDTH, HEIGHT)
    assert app.name == "testpattern", "the scheduler looks the app up by name"
    assert app.priority == 90, "the test pattern outranks everything"
