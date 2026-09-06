"""Time-of-day windows. Any app can gate wants_display on one."""

import time
from dataclasses import dataclass

DAY = 24 * 60


def _minutes(hhmm: str) -> int:
    h, _, m = hhmm.strip().partition(":")
    if not m or not h.isdigit() or not m.isdigit():
        raise ValueError(f"bad time {hhmm!r}, want HH:MM")
    hours, mins = int(h), int(m)
    if not (0 <= hours * 60 + mins <= DAY and mins < 60):
        raise ValueError(f"bad time {hhmm!r}, want HH:MM")
    return hours * 60 + mins  # 24:00 is a legal end-of-day, so no wrap here


@dataclass(frozen=True)
class Windows:
    """Local-time spans an app is allowed on screen. No spans = always on."""

    spans: tuple[tuple[int, int], ...] = ()

    @classmethod
    def parse(cls, spec: str) -> "Windows":
        """'07:00-10:00,17:00-20:00' -> Windows. Empty means always. Wraps past midnight."""
        spans = []
        for part in spec.split(","):
            part = part.strip()
            if not part:
                continue
            start, sep, end = part.partition("-")
            if not sep:
                raise ValueError(f"bad window {part!r}, want HH:MM-HH:MM")
            lo, hi = _minutes(start), _minutes(end)
            if lo == hi:
                raise ValueError(f"empty window {part!r}, start and end are the same minute")
            spans.append((lo, hi))
        return cls(tuple(spans))

    def contains(self, now: float) -> bool:
        if not self.spans:
            return True
        t = time.localtime(now)
        m = t.tm_hour * 60 + t.tm_min
        return any(lo <= m < hi if lo < hi else (m >= lo or m < hi) for lo, hi in self.spans)
