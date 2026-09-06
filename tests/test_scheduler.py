import threading

import numpy as np
import pytest
from conftest import FakeApp, lit

from ledboard.display.array import ArrayDisplay
from ledboard.display.base import FrameStore
from ledboard.scheduler import Scheduler, brightness_lut


def test_brightness_lut_at_full_is_the_identity():
    assert np.array_equal(brightness_lut(1.0), np.arange(256, dtype=np.uint8)), (
        "1.0 changes nothing"
    )


def test_brightness_lut_at_zero_is_black():
    assert not brightness_lut(0.0).any(), "0.0 blanks every value"


@pytest.mark.parametrize("level", [0.0, 0.1, 0.25, 0.5, 0.75, 1.0])
def test_brightness_lut_is_monotonic_and_starts_at_zero(level):
    lut = brightness_lut(level)
    assert lut[0] == 0, "black stays black"
    assert (np.diff(lut.astype(int)) >= 0).all(), "brighter input is never darker output"


@pytest.mark.parametrize("level,clamped", [(-1.0, 0.0), (2.0, 1.0)])
def test_brightness_lut_clamps_out_of_range_levels(level, clamped):
    assert np.array_equal(brightness_lut(level), brightness_lut(clamped)), "levels clamp to 0..1"


@pytest.mark.parametrize("low,high", [(0.2, 0.5), (0.5, 0.9), (0.9, 1.0)])
def test_brightness_lut_is_ordered_across_levels(low, high):
    assert (brightness_lut(low) <= brightness_lut(high)).all(), "a lower level is never brighter"


@pytest.mark.parametrize(
    "priorities,willing,expected",
    [
        ([10, 50, 0], [True, True, True], "p50"),
        ([10, 50, 0], [True, False, True], "p10"),
        ([10, 50, 0], [False, False, True], "p0"),
        ([10, 50, 0], [False, False, False], None),
        ([90, 90], [False, True], "p90b"),
    ],
)
def test_pick_takes_the_highest_priority_willing_app(display, priorities, willing, expected):
    names = [f"p{p}" for p in priorities]
    if len(set(names)) != len(names):
        names = [f"p{p}{s}" for p, s in zip(priorities, "ab", strict=True)]
    apps = [
        FakeApp(name=n, priority=p, wants=w)
        for n, p, w in zip(names, priorities, willing, strict=True)
    ]
    chosen = Scheduler(display, apps).pick(now=0.0)
    assert (chosen.name if chosen else None) == expected, "highest priority that wants the screen"


def test_tick_renders_shows_and_publishes(display: ArrayDisplay, store: FrameStore):
    app = FakeApp(color=(10, 20, 30))
    sched = Scheduler(display, [app], store)

    before = store.version
    active = sched.tick(now=123.0)

    assert active == "fake", "tick reports the app it rendered"
    assert app.renders == 1 and app.last_now == 123.0, "the app is rendered with the given time"
    assert display.shows == 1, "the frame is pushed to the display exactly once"
    assert (display.frame == np.array((10, 20, 30), dtype=np.uint8)).all(), "the app's pixels"
    assert store.version == before + 1, "the frame store gains a version"
    assert store.active_app == "fake" and store.last_show == 123.0, "the store records the app"
    assert sched.ticks == 1, "tick count increases"


def test_tick_applies_the_brightness_lut(display: ArrayDisplay):
    app = FakeApp(color=(255, 255, 255))
    Scheduler(display, [app], brightness=0.5).tick(now=0.0)
    expected = brightness_lut(0.5)[255]
    assert (display.frame == expected).all(), f"white at half brightness becomes {expected}"


def test_set_brightness_changes_later_ticks(display: ArrayDisplay):
    sched = Scheduler(display, [FakeApp(color=(255, 255, 255))])
    sched.tick(now=0.0)
    assert (display.frame == 255).all(), "full brightness by default"
    sched.set_brightness(0.0)
    sched.tick(now=1.0)
    assert not display.frame.any(), "zero brightness blanks the output"


def test_tick_with_no_willing_app_blanks_the_frame(display: ArrayDisplay, store: FrameStore):
    app = FakeApp(wants=False, color=(255, 0, 0))
    sched = Scheduler(display, [app], store)
    display.frame[:] = 255

    active = sched.tick(now=5.0)

    assert active is None, "nothing is active"
    assert app.renders == 0, "an unwilling app is never rendered"
    assert not lit(display.frame).any(), "the display is blanked"
    assert store.active_app is None, "the store records no active app"


def test_tick_without_a_store_still_shows(display: ArrayDisplay):
    Scheduler(display, [FakeApp()]).tick(now=0.0)
    assert display.shows == 1, "a store is optional"


def test_run_starts_and_stops_every_app(display: ArrayDisplay):
    apps = [FakeApp(name="a", priority=1, wants_for=2), FakeApp(name="b", priority=0, wants=False)]
    sched = Scheduler(display, apps, fps=500, stop_when_idle=True)

    sched.run(threading.Event())

    assert [a.starts for a in apps] == [1, 1], "every app is started"
    assert [a.stops for a in apps] == [1, 1], "every app is stopped"
    assert apps[0].renders == 2, "the willing app renders until it stops wanting the screen"


def test_run_exits_and_blanks_when_idle(display: ArrayDisplay):
    sched = Scheduler(display, [FakeApp(wants=False)], fps=500, stop_when_idle=True)
    display.frame[:] = 255

    sched.run(threading.Event())

    assert display.shows == 0, "an idle board never draws a frame"
    assert not display.frame.any(), "close() blanks the display on the way out"


def test_run_stops_when_the_event_is_set(display: ArrayDisplay):
    stop = threading.Event()
    stop.set()
    app = FakeApp()
    Scheduler(display, [app], fps=500).run(stop)

    assert app.renders == 0, "a pre-set stop event skips the loop"
    assert app.starts == 1 and app.stops == 1, "start/stop still run"


def test_apps_are_sorted_by_priority(display: ArrayDisplay):
    apps = [FakeApp(name="lo", priority=0), FakeApp(name="hi", priority=90)]
    assert [a.name for a in Scheduler(display, apps).apps] == ["hi", "lo"], "highest first"


def test_frame_store_snapshot_returns_the_published_bytes(store: FrameStore):
    fb = np.full((store.height, store.width, 3), 7, dtype=np.uint8)
    store.publish(fb, "text", now=9.0)
    version, data = store.snapshot()
    assert version == 1, "publishing bumps the version"
    assert data == fb.tobytes(), "the snapshot is the published frame"
