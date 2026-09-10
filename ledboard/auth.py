"""Clerk session JWT verification for the text endpoints.

A `ClerkVerifier` checks signature (via the issuer's JWKS), exp/iat, issuer and optionally the
`azp` origin. It accepts tokens from any of its issuers, so one Pi can serve both a Clerk
production instance and a development one. With no issuer configured the endpoints stay open."""

import logging

import jwt
from fastapi import HTTPException, Request

log = logging.getLogger("ledboard.auth")


class AuthError(Exception):
    """Token missing, malformed, expired, mis-signed or from the wrong party."""


class ClerkVerifier:
    def __init__(
        self,
        issuers: str | list[str],
        authorized_parties: list[str] | None = None,
        jwks_client: jwt.PyJWKClient | None = None,
    ) -> None:
        if isinstance(issuers, str):
            issuers = [issuers]
        self.issuers = [i.strip().rstrip("/") for i in issuers if i.strip()]
        if not self.issuers:
            raise ValueError("at least one issuer is required")
        self.authorized_parties = list(authorized_parties or [])
        # One JWKS client per issuer, built on first use. A client passed in serves them all.
        self._jwks: dict[str, jwt.PyJWKClient] = (
            dict.fromkeys(self.issuers, jwks_client) if jwks_client else {}
        )

    def jwks_for(self, issuer: str) -> jwt.PyJWKClient:
        if issuer not in self._jwks:
            self._jwks[issuer] = jwt.PyJWKClient(f"{issuer}/.well-known/jwks.json", cache_keys=True)
        return self._jwks[issuer]

    def _issuer_of(self, token: str) -> str:
        """The `iss` claim, before verification, so the right JWKS can be picked."""
        try:
            claims = jwt.decode(token, options={"verify_signature": False})
        except jwt.PyJWTError as e:
            raise AuthError(f"invalid token: {e}") from e
        issuer = str(claims.get("iss", "")).rstrip("/")
        if issuer not in self.issuers:
            raise AuthError(f"invalid token: issuer {issuer!r} is not trusted")
        return issuer

    def verify(self, token: str) -> dict:
        issuer = self._issuer_of(token)
        try:
            key = self.jwks_for(issuer).get_signing_key_from_jwt(token).key
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=issuer,
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
