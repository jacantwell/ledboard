"""TfL Unified API arrivals for one bus stop. Stdlib only, no key needed at one poll per 30s."""

import json
import logging
import urllib.parse
import urllib.request
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from ledboard import __version__

BASE = "https://api.tfl.gov.uk"

# TfL 403s the default urllib User-Agent. This header is not optional.
USER_AGENT = f"ledboard/{__version__} (+https://github.com/jacantwell/ledboard)"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Departure:
    line: str
    destination: str
    eta: float  # epoch seconds, so the countdown keeps ticking between fetches
    vehicle_id: str


def _eta(stamp: object) -> float:
    return datetime.fromisoformat(str(stamp).replace("Z", "+00:00")).timestamp()


def parse_arrivals(payload: object, routes: Sequence[str] = ()) -> list[Departure]:
    """Filter by route, dedupe by vehicle, sort soonest first. TfL returns them unordered."""
    if not isinstance(payload, list):
        raise ValueError(f"expected a list of arrivals, got {type(payload).__name__}")
    wanted = {r.strip().upper() for r in routes if r.strip()}
    seen: dict[str, Departure] = {}
    for row in payload:
        try:
            line = str(row["lineName"])
            dep = Departure(
                line=line,
                destination=str(row["destinationName"]),
                eta=_eta(row["expectedArrival"]),
                vehicle_id=str(row["vehicleId"]),
            )
        except (TypeError, KeyError, ValueError):
            log.debug("skipping malformed arrival %r", row)
            continue
        if wanted and line.upper() not in wanted:
            continue
        # Same bus can appear twice; keep the earlier prediction.
        if dep.vehicle_id not in seen or dep.eta < seen[dep.vehicle_id].eta:
            seen[dep.vehicle_id] = dep
    return sorted(seen.values(), key=lambda d: d.eta)


class ArrivalsClient:
    """Live arrivals for one stop. `stop_id` is a naptan id or the 5-digit code on the pole."""

    def __init__(
        self,
        stop_id: str,
        routes: Sequence[str] = (),
        api_key: str = "",
        base_url: str = BASE,
        timeout: float = 5.0,
    ) -> None:
        self.stop_id = stop_id.strip()
        self.routes = tuple(routes)
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._naptan: str | None = None

    def _get(self, path: str) -> tuple[object, str]:
        """GET a path under the API. Returns the decoded body and the final (post-redirect) URL."""
        url = f"{self.base_url}{path}"
        if self.api_key:
            url += f"?{urllib.parse.urlencode({'app_key': self.api_key})}"
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.load(resp), resp.url

    def naptan_id(self) -> str:
        """Resolve an SMS code to a naptan id, once. The body's naptanId is the stop *pair*,
        which has no arrivals of its own — the redirect target is the stop we want."""
        if self._naptan is None:
            if self.stop_id.isdigit():
                _, final = self._get(f"/StopPoint/Sms/{self.stop_id}")
                self._naptan = final.split("?")[0].rstrip("/").rsplit("/", 1)[-1]
                log.info("stop %s resolves to naptan %s", self.stop_id, self._naptan)
            else:
                self._naptan = self.stop_id
        return self._naptan

    def fetch(self) -> list[Departure]:
        payload, _ = self._get(f"/StopPoint/{self.naptan_id()}/Arrivals")
        return parse_arrivals(payload, self.routes)
