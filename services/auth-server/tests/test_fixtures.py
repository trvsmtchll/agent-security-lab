"""Tests for the invalid-token fixtures used by verifier negative tests.

Each fixture must carry its defining defect so the mcp-server suite can
assert the matching rejection path. The kill switch (TM-03) must remove
the endpoint entirely when fixtures are disabled.
"""

import time
from unittest.mock import patch

import jwt as pyjwt
from fastapi.testclient import TestClient

from src import keys
from src.main import app

client = TestClient(app)


def _fixture(variant: str) -> dict:
    """Fetch a fixture token payload, asserting a 200 and matching variant."""
    resp = client.get("/demo/mint-broken", params={"variant": variant})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["variant"] == variant
    assert body["why_broken"]
    return body


class TestFixtureDefects:
    """Each variant exhibits the defect a verifier must catch."""

    def test_alg_none_has_no_signature_alg(self) -> None:
        """none: the header advertises alg=none."""
        token = _fixture("none")["access_token"]
        assert pyjwt.get_unverified_header(token)["alg"] == "none"

    def test_hs256_confusion_uses_symmetric_alg_under_real_kid(self) -> None:
        """hs256-confusion: HS256 header carrying the real signing kid."""
        token = _fixture("hs256-confusion")["access_token"]
        header = pyjwt.get_unverified_header(token)
        assert header["alg"] == "HS256"
        assert header["kid"] == keys.current_keypair().kid

    def test_wrong_aud_targets_another_service(self) -> None:
        """wrong-aud: validly signed but aud is a different service."""
        token = _fixture("wrong-aud")["access_token"]
        assert pyjwt.get_unverified_header(token)["alg"] == "RS256"
        claims = pyjwt.decode(token, options={"verify_signature": False})
        assert claims["aud"] == "http://some-other-service/api"

    def test_wrong_iss_signed_by_unpublished_key(self) -> None:
        """wrong-iss: signed by the foreign key, which the JWKS never lists."""
        token = _fixture("wrong-iss")["access_token"]
        assert pyjwt.get_unverified_header(token)["kid"] == keys.foreign_keypair.kid
        claims = pyjwt.decode(token, options={"verify_signature": False})
        assert claims["iss"] == "http://evil-issuer:8085"

    def test_expired_is_in_the_past(self) -> None:
        """expired: exp predates now."""
        token = _fixture("expired")["access_token"]
        claims = pyjwt.decode(token, options={"verify_signature": False})
        assert claims["exp"] < time.time()

    def test_hostile_kid_is_an_injection_probe(self) -> None:
        """hostile-kid: the kid header is a path-traversal probe."""
        token = _fixture("hostile-kid")["access_token"]
        assert pyjwt.get_unverified_header(token)["kid"].startswith("../../etc/passwd")


class TestFixtureValidation:
    """Input validation and the TM-03 kill switch."""

    def test_unknown_variant_lists_valid_options(self) -> None:
        """An unknown variant returns 400 with the valid list."""
        resp = client.get("/demo/mint-broken", params={"variant": "bogus"})
        assert resp.status_code == 400
        assert "none" in resp.json()["valid"]

    def test_missing_variant_is_rejected(self) -> None:
        """No variant is a 400, not a server error."""
        assert client.get("/demo/mint-broken").status_code == 400

    def test_disabled_fixtures_return_404(self) -> None:
        """TM-03: with fixtures disabled the endpoint is a 404."""
        with patch("src.main.settings.demo_fixtures_enabled", False):
            resp = client.get("/demo/mint-broken", params={"variant": "none"})
        assert resp.status_code == 404
