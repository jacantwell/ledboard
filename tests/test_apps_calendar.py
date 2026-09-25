import time

import pytest
from conftest import lit, lit_bbox, lit_colors

from ledboard.apps.calendar import CalendarApp, when
from ledboard.canvas import Canvas
from ledboard.gcal import Event

WIDTH = 128
HEIGHT = 32
FW, FH = 5, 7  # the 5x7 font, two events of two lines each on a 32px panel
AMBER = (255, 140, 0)
DIM = (127, 70, 0)


def local(day: int, hour: int = 0, minute: int = 0, month: int = 9) -> float:
    """Epoch for a local wall-clock time in 2026."""
    return time.mktime((2026, month, day, hour, minute, 0, 0, 1, -1))


# Friday 25 September 2026, midday local time.
NOW = local(25, 12)


def timed(title: str, start: float, hours: float = 1.0) -> Event:
    return Event(title, start, start + hours * 3600, False)


def all_day(title: str, day: int, month: int = 9) -> Event:
    start = local(day, month=month)
    return Event(title, start, start + 86400, True)


EVENTS = [
    timed("Dentist", NOW + 3600),
    timed("Dinner", local(26, 19, 30)),
    all_day("Bins", 28),
    timed("Flight", local(10, 7, 15, month=10)),
]


def make_app(**kwargs) -> CalendarApp:
    kwargs.setdefault("fetch", lambda: list(EVENTS))
    return CalendarApp(kwargs.pop("width", WIDTH), kwargs.pop("height", HEIGHT), **kwargs)


def loaded(**kwargs) -> CalendarApp:
    """An app that fetched at NOW, without starting its thread."""
    app = make_app(**kwargs)
    app._poll_once(NOW)
    return app


@pytest.fixture
def app() -> CalendarApp:
    return loaded()


@pytest.fixture
def board() -> Canvas:
    return Canvas(WIDTH, HEIGHT)


# -- when wording ------------------------------------------------------------


@pytest.mark.parametrize(
    "event,expected",
    [
        (timed("x", local(25, 19, 30)), "Today 19:30"),
        (timed("x", local(25, 0, 5)), "Today 00:05"),
        (timed("x", local(25, 23, 59)), "Today 23:59"),
        (timed("x", local(24, 22)), "Today 22:00"),
        (timed("x", local(26, 0, 0)), "Tmrw 00:00"),
        (timed("x", local(26, 19, 30)), "Tmrw 19:30"),
        (timed("x", local(27, 9)), "Sun 09:00"),
        (timed("x", local(1, 18, month=10)), "Thu 18:00"),
        (timed("x", local(2, 8, month=10)), "Fri 2 Oct 08:00"),
        (timed("x", local(10, 7, 15, month=10)), "Sat 10 Oct 07:15"),
        (all_day("x", 25), "Today"),
        (all_day("x", 24), "Today"),
        (all_day("x", 26), "Tmrw"),
        (all_day("x", 29), "Tue"),
        (all_day("x", 10, month=10), "Sat 10 Oct"),
    ],
    ids=[
        "today",
        "early-today",
        "late-today",
        "started-yesterday",
        "tomorrow-midnight",
        "tomorrow",
        "this-week",
        "six-days",
        "seven-days",
        "far-off",
        "all-day-today",
        "all-day-started",
        "all-day-tomorrow",
        "all-day-this-week",
        "all-day-far-off",
    ],
)
def test_when_wording(event, expected):
    assert when(event, NOW) == expected, "relative day under a week, a real date past it"


@pytest.mark.parametrize("hour", [0, 12, 23], ids=["just-after-midnight", "midday", "late"])
def test_when_counts_calendar_days_not_24h_blocks(hour):
    now = local(25, hour)
    assert when(timed("x", local(26, 1)), now) == "Tmrw 01:00", (
        "tomorrow is tomorrow whatever the time of day"
    )


# -- snapshot ----------------------------------------------------------------


def test_snapshot_is_capped_at_count(app: CalendarApp):
    assert [e.title for e in app.snapshot(NOW)] == ["Dentist", "Dinner"], "the next two by default"


@pytest.mark.parametrize("count,expected", [(1, 1), (2, 2), (3, 3), (4, 4), (10, 4)])
def test_count_is_configurable(count, expected):
    assert len(loaded(count=count).snapshot(NOW)) == expected, f"count={count} keeps {expected}"


@pytest.mark.parametrize(
    "offset_s,expected",
    [
        (0, ["Dentist", "Dinner"]),
        (3600 + 1800, ["Dentist", "Dinner"]),
        (7199, ["Dentist", "Dinner"]),
        (7200, ["Dinner", "Bins"]),
    ],
    ids=["before", "during", "last-second", "finished"],
)
def test_finished_events_drop_off(offset_s, expected):
    app = loaded(stale_s=1e9)
    assert [e.title for e in app.snapshot(NOW + offset_s)] == expected, (
        "an event stays until its end, then the next one moves up"
    )


def test_snapshot_is_empty_before_the_first_fetch():
    assert make_app().snapshot(NOW) == [], "nothing fetched, nothing to show"


@pytest.mark.parametrize(
    "offset_s,fresh", [(0, True), (3600, True), (3601, False)], ids=["now", "edge", "stale"]
)
def test_snapshot_goes_empty_once_stale(app: CalendarApp, offset_s, fresh):
    assert bool(app.snapshot(NOW + offset_s)) is fresh, "past stale_s we admit we don't know"


# -- wants_display -----------------------------------------------------------


def test_it_wants_the_screen_when_there_are_events(app: CalendarApp):
    assert app.wants_display(NOW) is True, "upcoming events are worth showing"


@pytest.mark.parametrize(
    "fetch,at",
    [
        (None, NOW),
        (list, NOW),
        (lambda: list(EVENTS), NOW + 3601),
    ],
    ids=["never-fetched", "empty-calendar", "stale"],
)
def test_it_yields_when_it_has_nothing(fetch, at):
    app = make_app() if fetch is None else loaded(fetch=fetch)
    assert app.wants_display(at) is False, "let the clock have it"


def test_it_yields_once_every_event_is_over():
    app = loaded(stale_s=1e9)
    assert app.wants_display(local(11, month=10)) is False, "the flight has landed, nothing left"


# -- rendering ---------------------------------------------------------------


def test_it_draws_something(app: CalendarApp, board: Canvas):
    app.render(board, NOW)
    assert lit(board.fb).any(), "the events should be visible"


def test_it_clears_before_drawing(app: CalendarApp, board: Canvas):
    board.fb[:] = (255, 255, 255)
    app.render(board, NOW)
    assert not lit(board.fb).all(), "old pixels are wiped, not drawn over"


def test_it_draws_nothing_when_stale(app: CalendarApp, board: Canvas):
    board.fb[:] = (255, 255, 255)
    app.render(board, NOW + 3601)
    assert lit_bbox(board.fb) is None, "stale data renders a blank panel"


def test_it_stays_inside_the_panel(app: CalendarApp, board: Canvas):
    app.render(board, NOW)
    x0, y0, x1, y1 = lit_bbox(board.fb)
    assert x0 >= 0 and x1 <= WIDTH, "nothing is clipped off the left or right edge"
    assert y0 >= 0 and y1 <= HEIGHT, "nothing is clipped off the top or bottom"


@pytest.mark.parametrize(
    "rows,color",
    [
        ((0, FH + 1), DIM),
        ((FH + 1, 2 * (FH + 1)), AMBER),
        ((2 * (FH + 1), 3 * (FH + 1)), DIM),
        ((3 * (FH + 1), 4 * (FH + 1)), AMBER),
    ],
    ids=["first-date", "first-title", "second-date", "second-title"],
)
def test_date_lines_are_dim_and_titles_are_bright(app: CalendarApp, board: Canvas, rows, color):
    app.render(board, NOW)
    y0, y1 = rows
    assert lit_colors(board.fb[y0:y1]) == {color}, f"rows {y0}-{y1} are drawn in {color}"


@pytest.mark.parametrize(
    "color,dim",
    [("#FF8C00", DIM), ("#00ff00", (0, 127, 0)), ("#FFFFFF", (127, 127, 127))],
)
def test_the_date_colour_is_half_the_title_colour(color, dim):
    app = make_app(color=color)
    assert app.date_color == dim, "the date line is the title colour at half brightness"


def test_one_event_leaves_the_bottom_half_blank(board: Canvas):
    loaded(fetch=lambda: [EVENTS[0]]).render(board, NOW)
    assert not lit(board.fb)[2 * (FH + 1) :].any(), "the second slot is empty"


@pytest.mark.parametrize(
    "title,width,same_as",
    [
        ("Dentist appointment", 20, "Dent"),
        ("MMMMMMMMMMMMMMMMMMMMMMMMMMMMMMMM", WIDTH, "M" * (WIDTH // FW)),
    ],
    ids=["narrow", "full-width"],
)
def test_long_titles_are_cut_to_whole_characters(title, width, same_as):
    long, short = Canvas(width, HEIGHT), Canvas(width, HEIGHT)
    at = NOW + 3600
    loaded(width=width, fetch=lambda: [timed(title, at)]).render(long, NOW)
    loaded(width=width, fetch=lambda: [timed(same_as, at)]).render(short, NOW)
    assert (long.fb == short.fb).all(), f"only {width // FW} characters fit on a {width}px panel"


def test_long_date_lines_are_cut_too():
    narrow = Canvas(20, HEIGHT)
    loaded(width=20, fetch=lambda: [EVENTS[3]]).render(narrow, NOW)
    expected = Canvas(20, HEIGHT)
    expected.text(0, 0, "Sat ", DIM, "5x7")
    expected.text(0, FH + 1, "Flig", AMBER, "5x7")
    assert (narrow.fb == expected.fb).all(), "'Sat 10 Oct 07:15' is cut to four characters"


def test_the_board_changes_as_time_passes(app: CalendarApp, board: Canvas):
    """render takes `now`, so the list moves on while the poll thread sleeps."""
    app.render(board, NOW)
    first = board.fb.copy()
    app.render(board, NOW + 7200)
    assert not (first == board.fb).all(), "once the dentist is over the board reads differently"


# -- polling and lifecycle ---------------------------------------------------


def test_a_failing_fetch_does_not_kill_the_app():
    def boom():
        raise RuntimeError("google is having a moment")

    app = make_app(fetch=boom)
    app._poll_once(NOW)
    assert app.snapshot(NOW) == [], "a failed fetch leaves us with nothing, not an exception"


def test_a_failing_fetch_keeps_the_last_good_data():
    calls = {"n": 0}

    def flaky():
        calls["n"] += 1
        if calls["n"] > 1:
            raise RuntimeError("nope")
        return list(EVENTS)

    app = make_app(fetch=flaky)
    app._poll_once(NOW)
    app._poll_once(NOW + 1800)
    assert len(app.snapshot(NOW + 1800)) == 2, "the last good fetch still shows"
    assert app.snapshot(NOW + 3601) == [], "and still goes stale from when it was fetched"


def test_a_good_fetch_replaces_the_old_events():
    batches = iter([list(EVENTS), [timed("Pub", NOW + 600)]])
    app = make_app(fetch=lambda: next(batches))
    app._poll_once(NOW)
    app._poll_once(NOW)
    assert [e.title for e in app.snapshot(NOW)] == ["Pub"], "the new list wins outright"


def test_poll_once_stamps_the_real_time_by_default():
    app = make_app()
    before = time.time()
    app._poll_once()
    assert before <= app._fetched_at <= time.time(), "no `now` means wall-clock time"


def test_start_polls_and_stop_joins():
    app = make_app(refresh_s=0.01)
    app.start()
    try:
        deadline = time.time() + 2.0
        while not app._fetched_at and time.time() < deadline:
            time.sleep(0.001)
    finally:
        app.stop()
    assert app._thread is None, "stop joins the poll thread and clears it"
    assert app._fetched_at > 0, "the thread fetched at least once"


def test_stop_is_safe_without_start():
    make_app().stop()  # must not raise


# -- protocol ----------------------------------------------------------------


def test_app_identity_matches_the_protocol(app: CalendarApp):
    assert app.name == "calendar", "the scheduler looks the app up by name"
    assert app.priority == 15, "below the bus, above the clock"
