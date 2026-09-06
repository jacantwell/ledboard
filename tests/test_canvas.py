import numpy as np
import pytest
from conftest import lit, lit_bbox, lit_colors, text_box

from ledboard import fonts
from ledboard.canvas import AMBER, BLACK, Canvas, parse_color, text_mask, text_width

RED = (255, 0, 0)


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("#ff8c00", (255, 140, 0)),
        ("ff8c00", (255, 140, 0)),
        ("#FFF", (255, 255, 255)),
        ("f00", (255, 0, 0)),
        ("#000000", (0, 0, 0)),
        ((1, 2, 3), (1, 2, 3)),
        (None, AMBER),
    ],
)
def test_parse_color_accepts_hex_tuples_and_none(raw, expected):
    assert parse_color(raw) == expected, f"{raw!r} should parse to {expected}"


def test_parse_color_uses_the_given_default_for_none():
    assert parse_color(None, default=RED) == RED, "None should fall back to the default"


@pytest.mark.parametrize("raw", ["", "#", "12345", "#1234567", "nope", "#gggggg"])
def test_parse_color_rejects_bad_hex(raw):
    with pytest.raises(ValueError):
        parse_color(raw)


@pytest.mark.parametrize("font", fonts.NAMES)
@pytest.mark.parametrize("text", ["a", "hi", "hello", "hello world"])
def test_text_width_is_cell_width_times_length(font, text):
    cell_w, _ = fonts.size(font)
    expected = cell_w * len(text)
    assert text_width(text, font) == expected, f"{font} is monospace {cell_w}px per char"


def test_text_width_of_empty_string_is_zero():
    assert text_width("") == 0, "empty string has no width"


@pytest.mark.parametrize("font", fonts.NAMES)
def test_text_mask_shape_matches_font_and_width(font):
    mask = text_mask("hello", font)
    cell_w, cell_h = fonts.size(font)
    assert mask.shape == (cell_h, cell_w * len("hello")), "mask is font height by text width"
    assert mask.any(), "some pixels should be lit"


def test_text_draws_one_colour_inside_its_own_box(canvas: Canvas):
    x, y, s, font = 3, 4, "hello", "6x10"
    width = canvas.text(x, y, s, RED, font)

    assert width == text_width(s, font), "text() returns the drawn width"
    assert lit_colors(canvas.fb) == {RED}, "only the requested colour is drawn"
    x0, y0, x1, y1 = lit_bbox(canvas.fb)
    _, fh = fonts.size(font)
    assert x <= x0 and x1 <= x + width, "nothing is drawn left or right of the text box"
    assert y <= y0 and y1 <= y + fh, "nothing is drawn above or below the text box"


def test_text_of_empty_string_draws_nothing(canvas: Canvas):
    assert canvas.text(0, 0, "", RED) == 0, "empty text has zero width"
    assert not lit(canvas.fb).any(), "empty text leaves the canvas black"


@pytest.mark.parametrize("font", fonts.NAMES)
@pytest.mark.parametrize("text", ["hi", "hello", "abcdefgh"])
def test_text_centered_is_symmetric_within_a_pixel(canvas: Canvas, font, text):
    canvas.text_centered(text, RED, font)

    box0, box1 = text_box(canvas.width, text, font)
    left, right = box0, canvas.width - box1
    assert abs(left - right) <= 1, f"expected balanced margins, got {left} and {right}"

    x0, _, x1, _ = lit_bbox(canvas.fb)
    assert box0 <= x0 and x1 <= box1, "the glyphs stay inside the centred text box"
    cell_w, _ = fonts.size(font)
    gap = abs(x0 - (canvas.width - x1))
    assert gap <= cell_w, f"lit pixels sit within one character cell of centre, off by {gap}"


@pytest.mark.parametrize("font", fonts.NAMES)
def test_text_centered_is_vertically_centred(canvas: Canvas, font):
    canvas.text_centered("hi", RED, font)
    _, fh = fonts.size(font)
    y0 = (canvas.height - fh) // 2
    _, top, _, bottom = lit_bbox(canvas.fb)
    assert y0 <= top and bottom <= y0 + fh, "the glyphs stay inside the centred line"


@pytest.mark.parametrize(
    "x,y",
    [(-100, -100), (-5, -3), (0, 0), (120, 28), (200, 0), (0, 100), (500, 500)],
)
def test_blit_mask_clips_instead_of_raising(canvas: Canvas, x, y):
    mask = np.ones((10, 20), dtype=bool)
    canvas.blit_mask(mask, x, y, RED)

    expected_x0, expected_y0 = max(x, 0), max(y, 0)
    expected_x1 = min(x + 20, canvas.width)
    expected_y1 = min(y + 10, canvas.height)
    box = lit_bbox(canvas.fb)
    if expected_x1 <= expected_x0 or expected_y1 <= expected_y0:
        assert box is None, "a mask fully off the canvas lights nothing"
    else:
        assert box == (expected_x0, expected_y0, expected_x1, expected_y1), "clipped to the canvas"


def test_blit_mask_off_canvas_leaves_the_frame_untouched(canvas: Canvas):
    canvas.text(0, 0, "hello", RED)
    before = canvas.fb.copy()
    canvas.blit_mask(np.ones((4, 4), dtype=bool), -50, -50, (0, 255, 0))
    assert np.array_equal(canvas.fb, before), "an off-canvas blit changes nothing"


@pytest.mark.parametrize(
    "x,y,w,h,expected",
    [
        (2, 3, 4, 5, (2, 3, 6, 8)),
        (-2, -2, 4, 4, (0, 0, 2, 2)),
        (6, 6, 10, 10, (6, 6, 8, 8)),
        (-10, 0, 5, 5, None),
        (0, -10, 5, 5, None),
        (100, 100, 5, 5, None),
        (0, 0, 0, 5, None),
    ],
)
def test_rect_clips_to_the_canvas(small_canvas: Canvas, x, y, w, h, expected):
    small_canvas.rect(x, y, w, h, RED)
    assert lit_bbox(small_canvas.fb) == expected, "rect stays inside the canvas"


def test_pixel_ignores_out_of_range_coordinates(small_canvas: Canvas):
    for x, y in [(-1, 0), (0, -1), (8, 0), (0, 8)]:
        small_canvas.pixel(x, y, RED)
    assert lit_bbox(small_canvas.fb) is None, "off-canvas pixels are dropped"
    small_canvas.pixel(7, 7, RED)
    assert tuple(small_canvas.fb[7, 7]) == RED, "in-range pixels are drawn"


@pytest.mark.parametrize("color", [BLACK, RED, (1, 2, 3)])
def test_clear_fills_the_whole_canvas(small_canvas: Canvas, color):
    small_canvas.clear(color)
    assert (small_canvas.fb == np.array(color, dtype=np.uint8)).all(), "clear fills every pixel"
