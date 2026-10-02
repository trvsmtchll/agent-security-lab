"""Hand-written JWT/JWKS access-token verifier — the teaching centerpiece.

Every check the MCP authorization spec and RFC 8725 require is here in plain
Python: an RS256-only algorithm allow-list, kid sanitization, signature
verification against a cached JWKS, and exact iss / aud / exp / nbf / typ
checks. The one configurable decision — what to do when a key cannot be
resolved because the issuer is unreachable — is the single visible
fail-open/fail-closed branch (§4, TM-08).

What you'd write in production (FastMCP's built-in verifier, ~6 lines):

    from fastmcp.server.auth.providers.jwt import JWTVerifier
    verifier = JWTVerifier(
        jwks_uri=settings.jwks_url,
        issuer=settings.oauth_issuer,
        audience=settings.canonical_uri,
        algorithm="RS256",
    )

The hand-rolled version below exists so the checks — and the fail policy —
are readable, testable, and breakable in the lab.
"""

import logging
import re
import time

import jwt

from .config import settings

logger = logging.getLogger("mcp-server.verifier")

# TM-10: the allow-list is the whole defence against alg=none and HS256/RS256
# key confusion. It is passed explicitly to jwt.decode(algorithms=...).
_ALLOWED_ALGS = ["RS256"]

# TM-06: a kid is only ever a dict key into the JWKS — never a path, query, or
# shell argument. Cap length and charset so a hostile kid cannot be a probe.
_KID_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")

_BREAKER_THRESHOLD = 3       # consecutive fetch failures before opening
_BREAKER_PROBE_SECONDS = 30  # half-open probe delay


class InvalidToken(Exception):
    """Token is present but invalid — the server maps this to 401."""


class AuthUnavailable(Exception):
    """Key unresolvable due to issuer outage under fail_closed — maps to 503."""


class _UnknownKey(Exception):
    """JWKS was reachable but holds no key for this kid (→ 401)."""


class _JWKSUnavailable(Exception):
    """A live JWKS fetch failed (network/IdP down) (→ fail policy)."""


class _JWKSCache:
    """PyJWKClient wrapper with last-known-good keys and a circuit breaker.

    Keys once fetched are served past their TTL (warm cache survives an IdP
    outage). Consecutive fetch failures open a breaker that rejects fast and
    half-opens after a probe delay.
    """

    def __init__(self) -> None:
        self._client = jwt.PyJWKClient(
            settings.jwks_url, cache_keys=True, lifespan=settings.jwks_cache_ttl
        )
        self._known_good: dict[str, "jwt.PyJWK"] = {}
        self._consecutive_failures = 0
        self._opened_at: float | None = None

    @property
    def breaker_state(self) -> str:
        """closed | open | half_open — exposed on /health for the demo panel."""
        if self._opened_at is None:
            return "closed"
        if time.monotonic() - self._opened_at >= _BREAKER_PROBE_SECONDS:
            return "half_open"
        return "open"

    def _record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._consecutive_failures >= _BREAKER_THRESHOLD and self._opened_at is None:
            self._opened_at = time.monotonic()

    def _record_success(self) -> None:
        self._consecutive_failures = 0
        self._opened_at = None

    def _fetch(self, kid: str) -> "jwt.PyJWK":
        try:
            key = self._client.get_signing_key(kid)
        except jwt.PyJWKClientConnectionError as exc:
            # Issuer unreachable — this is the only input to the fail policy.
            self._record_failure()
            raise _JWKSUnavailable(kid) from exc
        except jwt.PyJWKClientError as exc:
            # Reachable but no such kid — the issuer is up, so this is a plain
            # unknown-key rejection, never a fail-policy event (e.g. wrong-iss).
            self._record_success()
            raise _UnknownKey(kid) from exc
        self._known_good[kid] = key
        self._record_success()
        return key

    def get_key(self, kid: str) -> "jwt.PyJWK":
        """Resolve a signing key, preferring last-known-good over a live fetch."""
        if kid in self._known_good:
            return self._known_good[kid]
        if self.breaker_state == "open":
            raise _JWKSUnavailable(kid)
        # Unknown kid: at most one (rate-limited by the breaker) refetch.
        return self._fetch(kid)

    def refresh(self) -> None:
        """Best-effort background refresh hook (server schedules this ~15 s)."""
        try:
            self._client.get_signing_keys(refresh=True)
            self._record_success()
        except jwt.PyJWKClientError:
            self._record_failure()


_cache = _JWKSCache()


def breaker_state() -> str:
    """Current circuit-breaker state, for the /health endpoint."""
    return _cache.breaker_state


def refresh_keys() -> None:
    """Trigger a JWKS refresh (called by the server's background loop)."""
    _cache.refresh()


def _degraded_accept(token: str, kid: str) -> dict:
    """fail_open path: accept iff every non-signature check passes (§4)."""
    claims = jwt.decode(token, options={"verify_signature": False})
    _check_non_signature_claims(token, claims)
    logger.warning(
        "auth event %s",
        {
            "event": "auth_degraded_accept",
            "policy": "fail_open",
            "reason": "jwks_unavailable",
            "sub": claims.get("sub"),
            "jti": claims.get("jti"),
            "kid": kid,
        },
    )
    claims["_auth_degraded"] = True
    return claims


def _check_non_signature_claims(token: str, claims: dict) -> None:
    """Steps 4–7 without the signature: iss, aud, exp/nbf, typ.

    Used by the fail_open branch; expired or wrong iss/aud still raise
    InvalidToken (401) in both modes — the toggle only excuses an
    *unverifiable* token, never an *invalid* one.
    """
    leeway = settings.clock_leeway_seconds
    now = time.time()
    if claims.get("iss") != settings.oauth_issuer:
        raise InvalidToken("issuer mismatch")
    aud = claims.get("aud")
    aud_list = [aud] if isinstance(aud, str) else (aud or [])
    if settings.canonical_uri not in aud_list:
        raise InvalidToken("audience mismatch")
    if "exp" in claims and now > claims["exp"] + leeway:
        raise InvalidToken("expired")
    if "nbf" in claims and now < claims["nbf"] - leeway:
        raise InvalidToken("not yet valid")
    if jwt.get_unverified_header(token).get("typ") != "at+jwt":
        raise InvalidToken("wrong typ")


def verify_token(token: str) -> dict:
    """Validate an access token and return its claims, or raise.

    Raises:
        InvalidToken: any invalid token (→ 401).
        AuthUnavailable: key unresolvable + fail_closed (→ 503).
    """
    # 1. Header + algorithm allow-list (TM-10).
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError as exc:
        raise InvalidToken("malformed header") from exc
    if header.get("alg") not in _ALLOWED_ALGS:
        raise InvalidToken(f"disallowed alg: {header.get('alg')!r}")

    # 2. Sanitize kid before it is ever used as a lookup key (TM-06).
    kid = header.get("kid", "")
    if not isinstance(kid, str) or not _KID_RE.match(kid):
        raise InvalidToken("invalid kid")

    # Resolve the signing key; this is where the fail policy may trigger.
    try:
        signing_key = _cache.get_key(kid)
    except _UnknownKey as exc:
        raise InvalidToken("unknown key id") from exc
    except _JWKSUnavailable as exc:
        # The single fail-open/fail-closed branch (§4, TM-08).
        if settings.auth_failure_mode == "fail_closed":
            logger.warning(
                "auth event %s",
                {
                    "event": "auth_unavailable",
                    "policy": "fail_closed",
                    "reason": "jwks_unavailable",
                    "kid": kid,
                },
            )
            raise AuthUnavailable("jwks_unavailable") from exc
        return _degraded_accept(token, kid)

    # 3–6. Signature + registered-claim validation. jku/x5u headers are ignored
    # by construction — the key comes only from our JWKS cache (TM-07).
    try:
        claims = jwt.decode(
            token,
            signing_key.key,
            algorithms=_ALLOWED_ALGS,
            issuer=settings.oauth_issuer,
            audience=settings.canonical_uri,
            leeway=settings.clock_leeway_seconds,
            options={"require": ["exp", "iat", "nbf", "iss", "aud", "sub"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise InvalidToken("expired") from exc
    except jwt.InvalidIssuerError as exc:
        raise InvalidToken("issuer mismatch") from exc
    except jwt.InvalidAudienceError as exc:
        raise InvalidToken("audience mismatch") from exc
    except jwt.PyJWTError as exc:
        raise InvalidToken("signature or claims invalid") from exc

    # 7. Token type.
    if header.get("typ") != "at+jwt":
        raise InvalidToken("wrong typ")
    return claims
