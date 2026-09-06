import time

import pytest

from ledboard.schedule import Windows

COMMUTE = "07:00-10:00,17:00-20:00"
OVERNIGHT = "22:00-02:00"


def at(hour: int, minute: int = 0) -> float:
    """Epoch seconds for a local wall-clock time on an arbitrary day."""
    return time.mktime((2026, 1, 1, hour, minute, 0, 0, 1, -1))


# -- parsing -----------------------------------------------------------------


@pytest.mark.parametrize(
    "spec,expected",
    [
        ("", ()),
        ("   ", ()),
        ("07:00-10:00", ((420, 600),)),
        (COMMUTE, ((420, 600), (1020, 1200))),
        (" 07:00 - 10:00 ", ((420, 600),)),
        ("07:00-10:00,,17:00-20:00", ((420, 600), (1020, 1200))),
        (OVERNIGHT, ((1320, 120),)),
        ("00:00-24:00", ((0, 1440),)),
    ],
    ids=["empty", "blank", "one", "two", "spaces", "gap", "overnight", "all-day"],
)
def test_parse_reads_the_spec(spec, expected):
    assert Windows.parse(spec).spans == expected, f"{spec!r} should parse to {expected}"


@pytest.mark.parametrize(
    "spec",
    [
        "07:00",
        "07:00-",
        "-10:00",
        "7-10",
        "25:00-26:00",
        "07:70-10:00",
        "aa:bb-cc:dd",
        "09:00-09:00",
    ],
)
def test_parse_rejects_rubbish(spec):
    with pytest.raises(ValueError):
        Windows.parse(spec)


# -- membership --------------------------------------------------------------


@pytest.mark.parametrize("now", [at(0), at(3, 30), at(12), at(23, 59)])
def test_no_spans_means_always_on(now):
    assert Windows().contains(now) is True, "an app with no windows is never gated"
    assert Windows.parse("").contains(now) is True, "an empty spec is the same as no windows"


@pytest.mark.parametrize(
    "now,expected",
    [
        (at(6, 59), False),
        (at(7, 0), True),
        (at(8, 30), True),
        (at(9, 59), True),
        (at(10, 0), False),
        (at(16, 59), False),
        (at(17, 0), True),
        (at(19, 59), True),
        (at(20, 0), False),
        (at(3), False),
    ],
)
def test_commute_windows(now, expected):
    got = Windows.parse(COMMUTE).contains(now)
    assert got is expected, "spans are half-open: the start minute is in, the end minute is out"


@pytest.mark.parametrize(
    "now,expected",
    [
        (at(21, 59), False),
        (at(22, 0), True),
        (at(23, 30), True),
        (at(0, 0), True),
        (at(1, 59), True),
        (at(2, 0), False),
        (at(12, 0), False),
    ],
)
def test_windows_wrap_past_midnight(now, expected):
    assert Windows.parse(OVERNIGHT).contains(now) is expected, "22:00-02:00 spans the day boundary"


@pytest.mark.parametrize("now", [at(0), at(9, 59), at(23, 59)])
def test_all_day_spec_covers_everything(now):
    assert Windows.parse("00:00-24:00").contains(now) is True, "24:00 is a legal end-of-day"


def test_seconds_are_ignored():
    a = Windows.parse("07:00-10:00")
    assert a.contains(at(9, 59) + 59) is True, "resolution is minutes, not seconds"
