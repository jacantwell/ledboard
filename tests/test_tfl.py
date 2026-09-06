import io
import json
import urllib.request
from datetime import UTC, datetime

import pytest

from ledboard.tfl import USER_AGENT, ArrivalsClient, Departure, parse_arrivals

SMS = "59378"
NAPTAN = "490012713W"


def stamp(minute: int, second: int = 0) -> str:
    """An expectedArrival string at 17:<minute> UTC on a fixed day."""
    return f"2026-09-06T17:{minute:02d}:{second:02d}Z"


def epoch(minute: int, second: int = 0) -> float:
    return datetime(2026, 9, 6, 17, minute, second, tzinfo=UTC).timestamp()


def arrival(line: str, dest: str, minute: int, vehicle: str) -> dict:
    """One row shaped like the real TfL payload, extra fields and all."""
    return {
        "$type": "Tfl.Api.Presentation.Entities.Prediction, Tfl.Api.Presentation.Entities",
        "lineName": line,
        "destinationName": dest,
        "expectedArrival": stamp(minute),
        "timeToStation": minute * 60,
        "vehicleId": vehicle,
        "stationName": "St Giles Church",
        "platformName": "U",
    }


# Deliberately out of order, the way the API actually returns them.
PAYLOAD = [
    arrival("36", "Queen's Park", 18, "LTZ1001"),
    arrival("345", "South Kensington", 12, "LTZ1002"),
    arrival("N89", "Charlton", 40, "LTZ1003"),
    arrival("12", "Oxford Circus", 15, "LTZ1004"),
]


class FakeResponse(io.BytesIO):
    def __init__(self, body: bytes, url: str) -> None:
        super().__init__(body)
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


# -- parse_arrivals ----------------------------------------------------------


def test_arrivals_come_back_soonest_first():
    got = [d.line for d in parse_arrivals(PAYLOAD)]
    assert got == ["345", "12", "36", "N89"], "the api returns them unordered, we sort by eta"


def test_fields_are_mapped():
    first = parse_arrivals(PAYLOAD)[0]
    assert first == Departure("345", "South Kensington", epoch(12), "LTZ1002"), (
        "line, destination, absolute eta and vehicle are all carried through"
    )


@pytest.mark.parametrize(
    "routes,expected",
    [
        ((), ["345", "12", "36", "N89"]),
        (("12",), ["12"]),
        (("12", "36"), ["12", "36"]),
        (("n89",), ["N89"]),
        ((" 12 ", ""), ["12"]),
        (("999",), []),
    ],
    ids=["all", "one", "two", "case-insensitive", "whitespace", "no-match"],
)
def test_routes_filter_the_list(routes, expected):
    got = [d.line for d in parse_arrivals(PAYLOAD, routes)]
    assert got == expected, f"routes={routes} should keep {expected}"


def test_the_same_bus_twice_keeps_the_earlier_prediction():
    twice = [*PAYLOAD, arrival("36", "Queen's Park", 17, "LTZ1001")]
    got = parse_arrivals(twice)
    assert len(got) == 4, "a repeated vehicleId is one bus, not two"
    assert next(d for d in got if d.vehicle_id == "LTZ1001").eta == epoch(17), (
        "the earlier of the two predictions wins"
    )


@pytest.mark.parametrize(
    "row",
    [
        {},
        {"lineName": "12"},
        {"lineName": "12", "destinationName": "X", "vehicleId": "V", "expectedArrival": "nope"},
        {"lineName": "12", "destinationName": "X", "vehicleId": "V", "expectedArrival": None},
        "not a dict",
        None,
    ],
    ids=["empty", "partial", "bad-date", "null-date", "string", "none"],
)
def test_malformed_rows_are_skipped_not_fatal(row):
    got = parse_arrivals([*PAYLOAD, row])
    assert len(got) == 4, "one junk row must not take the whole board down"


def test_a_non_list_payload_is_an_error():
    with pytest.raises(ValueError, match="expected a list"):
        parse_arrivals({"message": "rate limited"})


def test_an_empty_payload_is_an_empty_list():
    assert parse_arrivals([]) == [], "a stop with nothing due is not an error"


# -- ArrivalsClient ----------------------------------------------------------


@pytest.fixture
def calls(monkeypatch: pytest.MonkeyPatch) -> list[urllib.request.Request]:
    """Record every request and answer it from the fixtures above."""
    seen: list[urllib.request.Request] = []

    def fake_urlopen(req, timeout=None):
        seen.append(req)
        if "/Sms/" in req.full_url:
            body = json.dumps({"naptanId": "490G00012713", "smsCode": SMS}).encode()
            return FakeResponse(body, f"https://api.tfl.gov.uk/StopPoint/{NAPTAN}")
        return FakeResponse(json.dumps(PAYLOAD).encode(), req.full_url)

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    return seen


def test_fetch_sends_a_user_agent(calls):
    ArrivalsClient(NAPTAN).fetch()
    assert calls[0].get_header("User-agent") == USER_AGENT, "tfl 403s the default urllib agent"


def test_fetch_hits_the_arrivals_endpoint(calls):
    ArrivalsClient(NAPTAN).fetch()
    assert calls[0].full_url == f"https://api.tfl.gov.uk/StopPoint/{NAPTAN}/Arrivals", (
        "a naptan id is used as-is"
    )


def test_fetch_returns_parsed_departures(calls):
    got = ArrivalsClient(NAPTAN, routes=("12", "36")).fetch()
    assert [d.line for d in got] == ["12", "36"], "the client applies its own route filter"


def test_an_sms_code_resolves_via_the_redirect(calls):
    client = ArrivalsClient(SMS)
    assert client.naptan_id() == NAPTAN, (
        "the body's naptanId is the stop pair and has no arrivals; the redirect target is the stop"
    )
    assert calls[0].full_url == f"https://api.tfl.gov.uk/StopPoint/Sms/{SMS}", "sms lookup first"


def test_the_sms_lookup_happens_once(calls):
    client = ArrivalsClient(SMS)
    client.fetch()
    client.fetch()
    lookups = [r for r in calls if "/Sms/" in r.full_url]
    assert len(lookups) == 1, "the resolved naptan id is cached for the life of the client"
    assert len(calls) == 3, "one lookup plus one arrivals call per fetch"


@pytest.mark.parametrize("stop_id", [NAPTAN, f" {NAPTAN} "])
def test_a_naptan_id_needs_no_lookup(calls, stop_id):
    ArrivalsClient(stop_id).fetch()
    assert not [r for r in calls if "/Sms/" in r.full_url], "only all-digit ids are sms codes"


def test_an_api_key_is_appended_when_configured(calls):
    ArrivalsClient(NAPTAN, api_key="s3cret").fetch()
    assert calls[0].full_url.endswith("/Arrivals?app_key=s3cret"), "the key raises the rate limit"


def test_no_api_key_means_no_query_string(calls):
    ArrivalsClient(NAPTAN).fetch()
    assert "?" not in calls[0].full_url, "unauthenticated is fine at one poll per 30s"


def test_the_base_url_can_be_pointed_elsewhere(calls):
    ArrivalsClient(NAPTAN, base_url="http://localhost:9999/").fetch()
    assert calls[0].full_url.startswith("http://localhost:9999/StopPoint/"), (
        "the trailing slash is handled"
    )
