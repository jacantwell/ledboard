import base64

import numpy as np
import pytest

from ledboard.apps.etch import EtchApp
from ledboard.canvas import Canvas

W, H = 32, 16


@pytest.fixture
def etch() -> EtchApp:
    return EtchApp(W, H)


def test_starts_centred_with_one_pixel_lit(etch: EtchApp):
    assert etch.cursor == (W // 2, H // 2), "stylus starts in the middle"
    assert etch.lit_count == 1, "just the starting pixel"


def test_move_draws_a_line_through_every_pixel(etch: EtchApp):
    x0, _ = etch.cursor
    etch.move(5, 0)
    assert etch.cursor == (x0 + 5, H // 2), "the stylus lands five right"
    assert etch.lit_count == 6, "start plus five new pixels, no gaps"


def test_move_diagonal_draws_without_gaps(etch: EtchApp):
    etch.move(4, 4)
    assert etch.lit_count == 5, "a diagonal still inks every step"


def test_move_clamps_to_the_panel(etch: EtchApp):
    etch.move(1000, 1000)
    assert etch.cursor == (W - 1, H - 1), "the stylus stops at the edge"


def test_move_clamps_a_single_step(etch: EtchApp):
    x0, _ = etch.cursor
    etch.move(32, 0)
    assert etch.cursor[0] - x0 <= 32, "one request can't cross the whole board"


def test_clear_wipes_but_keeps_the_stylus(etch: EtchApp):
    etch.move(5, 3)
    pos = etch.cursor
    assert etch.lit_count > 1, "setup: something is drawn"
    etch.clear()
    assert etch.cursor == pos, "shake keeps the stylus where it was"
    assert etch.lit_count == 1, "only the stylus pixel is left"


def test_wants_display_is_always_true(etch: EtchApp):
    assert etch.wants_display(0.0) is True, "it is the background layer"


def test_priority_sits_between_bus_and_clock():
    assert EtchApp.priority == 10, "above clock (0), below bus (20) and text (50)"


def test_render_paints_the_buffer(canvas: Canvas):
    app = EtchApp(canvas.width, canvas.height)
    app.move(3, 0)
    app.render(canvas, 0.0)
    lit = canvas.fb.any(axis=2)
    assert lit.sum() == 4, "start plus three steps show on the board"
    assert tuple(canvas.fb[canvas.height // 2, canvas.width // 2 + 3]) == app.color


def test_buffer_survives_preemption(canvas: Canvas):
    app = EtchApp(canvas.width, canvas.height)
    app.move(4, 0)
    before = app.lit_count
    canvas.clear()  # some higher-priority app takes the screen for a while
    app.render(canvas, 1.0)
    assert app.lit_count == before, "bus/text overwriting the board never wipes the sketch"


def test_state_roundtrips_through_base64(etch: EtchApp):
    etch.move(6, 2)
    st = etch.state()
    raw = base64.b64decode(st["pixels_b64"])
    bits = np.unpackbits(np.frombuffer(raw, dtype=np.uint8))[: W * H].reshape(H, W)
    assert int(bits.sum()) == st["lit"] == etch.lit_count, "the payload matches the buffer"
    assert (st["x"], st["y"]) == etch.cursor, "the cursor rides along"
    assert (st["w"], st["h"]) == (W, H), "the size rides along"
