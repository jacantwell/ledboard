"""Clerk session JWT verification for the text endpoints.

A `ClerkVerifier` checks signature (via the issuer's JWKS), exp/iat, issuer and optionally the
`azp` origin. With no issuer configured the endpoints stay open, like they were before."""

import logging

import jwt
from fastapi import HTTPException, Request

log = logging.getLogger("ledboard.auth")


class AuthError(Exception):
    """Token missing, malformed, expired, mis-signed or from the wrong party."""


class ClerkVerifier:
    def __init__(
        self,
        issuer: str,
        authorized_parties: list[str] | None = None,
        jwks_client: jwt.PyJWKClient | None = None,
    ) -> None:
        self.issuer = issuer.rstrip("/")
        self.authorized_parties = list(authorized_parties or [])
        self._jwks = jwks_client

    @property
    def jwks(self) -> jwt.PyJWKClient:
        if self._jwks is None:
            self._jwks = jwt.PyJWKClient(f"{self.issuer}/.well-known/jwks.json", cache_keys=True)
        return self._jwks

    def _signing_key(self, token: str):
        return self.jwks.get_signing_key_from_jwt(token).key

    def verify(self, token: str) -> dict:
        try:
            key = self._signing_key(token)
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=self.issuer,
                options={"require": ["exp", "iat", "sub"]},
                leeway=5,
            )
        except jwt.PyJWTError as e:
            raise AuthError(f"invalid token: {e}") from e
        if self.authorized_parties and claims.get("azp") not in self.authorized_parties:
            raise AuthError(f"azp {claims.get('azp')!r} is not an authorized party")
        return claims


def bearer_token(request: Request) -> str:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise AuthError("missing bearer token")
    return token.strip()


def require_user(verifier: ClerkVerifier | None):
    """FastAPI dependency: the verified claims, or {} when auth is not configured."""

    def dependency(request: Request) -> dict:
        if verifier is None:
            return {}
        try:
            return verifier.verify(bearer_token(request))
        except AuthError as e:
            raise HTTPException(401, str(e)) from e

    return dependency
