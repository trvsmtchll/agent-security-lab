"""In-memory RSA key material for the toy issuer.

Keys are generated at process startup and live only in memory — never
written to disk, never committed. Rotation keeps the previous public key
published for at least one token lifetime so in-flight tokens stay
verifiable (TM-09).
"""

import base64
import hashlib
import secrets
import time
from dataclasses import dataclass

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from .config import settings


@dataclass
class KeyPair:
    """An RSA signing key and its public JWK representation."""

    kid: str
    private_pem: str
    public_jwk: dict


def _b64url_uint(value: int) -> str:
    """Encode an integer as base64url without padding (RFC 7518 JWK form)."""
    raw = value.to_bytes((value.bit_length() + 7) // 8, "big")
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def generate_keypair() -> KeyPair:
    """Generate an RSA-2048 keypair with a deterministic kid.

    Returns:
        KeyPair with kid = first 16 hex chars of SHA-256 of the public key DER.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode("ascii")
    public_der = key.public_key().public_bytes(
        serialization.Encoding.DER,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    kid = hashlib.sha256(public_der).hexdigest()[:16]
    numbers = key.public_key().public_numbers()
    public_jwk = {
        "kty": "RSA",
        "n": _b64url_uint(numbers.n),
        "e": _b64url_uint(numbers.e),
        "alg": "RS256",
        "use": "sig",
        "kid": kid,
    }
    return KeyPair(kid=kid, private_pem=private_pem, public_jwk=public_jwk)


# Current key last; retired keys carry the time they stopped being current.
_current: KeyPair = generate_keypair()
_retired: list[tuple[KeyPair, float]] = []

# Fixture material for /demo/mint-broken (Task 1.4): an HS256 secret for
# key-confusion tokens and a "foreign" keypair that is never published in
# the JWKS, so its signatures can never verify against this issuer.
hs256_secret: str = secrets.token_hex(32)
foreign_keypair: KeyPair = generate_keypair()


def current_keypair() -> KeyPair:
    """Return the keypair currently used to sign tokens."""
    return _current


def rotate() -> KeyPair:
    """Make a fresh keypair current, retiring (not dropping) the old one.

    Returns:
        The new current keypair.
    """
    global _current
    _retired.append((_current, time.monotonic()))
    _current = generate_keypair()
    return _current


def published_jwks() -> dict:
    """Return the JWKS document: current key + recently retired keys.

    Reason: TM-09 — a retired key stays published for >= token_ttl_seconds
    so tokens signed just before rotation remain verifiable until expiry.
    """
    now = time.monotonic()
    ttl = settings.token_ttl_seconds
    _retired[:] = [(kp, t) for kp, t in _retired if now - t < ttl]
    keys = [kp.public_jwk for kp, _ in _retired] + [_current.public_jwk]
    return {"keys": keys}
