"""Threat-model-driven tests for the JWT/JWKS verifier (Task 2.7)."""

import logging
import time

import jwt

from src import verifier
from src.config import settings
from tests._helpers import KeyFixture, broken


class _DownClient:
    """Stand-in PyJWKClient whose fetches always fail (IdP unreachable)."""

    def get_signing_key(self, kid):
        raise jwt.PyJWKClientConnectionError("idp down")

    def get_signing_keys(self, refresh=False):
        raise jwt.PyJWKClientConnectionError("idp down")


class _ReachableEmptyClient:
    """Reachable JWKS that simply holds no key for the requested kid."""

    def get_signing_key(self, kid):
        raise jwt.PyJWKClientError("no matching key")

    def get_signing_keys(self, refresh=False):
        return []


class _VerifierTestBase:
    """Resets the module-level cache and injects a known-good key per test."""

    def setup_method(self) -> None:
        self.key = KeyFixture("primarykid")
        self.foreign = KeyFixture("foreignkid")
        verifier._cache._known_good = {self.key.kid: self.key.jwk}
        verifier._cache._consecutive_failures = 0
        verifier._cache._opened_at = None
        settings.auth_failure_mode = "fail_closed"

    def _expect_invalid(self, token: str) -> None:
        try:
            verifier.verify_token(token)
            raise AssertionError("token was accepted")
        except verifier.InvalidToken:
            pass


class TestValidToken(_VerifierTestBase):
    def test_valid_token_returns_claims(self) -> None:
        claims = verifier.verify_token(self.key.mint(scope="tools:read"))
        assert claims["sub"] == "devbot-agent"
        assert claims["scope"] == "tools:read"


class TestAlgorithmAttacks(_VerifierTestBase):
    def test_alg_none_rejected(self) -> None:  # TM-10
        self._expect_invalid(broken("none", self.key, self.foreign))

    def test_hs256_confusion_rejected(self) -> None:  # TM-10
        self._expect_invalid(broken("hs256-confusion", self.key, self.foreign))


class TestClaimValidation(_VerifierTestBase):
    def test_wrong_aud_rejected(self) -> None:  # TM-11
        self._expect_invalid(broken("wrong-aud", self.key, self.foreign))

    def test_wrong_iss_rejected(self) -> None:  # TM-01
        # Foreign kid: JWKS reachable but holds no such key -> unknown key 401.
        verifier._cache._client = _ReachableEmptyClient()
        self._expect_invalid(broken("wrong-iss", self.key, self.foreign))
        assert verifier.breaker_state() == "closed"  # not a policy event

    def test_expired_rejected_fail_closed(self) -> None:  # TM-12
        self._expect_invalid(broken("expired", self.key, self.foreign))

    def test_expired_rejected_fail_open(self) -> None:  # TM-12
        settings.auth_failure_mode = "fail_open"
        self._expect_invalid(broken("expired", self.key, self.foreign))

    def test_nbf_future_rejected(self) -> None:  # TM-12
        self._expect_invalid(broken("nbf-future", self.key, self.foreign))

    def test_wrong_typ_rejected(self) -> None:
        self._expect_invalid(self.key.mint(headers={"typ": "JWT"}))


class TestLeewayBoundary(_VerifierTestBase):
    def test_within_leeway_accepted(self) -> None:  # TM-12
        now = int(time.time())
        # Expired by less than the leeway window -> still accepted.
        token = self.key.mint(exp=now - (settings.clock_leeway_seconds - 2),
                              iat=now - 400, nbf=now - 400)
        assert verifier.verify_token(token)["sub"] == "devbot-agent"

    def test_beyond_leeway_rejected(self) -> None:  # TM-12
        now = int(time.time())
        token = self.key.mint(exp=now - (settings.clock_leeway_seconds + 5),
                              iat=now - 400, nbf=now - 400)
        self._expect_invalid(token)


class TestHostileKid(_VerifierTestBase):
    def test_hostile_kid_clean_reject(self) -> None:  # TM-06
        # Rejected on the charset/length guard before any lookup — no side effect.
        self._expect_invalid(broken("hostile-kid", self.key, self.foreign))


class TestFailPolicy(_VerifierTestBase):
    def _cold_cache_outage_token(self) -> str:
        verifier._cache._client = _DownClient()
        verifier._cache._known_good = {}
        return self.key.mint(headers={"kid": "coldkid"})

    def test_fail_closed_raises_unavailable(self) -> None:  # TM-08
        token = self._cold_cache_outage_token()
        settings.auth_failure_mode = "fail_closed"
        try:
            verifier.verify_token(token)
            raise AssertionError("fail_closed accepted an unverifiable token")
        except verifier.AuthUnavailable:
            pass

    def test_fail_open_degraded_accept(self) -> None:  # TM-08
        token = self._cold_cache_outage_token()
        settings.auth_failure_mode = "fail_open"
        claims = verifier.verify_token(token)
        assert claims.get("_auth_degraded") is True
        assert claims["sub"] == "devbot-agent"

    def test_warm_cache_survives_outage(self) -> None:  # TM-08
        # Key already cached: an IdP outage is not a policy event at all.
        verifier._cache._client = _DownClient()
        claims = verifier.verify_token(self.key.mint(scope="tools:read"))
        assert claims["sub"] == "devbot-agent"
        assert "_auth_degraded" not in claims


class TestNoTokenInLogs(_VerifierTestBase):
    def test_logs_never_contain_raw_token(self) -> None:  # TM-16
        records: list[logging.LogRecord] = []
        handler = logging.Handler()
        handler.emit = records.append  # type: ignore[method-assign]
        verifier.logger.addHandler(handler)
        try:
            # Force the fail_open audit-log path, which logs sub/jti/kid.
            verifier._cache._client = _DownClient()
            verifier._cache._known_good = {}
            settings.auth_failure_mode = "fail_open"
            raw = self.key.mint(headers={"kid": "coldkid2"})
            verifier.verify_token(raw)
        finally:
            verifier.logger.removeHandler(handler)
        assert records, "expected an audit log record"
        for record in records:
            assert raw not in record.getMessage()
