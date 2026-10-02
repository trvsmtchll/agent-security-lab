"""Shared test helpers (plain module, not a conftest — repo convention).

Generates RSA keys at runtime and mints both valid and deliberately broken
tokens the same way the auth-server's /demo/mint-broken endpoint does, so the
verifier's negative-path tests agree with the issuer's fixtures.
"""

import base64
import hashlib
import hmac
import json
import time

import jwt
from jwt import PyJWK, algorithms
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.config import settings

ISS = settings.oauth_issuer
AUD = settings.canonical_uri


def _pem(key: rsa.RSAPrivateKey) -> str:
    return key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()


def _public_pem(key: rsa.RSAPrivateKey) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def _jwk(key: rsa.RSAPrivateKey, kid: str) -> dict:
    data = json.loads(algorithms.RSAAlgorithm.to_jwk(key.public_key()))
    data.update(kid=kid, alg="RS256", use="sig")
    return data


class KeyFixture:
    """A signing key plus its published JWK, for injecting into the cache."""

    def __init__(self, kid: str = "testkid") -> None:
        self.kid = kid
        self._key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.private_pem = _pem(self._key)
        self.jwk = PyJWK.from_dict(_jwk(self._key, kid))
        self.public_pem = _public_pem(self._key)

    def claims(self, **overrides) -> dict:
        now = int(time.time())
        base = {
            "iss": ISS,
            "aud": AUD,
            "sub": "devbot-agent",
            "iat": now,
            "nbf": now,
            "exp": now + 300,
            "jti": "test-jti",
            "scope": "tools:read tools:execute tools:write",
        }
        base.update(overrides)
        return base

    def mint(self, *, headers=None, **claim_overrides) -> str:
        """A valid RS256 token with optional claim/header overrides."""
        hdr = {"kid": self.kid, "typ": "at+jwt"}
        hdr.update(headers or {})
        return jwt.encode(self.claims(**claim_overrides), self.private_pem,
                          algorithm="RS256", headers=hdr)


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def broken(variant: str, key: KeyFixture, foreign: KeyFixture) -> str:
    """Construct a broken token identical in shape to /demo/mint-broken."""
    claims = key.claims()
    if variant == "none":
        return jwt.encode(claims, key="", algorithm="none")
    if variant == "hs256-confusion":
        header = {"alg": "HS256", "kid": key.kid}
        signing_input = (
            _b64url(json.dumps(header, separators=(",", ":")).encode())
            + "."
            + _b64url(json.dumps(claims, separators=(",", ":")).encode())
        )
        sig = hmac.new(key.public_pem, signing_input.encode(), hashlib.sha256)
        return signing_input + "." + _b64url(sig.digest())
    if variant == "wrong-aud":
        return key.mint(aud="http://some-other-service/api")
    if variant == "wrong-iss":
        return foreign.mint(iss="http://evil-issuer:8085")
    if variant == "expired":
        now = int(time.time())
        return key.mint(exp=now - 3600, iat=now - 3900, nbf=now - 3900)
    if variant == "nbf-future":
        now = int(time.time())
        return key.mint(nbf=now + 3600)
    if variant == "hostile-kid":
        return key.mint(headers={"kid": "../../etc/passwd" + "A" * 10240})
    raise KeyError(variant)
