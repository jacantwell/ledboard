import io
import json
import time
import urllib.parse
import urllib.request
from datetime import UTC, datetime

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from ledboard.gcal import API, SCOPE, TOKEN_URL, CalendarClient, Event, parse_events

CAL_ID = "family@group.calendar.google.com"
EMAIL = "ledboard@home-dash.iam.gserviceaccount.com"
TOKEN = "ya29.fake-token"

# Midday local time, so a dateless all-day event can't straddle a day boundary.
NOW = time.mktime((2026, 9, 25, 12, 0, 0, 0, 1, -1))


def local(day: int, hour: int = 0, minute: int = 0) -> float:
    """Epoch for a local wall-clock time in September 2026."""
    return time.mktime((2026, 9, day, hour, minute, 0, 0, 1, -1))


def utc(day: int, hour: int, minute: int = 0) -> float:
    return datetime(2026, 9, day, hour, minute, tzinfo=UTC).timestamp()


def item(summary: str | None, start: dict, end: dict, **extra) -> dict:
    """One row shaped like the real Calendar API payload, extra fields and all."""
    row = {
        "kind": "calendar#event",
        "id": f"id-{summary}",
        "status": "confirmed",
        "htmlLink": "https://www.google.com/calendar/event?eid=abc",
        "start": start,
        "end": end,
        **extra,
    }
    if summary is not None:
        row["summary"] = summary
    return row


def timed(summary: str | None, start: str, end: str, **extra) -> dict:
    return item(summary, {"dateTime": start}, {"dateTime": end}, **extra)


# Deliberately out of order, so the sort is actually exercised.
PAYLOAD = {
    "kind": "calendar#events",
    "summary": "Family",
    "items": [
        timed("Dinner", "2026-09-26T19:30:00Z", "2026-09-26T21:00:00Z"),
        timed("Dentist", "2026-09-25T15:00:00Z", "2026-09-25T15:30:00Z"),
        item("Bins", {"date": "2026-09-28"}, {"date": "2026-09-29"}),
    ],
}


class FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# -- parse_events ------------------------------------------------------------


def test_events_come_back_soonest_first():
    got = [e.title for e in parse_events(PAYLOAD)]
    assert got == ["Dentist", "Dinner", "Bins"], "sorted by start, whatever order the api used"


def test_timed_fields_are_mapped():
    first = parse_events(PAYLOAD)[0]
    assert first == Event("Dentist", utc(25, 15), utc(25, 15, 30), False), (
        "title, absolute start and end, and not all-day"
    )


@pytest.mark.parametrize(
    "stamp,expected",
    [
        ("2026-09-25T15:00:00Z", utc(25, 15)),
        ("2026-09-25T16:00:00+01:00", utc(25, 15)),
        ("2026-09-25T10:00:00-05:00", utc(25, 15)),
        ("2026-09-25T15:00:00", local(25, 15)),
    ],
    ids=["zulu", "plus-offset", "minus-offset", "naive-is-local"],
)
def test_date_times_honour_their_offset(stamp, expected):
    (got,) = parse_events({"items": [timed("X", stamp, stamp)]})
    assert got.start == expected, f"{stamp} is the same instant however it's written"


def test_all_day_events_start_at_local_midnight():
    (got,) = parse_events({"items": [item("Bins", {"date": "2026-09-27"}, {"date": "2026-09-28"})]})
    assert got.all_day is True, "a bare date is an all-day event"
    assert (got.start, got.end) == (local(27), local(28)), "both ends are local midnight"


@pytest.mark.parametrize(
    "summary,expected",
    [
        ("Dinner", "Dinner"),
        ("  Dinner  ", "Dinner"),
        ("", "(no title)"),
        ("   ", "(no title)"),
        (None, "(no title)"),
    ],
    ids=["plain", "padded", "empty", "blank", "missing"],
)
def test_titles_are_tidied(summary, expected):
    (got,) = parse_events({"items": [timed(summary, "2026-09-25T15:00:00Z", "2026-09-25T16:00Z")]})
    assert got.title == expected, "whitespace trimmed, untitled events still get a label"


def test_cancelled_events_are_dropped():
    gone = timed("Party", "2026-09-25T13:00:00Z", "2026-09-25T14:00:00Z", status="cancelled")
    got = [e.title for e in parse_events({"items": [*PAYLOAD["items"], gone]})]
    assert "Party" not in got, "a cancelled instance of a recurring event is not shown"
    assert len(got) == 3, "the rest survive"


@pytest.mark.parametrize(
    "row",
    [
        {},
        {"summary": "no times"},
        {"summary": "X", "start": {"dateTime": "2026-09-25T15:00:00Z"}},
        {"summary": "X", "start": {"dateTime": "nope"}, "end": {"dateTime": "nope"}},
        {"summary": "X", "start": {"date": "nope"}, "end": {"date": "nope"}},
        {"summary": "X", "start": {}, "end": {}},
        {"summary": "X", "start": "2026-09-25", "end": "2026-09-26"},
        {"summary": "X", "start": None, "end": None},
        "not a dict",
        None,
    ],
    ids=[
        "empty",
        "no-times",
        "no-end",
        "bad-datetime",
        "bad-date",
        "empty-times",
        "string-times",
        "null-times",
        "string",
        "none",
    ],
)
def test_malformed_items_are_skipped_not_fatal(row):
    got = parse_events({"items": [*PAYLOAD["items"], row]})
    assert len(got) == 3, "one junk event must not take the whole board down"


@pytest.mark.parametrize("payload", [[], "nope", None, 42], ids=["list", "str", "none", "int"])
def test_a_non_object_payload_is_an_error(payload):
    with pytest.raises(ValueError, match="expected an events object"):
        parse_events(payload)


@pytest.mark.parametrize(
    "payload", [{}, {"items": []}, {"items": None}], ids=["no-items", "empty", "null"]
)
def test_an_empty_calendar_is_an_empty_list(payload):
    assert parse_events(payload) == [], "a quiet week is not an error"


# -- CalendarClient ----------------------------------------------------------


@pytest.fixture(scope="module")
def rsa_key() -> rsa.RSAPrivateKey:
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def write_creds(path, key: rsa.RSAPrivateKey, **overrides) -> str:
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    creds = {
        "type": "service_account",
        "project_id": "home-dash",
        "client_email": EMAIL,
        "private_key": pem,
        **overrides,
    }
    creds = {k: v for k, v in creds.items() if v is not None}
    path.write_text(json.dumps(creds))
    return str(path)


@pytest.fixture
def creds(tmp_path, rsa_key) -> str:
    return write_creds(tmp_path / "sa.json", rsa_key)


class Recorder:
    """Stands in for CalendarClient._open: records requests, answers from canned payloads."""

    def __init__(self, token: object = None, events: object = None) -> None:
        self.token = {"access_token": TOKEN, "expires_in": 3600} if token is None else token
        self.events = PAYLOAD if events is None else events
        self.requests: list[urllib.request.Request] = []

    def __call__(self, req: urllib.request.Request) -> object:
        self.requests.append(req)
        return self.token if req.get_method() == "POST" else self.events

    @property
    def token_calls(self) -> list[urllib.request.Request]:
        return [r for r in self.requests if r.get_method() == "POST"]

    @property
    def event_calls(self) -> list[urllib.request.Request]:
        return [r for r in self.requests if r.get_method() == "GET"]


def make_client(creds: str, recorder: Recorder, **kwargs) -> CalendarClient:
    client = CalendarClient(kwargs.pop("calendar_id", CAL_ID), creds, **kwargs)
    client._open = recorder
    return client


@pytest.fixture
def recorder() -> Recorder:
    return Recorder()


def form(req: urllib.request.Request) -> dict[str, str]:
    return {k: v[0] for k, v in urllib.parse.parse_qs(req.data.decode()).items()}


def claims(assertion: str, key: rsa.RSAPrivateKey, audience: str) -> dict:
    """Verify the signature with the public half and hand back the payload."""
    return jwt.decode(
        assertion,
        key.public_key(),
        algorithms=["RS256"],
        audience=audience,
        options={"verify_exp": False, "verify_iat": False},
    )


def test_the_token_request_is_a_jwt_bearer_grant(creds, recorder):
    make_client(creds, recorder).access_token(NOW)
    (req,) = recorder.token_calls
    assert req.full_url == TOKEN_URL, "google's token endpoint by default"
    assert form(req)["grant_type"] == "urn:ietf:params:oauth:grant-type:jwt-bearer", (
        "the service-account flow, no user consent"
    )


def test_the_assertion_is_signed_by_the_service_account(creds, recorder, rsa_key):
    make_client(creds, recorder).access_token(NOW)
    got = claims(form(recorder.token_calls[0])["assertion"], rsa_key, TOKEN_URL)
    assert got == {
        "iss": EMAIL,
        "scope": SCOPE,
        "aud": TOKEN_URL,
        "iat": int(NOW),
        "exp": int(NOW) + 3600,
    }, "read-only scope, issued now, valid for the hour google allows"


@pytest.mark.parametrize(
    "token_uri,expected",
    [
        (None, TOKEN_URL),
        ("", TOKEN_URL),
        ("http://localhost:9999/token", "http://localhost:9999/token"),
    ],
    ids=["missing", "blank", "custom"],
)
def test_the_token_uri_comes_from_the_key_file(tmp_path, rsa_key, recorder, token_uri, expected):
    path = write_creds(tmp_path / "sa.json", rsa_key, token_uri=token_uri)
    make_client(path, recorder).access_token(NOW)
    req = recorder.token_calls[0]
    assert req.full_url == expected, "the key file's token_uri wins, else google's"
    assert claims(form(req)["assertion"], rsa_key, expected)["aud"] == expected, (
        "the audience matches the endpoint it's posted to"
    )


def test_access_token_returns_the_token(creds, recorder):
    got = make_client(creds, recorder).access_token(NOW)
    assert got == TOKEN, "the access_token is handed back"


@pytest.mark.parametrize(
    "token,elapsed,requests",
    [
        ({"access_token": TOKEN, "expires_in": 3600}, 0, 1),
        ({"access_token": TOKEN, "expires_in": 3600}, 3539, 1),
        ({"access_token": TOKEN, "expires_in": 3600}, 3540, 2),
        ({"access_token": TOKEN, "expires_in": 3600}, 7200, 2),
        ({"access_token": TOKEN, "expires_in": 120}, 59, 1),
        ({"access_token": TOKEN, "expires_in": 120}, 60, 2),
        ({"access_token": TOKEN}, 3539, 1),
        ({"access_token": TOKEN}, 3540, 2),
    ],
    ids=[
        "same",
        "just-fresh",
        "minute-left",
        "expired",
        "short-fresh",
        "short-due",
        "default-fresh",
        "default-due",
    ],
)
def test_the_token_is_cached_until_a_minute_before_expiry(creds, token, elapsed, requests):
    rec = Recorder(token=token)
    client = make_client(creds, rec)
    client.access_token(NOW)
    client.access_token(NOW + elapsed)
    assert len(rec.token_calls) == requests, (
        f"{elapsed}s after a {token.get('expires_in', 3600)}s token: {requests} request(s)"
    )


@pytest.mark.parametrize(
    "token",
    [{}, {"error": "invalid_grant"}, ["nope"], "nope"],
    ids=["empty", "error", "list", "string"],
)
def test_a_token_response_without_a_token_is_an_error(creds, token):
    client = make_client(creds, Recorder(token=token))
    with pytest.raises(ValueError, match="no access_token"):
        client.access_token(NOW)


def test_a_failed_token_response_is_not_cached(creds):
    rec = Recorder(token={"error": "invalid_grant"})
    client = make_client(creds, rec)
    with pytest.raises(ValueError):
        client.access_token(NOW)
    rec.token = {"access_token": TOKEN, "expires_in": 3600}
    assert client.access_token(NOW + 1) == TOKEN, "the next call tries again"


def test_a_missing_key_file_is_an_error(tmp_path, recorder):
    client = make_client(str(tmp_path / "nope.json"), recorder)
    with pytest.raises(FileNotFoundError):
        client.access_token(NOW)


def test_fetch_hits_the_events_endpoint(creds, recorder):
    make_client(creds, recorder).fetch(NOW)
    (req,) = recorder.event_calls
    url = urllib.parse.urlsplit(req.full_url)
    assert f"{url.scheme}://{url.netloc}{url.path}" == (
        f"{API}/calendars/family%40group.calendar.google.com/events"
    ), "the calendar id is fully percent-encoded into the path"


def test_fetch_asks_for_upcoming_single_events(creds, recorder):
    make_client(creds, recorder, max_results=4).fetch(NOW)
    url = urllib.parse.urlsplit(recorder.event_calls[0].full_url)
    query = dict(urllib.parse.parse_qsl(url.query))
    assert query == {
        "timeMin": datetime.fromtimestamp(NOW, UTC).isoformat(),
        "singleEvents": "true",
        "orderBy": "startTime",
        "maxResults": "4",
    }, "from now, recurring events expanded, soonest first, capped"


def test_fetch_sends_the_bearer_token(creds, recorder):
    make_client(creds, recorder).fetch(NOW)
    assert recorder.event_calls[0].get_header("Authorization") == f"Bearer {TOKEN}", (
        "the access token authorises the read"
    )


def test_fetch_returns_parsed_events(creds, recorder):
    got = make_client(creds, recorder).fetch(NOW)
    assert [e.title for e in got] == ["Dentist", "Dinner", "Bins"], "parsed and sorted"


def test_fetch_reuses_the_token(creds, recorder):
    client = make_client(creds, recorder)
    client.fetch(NOW)
    client.fetch(NOW + 300)
    assert len(recorder.token_calls) == 1, "one token covers every poll inside its hour"
    assert len(recorder.event_calls) == 2, "but each fetch reads the calendar"


@pytest.mark.parametrize(
    "calendar_id,api_url,expected",
    [
        (f" {CAL_ID} ", API, f"{API}/calendars/family%40group.calendar.google.com/events"),
        ("primary", "http://localhost:9999/", "http://localhost:9999/calendars/primary/events"),
        ("a/b c", API, f"{API}/calendars/a%2Fb%20c/events"),
    ],
    ids=["padded-id", "trailing-slash", "odd-chars"],
)
def test_fetch_url_is_built_safely(creds, recorder, calendar_id, api_url, expected):
    make_client(creds, recorder, calendar_id=calendar_id, api_url=api_url).fetch(NOW)
    assert recorder.event_calls[0].full_url.split("?")[0] == expected, (
        "ids are trimmed and quoted, the base url's trailing slash is handled"
    )


def test_open_decodes_json_and_passes_the_timeout(monkeypatch: pytest.MonkeyPatch):
    seen = {}

    def fake_urlopen(req, timeout=None):
        seen["req"], seen["timeout"] = req, timeout
        return FakeResponse(json.dumps({"ok": True}).encode())

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    req = urllib.request.Request("https://example.invalid/")
    got = CalendarClient(CAL_ID, "unused.json", timeout=2.5)._open(req)
    assert got == {"ok": True}, "the body is parsed as json"
    assert seen == {"req": req, "timeout": 2.5}, "the request goes out with the client's timeout"
