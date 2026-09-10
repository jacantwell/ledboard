import time

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient

from ledboard.api import create_api
from ledboard.apps.text import TextApp
from ledboard.auth import AuthError, ClerkVerifier, bearer_token
from ledboard.config import Settings
from ledboard.display.base import FrameStore

ISSUER = "https://clean-dinosaur-8235.clerk.accounts.dev"
PARTIES = ["https://home-dash.vercel.app", "http://localhost:3000"]


class FakeJWKS:
    """Stands in for PyJWKClient: every token is 'signed' by the one key we hold."""

    def __init__(self, public_key) -> None:
        self.public_key = public_key
        self.lookups = 0

    def get_signing_key_from_jwt(self, token: str):
        self.lookups += 1
        return jwt.PyJWK.from_json(
            jwt.algorithms.RSAAlgorithm.to_jwk(self.public_key), algorithm="RS256"
        )


@pytest.fixture(scope="module")
def private_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def other_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture
def jwks(private_key) -> FakeJWKS:
    return FakeJWKS(private_key.public_key())


@pytest.fixture
def verifier(jwks: FakeJWKS) -> ClerkVerifier:
    return ClerkVerifier(ISSUER, PARTIES, jwks_client=jwks)


def mint(key, **overrides) -> str:
    now = int(time.time())
    claims = {
        "sub": "user_123",
        "iss": ISSUER,
        "azp": PARTIES[0],
        "iat": now,
        "nbf": now,
        "exp": now + 60,
    }
    claims.update(overrides)
    claims = {k: v for k, v in claims.items() if v is not None}
    return jwt.encode(claims, key, algorithm="RS256", headers={"kid": "k1"})


def bearer(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}"}


# -- ClerkVerifier ---------------------------------------------------------------


def test_verify_returns_the_claims_of_a_good_token(verifier: ClerkVerifier, private_key):
    claims = verifier.verify(mint(private_key))
    assert claims["sub"] == "user_123", "the user id comes back"
    assert claims["azp"] == PARTIES[0], "so does the minting origin"


@pytest.mark.parametrize(
    "overrides,reason",
    [
        ({"exp": int(time.time()) - 30}, "expired"),
        ({"iss": "https://someone-else.clerk.accounts.dev"}, "wrong issuer"),
        ({"azp": "https://evil.example"}, "azp not allowed"),
        ({"azp": None}, "azp missing while the allow-list is set"),
        ({"sub": None}, "sub missing"),
        ({"exp": None}, "exp missing"),
        ({"iat": None}, "iat missing"),
        ({"nbf": int(time.time()) + 300}, "not yet valid"),
    ],
)
def test_verify_rejects_bad_claims(verifier: ClerkVerifier, private_key, overrides, reason):
    with pytest.raises(AuthError):
        verifier.verify(mint(private_key, **overrides))


def test_verify_rejects_a_token_signed_by_another_key(verifier: ClerkVerifier, other_key):
    with pytest.raises(AuthError, match="invalid token"):
        verifier.verify(mint(other_key))


@pytest.mark.parametrize("token", ["", "not.a.jwt", "a.b.c"])
def test_verify_rejects_garbage(verifier: ClerkVerifier, token):
    with pytest.raises(AuthError):
        verifier.verify(token)


def test_verify_skips_the_azp_check_when_the_allow_list_is_empty(jwks: FakeJWKS, private_key):
    v = ClerkVerifier(ISSUER, [], jwks_client=jwks)
    claims = v.verify(mint(private_key, azp="https://anywhere.example"))
    assert claims["azp"] == "https://anywhere.example", "any azp is fine without an allow-list"


def test_verify_tolerates_a_trailing_slash_on_the_issuer(jwks: FakeJWKS, private_key):
    v = ClerkVerifier(ISSUER + "/", PARTIES, jwks_client=jwks)
    assert v.verify(mint(private_key))["sub"] == "user_123", "the slash is normalised away"


def test_jwks_client_is_built_lazily_from_the_issuer():
    v = ClerkVerifier(ISSUER, [])
    assert v._jwks == {}, "nothing is built until a token shows up"
    assert v.jwks_for(ISSUER).uri == f"{ISSUER}/.well-known/jwks.json", (
        "the jwks url hangs off the issuer"
    )


PROD_ISSUER = "https://clerk.worm.beer"


@pytest.mark.parametrize("iss", [ISSUER, PROD_ISSUER])
def test_verify_accepts_a_token_from_any_configured_issuer(jwks: FakeJWKS, private_key, iss):
    v = ClerkVerifier([ISSUER, PROD_ISSUER], PARTIES, jwks_client=jwks)
    assert v.verify(mint(private_key, iss=iss))["sub"] == "user_123"


@pytest.mark.parametrize(
    "iss",
    ["https://someone-else.clerk.accounts.dev", "", None],
    ids=["unknown issuer", "empty issuer", "no issuer"],
)
def test_verify_rejects_an_issuer_outside_the_list(jwks: FakeJWKS, private_key, iss):
    v = ClerkVerifier([ISSUER, PROD_ISSUER], PARTIES, jwks_client=jwks)
    with pytest.raises(AuthError, match="issuer"):
        v.verify(mint(private_key, iss=iss))


def test_each_issuer_gets_its_own_jwks_url():
    v = ClerkVerifier([ISSUER, f" {PROD_ISSUER}/ "], [])
    assert v.issuers == [ISSUER, PROD_ISSUER], "whitespace and trailing slashes normalised"
    assert v.jwks_for(PROD_ISSUER).uri == f"{PROD_ISSUER}/.well-known/jwks.json"
    assert v.jwks_for(ISSUER) is not v.jwks_for(PROD_ISSUER)


@pytest.mark.parametrize("raw", ["", " , "], ids=["empty", "only separators"])
def test_verifier_refuses_to_start_with_no_issuer(raw):
    with pytest.raises(ValueError):
        ClerkVerifier(raw.split(","), [])


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("", []),
        (ISSUER, [ISSUER]),
        (f"{ISSUER}, {PROD_ISSUER}", [ISSUER, PROD_ISSUER]),
    ],
    ids=["empty", "single", "two"],
)
def test_settings_split_the_issuer_list(raw, expected):
    assert Settings(_env_file=None, auth_issuer=raw).auth_issuer_list == expected


@pytest.mark.parametrize(
    "header",
    ["Bearer abc", "bearer abc", "BEARER abc", "Bearer  abc "],
)
def test_bearer_token_is_extracted_from_the_header(header):
    class Req:
        headers = {"authorization": header}

    assert bearer_token(Req()) == "abc", f"{header!r} carries the token"


@pytest.mark.parametrize("header", [None, "", "Bearer", "Bearer ", "Basic abc", "abc"])
def test_bearer_token_rejects_a_missing_or_odd_header(header):
    class Req:
        headers = {} if header is None else {"authorization": header}

    with pytest.raises(AuthError, match="missing bearer token"):
        bearer_token(Req())


# -- protected endpoints ---------------------------------------------------------


@pytest.fixture
def text_app() -> TextApp:
    return TextApp(128, 32)


@pytest.fixture
def api_settings() -> Settings:
    return Settings(_env_file=None, auth_issuer=ISSUER, auth_authorized_parties=",".join(PARTIES))


@pytest.fixture
def client(api_settings: Settings, store: FrameStore, text_app: TextApp, verifier) -> TestClient:
    return TestClient(create_api(api_settings, store, text_app, verifier=verifier))


def test_post_text_accepts_a_valid_token(client: TestClient, text_app: TextApp, private_key):
    r = client.post("/text", content="hi", headers=bearer(mint(private_key)))
    assert r.status_code == 202, r.text
    assert text_app.pending == 1, "the message reached the app"


def test_post_text_without_a_header_is_unauthorised(client: TestClient, text_app: TextApp):
    r = client.post("/text", content="hi")
    assert r.status_code == 401, r.text
    assert "missing bearer token" in r.json()["detail"], "the reason is spelled out"
    assert text_app.pending == 0, "nothing is queued"


@pytest.mark.parametrize(
    "overrides",
    [
        {"exp": int(time.time()) - 30},
        {"iss": "https://someone-else.clerk.accounts.dev"},
        {"azp": "https://evil.example"},
    ],
    ids=["expired", "wrong issuer", "azp not allowed"],
)
def test_post_text_rejects_a_bad_token(
    client: TestClient, text_app: TextApp, private_key, overrides
):
    r = client.post("/text", content="hi", headers=bearer(mint(private_key, **overrides)))
    assert r.status_code == 401, r.text
    assert text_app.pending == 0, "nothing is queued"


def test_post_text_rejects_a_token_from_another_key(client: TestClient, other_key):
    r = client.post("/text", content="hi", headers=bearer(mint(other_key)))
    assert r.status_code == 401, r.text


def test_post_text_ignores_azp_without_an_allow_list(
    store: FrameStore, text_app: TextApp, jwks: FakeJWKS, private_key
):
    settings = Settings(_env_file=None, auth_issuer=ISSUER)
    v = ClerkVerifier(ISSUER, settings.auth_authorized_party_list, jwks_client=jwks)
    client = TestClient(create_api(settings, store, text_app, verifier=v))

    r = client.post("/text", content="hi", headers=bearer(mint(private_key, azp="https://x.y")))
    assert r.status_code == 202, r.text


def test_delete_text_is_protected_too(client: TestClient, text_app: TextApp, private_key):
    client.post("/text", content="hi", headers=bearer(mint(private_key)))

    assert client.delete("/text").status_code == 401, "no token, no clearing"
    assert text_app.pending == 1, "the queue is untouched"
    assert client.delete("/text", headers=bearer(mint(private_key))).status_code == 200, "ok"
    assert text_app.pending == 0, "the queue is cleared"


@pytest.mark.parametrize("path", ["/healthz", "/", "/sim"])
def test_read_only_routes_stay_open(client: TestClient, path):
    assert client.get(path).status_code == 200, f"{path} needs no token"


def test_open_mode_lets_anyone_post(store: FrameStore, text_app: TextApp, caplog):
    settings = Settings(_env_file=None)
    with caplog.at_level("WARNING", logger="ledboard.api"):
        client = TestClient(create_api(settings, store, text_app))

    assert client.post("/text", content="hi").status_code == 202, "no issuer means open"
    assert client.delete("/text").status_code == 200, "for delete too"
    assert any("LEDBOARD_AUTH_ISSUER is empty" in m for m in caplog.messages), "but it's loud"


def test_create_api_builds_a_verifier_from_settings(store: FrameStore, text_app: TextApp):
    settings = Settings(_env_file=None, auth_issuer=ISSUER)
    client = TestClient(create_api(settings, store, text_app))
    assert client.post("/text", content="hi").status_code == 401, "an issuer closes the endpoint"


def test_rate_limit_follows_the_user_not_the_ip(
    store: FrameStore, text_app: TextApp, verifier, private_key
):
    settings = Settings(_env_file=None, rate_limit_per_min=2)
    client = TestClient(create_api(settings, store, text_app, verifier=verifier))
    tok = mint(private_key)

    for ip in ["10.0.0.1", "10.0.0.2"]:
        client.post("/text", content="hi", headers=bearer(tok) | {"x-forwarded-for": ip})

    r = client.post("/text", content="hi", headers=bearer(tok) | {"x-forwarded-for": "10.0.0.3"})
    assert r.status_code == 429, "the same sub is capped whatever the ip"

    other = mint(private_key, sub="user_456")
    assert client.post("/text", content="hi", headers=bearer(other)).status_code == 202, (
        "another user is fine"
    )
