"""Upcoming events on one Google Calendar, read as a service account. Stdlib + pyjwt only."""

import json
import logging
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import UTC, date, datetime

import jwt

SCOPE = "https://www.googleapis.com/auth/calendar.readonly"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API = "https://www.googleapis.com/calendar/v3"

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Event:
    title: str
    start: float  # epoch seconds; local midnight for all-day events
    end: float
    all_day: bool


def _when(field: object) -> tuple[float, bool]:
    """(epoch, all_day) from a Google start/end object."""
    if not isinstance(field, dict):
        raise ValueError(f"expected a start/end object, got {field!r}")
    if "dateTime" in field:
        return datetime.fromisoformat(str(field["dateTime"])).timestamp(), False
    if "date" in field:
        d = date.fromisoformat(str(field["date"]))
        return datetime(d.year, d.month, d.day).timestamp(), True
    raise ValueError(f"start/end has neither dateTime nor date: {field!r}")


def parse_events(payload: object) -> list[Event]:
    """Events from a Calendar API list response, soonest first. Cancelled ones dropped."""
    if not isinstance(payload, dict):
        raise ValueError(f"expected an events object, got {type(payload).__name__}")
    events = []
    for item in payload.get("items") or []:
        try:
            if item.get("status") == "cancelled":
                continue
            start, all_day = _when(item["start"])
            end, _ = _when(item["end"])
        except (AttributeError, TypeError, KeyError, ValueError):
            log.debug("skipping malformed event %r", item)
            continue
        title = str(item.get("summary") or "").strip() or "(no title)"
        events.append(Event(title=title, start=start, end=end, all_day=all_day))
    return sorted(events, key=lambda e: e.start)


class CalendarClient:
    """Reads one calendar that has been shared with the service account in `credentials_path`."""

    def __init__(
        self,
        calendar_id: str,
        credentials_path: str,
        max_results: int = 10,
        api_url: str = API,
        timeout: float = 5.0,
    ) -> None:
        self.calendar_id = calendar_id.strip()
        self.credentials_path = credentials_path
        self.max_results = max_results
        self.api_url = api_url.rstrip("/")
        self.timeout = timeout
        self._token = ""
        self._token_expires = 0.0

    def _open(self, req: urllib.request.Request) -> object:
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:
            return json.load(resp)

    def access_token(self, now: float | None = None) -> str:
        """Swap a signed JWT for an access token. Cached until a minute before it expires."""
        now = time.time() if now is None else now
        if self._token and now < self._token_expires - 60:
            return self._token
        with open(self.credentials_path) as f:
            creds = json.load(f)
        token_url = creds.get("token_uri") or TOKEN_URL
        iat = int(now)
        assertion = jwt.encode(
            {
                "iss": creds["client_email"],
                "scope": SCOPE,
                "aud": token_url,
                "iat": iat,
                "exp": iat + 3600,
            },
            creds["private_key"],
            algorithm="RS256",
        )
        body = urllib.parse.urlencode(
            {"grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer", "assertion": assertion}
        ).encode()
        payload = self._open(urllib.request.Request(token_url, data=body, method="POST"))
        if not isinstance(payload, dict) or "access_token" not in payload:
            raise ValueError("token response has no access_token")
        self._token = str(payload["access_token"])
        self._token_expires = now + float(payload.get("expires_in", 3600))
        return self._token

    def fetch(self, now: float | None = None) -> list[Event]:
        now = time.time() if now is None else now
        query = urllib.parse.urlencode(
            {
                "timeMin": datetime.fromtimestamp(now, UTC).isoformat(),
                "singleEvents": "true",  # Google expands recurring events for us
                "orderBy": "startTime",
                "maxResults": self.max_results,
            }
        )
        cal = urllib.parse.quote(self.calendar_id, safe="")
        req = urllib.request.Request(
            f"{self.api_url}/calendars/{cal}/events?{query}",
            headers={"Authorization": f"Bearer {self.access_token(now)}"},
        )
        return parse_events(self._open(req))
