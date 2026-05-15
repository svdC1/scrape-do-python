import os
import pytest
from scrape_do.client import ScrapeDoClient
from scrape_do.exceptions import (
    AuthenticationError,
    ScrapeDoJSONErrorMessage,
    TargetError,
    )

pytestmark = pytest.mark.integration

# Uses `go-httpbin`
HTTPBIN_BASE = os.getenv("HTTPBIN_BASE", "https://httpbin.co")


class TestLiveProxyErrorDetection:
    """
    Verifies the SDK correctly traverses its error detection logic tree
    against live Scrape.do gateway responses. The `response_trace`
    fixture (defined in conftest.py) emits a structured log trace of
    the full response surface and asserts `is_proxy_error` against the
    expected value.
    """

    def test_target_rate_limit_logic(
        self,
        no_retry_sync_client: ScrapeDoClient,
        response_trace,
    ):
        """
        Checks logic when the target explicitly rate-limits the proxy.
        """
        response = no_retry_sync_client.get(
            f"{HTTPBIN_BASE}/status/429",
            super=True,
            disable_retry=True,
            transparent_response=True
            )
        # Target error, proxy succeeded
        response_trace(response, expected_is_proxy_error=False)

    def test_proxy_timeout_logic(
        self,
        no_retry_sync_client: ScrapeDoClient,
        response_trace,
    ):
        """
        Checks logic when the proxy worker times out waiting for the target.
        """
        response = no_retry_sync_client.get(
            f"{HTTPBIN_BASE}/delay/10",
            timeout=5000,
            super=True,
            disable_retry=True,
            transparent_response=True
            )
        # True proxy error
        response_trace(response, expected_is_proxy_error=True)

    def test_unroutable_domain_logic(
        self,
        no_retry_sync_client: ScrapeDoClient,
        response_trace,
    ):
        """
        Checks logic when the proxy fails DNS resolution.
        """
        response = no_retry_sync_client.get(
            "http://this-domain-is-guaranteed-to-fail-12345.com",
            super=True
            )
        # True proxy error
        response_trace(response, expected_is_proxy_error=True)

    # --- Transparent Response Calls (Header-only logic) ---

    def test_transparent_target_error_logic(
        self,
        no_retry_sync_client: ScrapeDoClient,
        response_trace,
    ):
        """
        Checks logic when transparentResponse=True.
        """
        response = no_retry_sync_client.get(
            f"{HTTPBIN_BASE}/status/500",
            transparent_response=True,
            super=True,
            disable_retry=True
        )
        # The target failed, not the proxy.
        response_trace(response, expected_is_proxy_error=False)

    def test_transparent_proxy_timeout_logic(
        self,
        no_retry_sync_client: ScrapeDoClient,
        response_trace,
    ):
        """
        Checks logic when transparentResponse=True but the proxy itself fails.
        """
        response = no_retry_sync_client.get(
            f"{HTTPBIN_BASE}/delay/10",
            timeout=5000,
            transparent_response=True,
            super=True,
            disable_retry=True
        )
        # The proxy timed out.
        response_trace(response, expected_is_proxy_error=True)


class TestLiveDataBoundaries:
    """
    Verifies the SDK can handle complex data payloads, binary streams, and
    state injection.
    """

    def test_live_post_json_payload(
        self,
        default_sync_client: ScrapeDoClient,
        response_trace,
    ):
        """
        Ensures dictionary bodies are correctly serialized as JSON and
        forwarded by the Scrape.do proxy to the target website.
        """
        test_payload = {"sdk_status": "operational", "retries_tested": True}

        # httpbin.org/post will echo back whatever body we sent it
        response = default_sync_client.post(
            f"{HTTPBIN_BASE}/post",
            body=test_payload,
            payload_type="json",
            super=True,
            disable_retry=True,
            transparent_response=True
        )
        response_trace(response)

        assert response.status_code == 200

        # Parse the echo response
        echoed_data = response.httpx_response.json()

        # httpbin puts JSON payloads inside the 'json' key of its response
        assert echoed_data.get("json") == test_payload

    def test_live_binary_file_download(
        self,
        default_sync_client: ScrapeDoClient,
        response_trace,
    ):
        """
        Ensures downloading images or files returns uncorrupted raw bytes.
        """

        # Request a raw PNG image
        response = default_sync_client.get(
            f"{HTTPBIN_BASE}/image/png",
            super=True,
            disable_retry=True,
            transparent_response=True
            )
        response_trace(response)

        assert response.status_code == 200

        # Verify the Content-Type passed through
        assert "image/png" in response.httpx_response.headers.get(
            "content-type", ""
            )

        # Verify we actually got bytes back, not a decoded string
        assert isinstance(response.httpx_response.content, bytes)
        # PNG files always start with this exact byte signature
        assert response.httpx_response.content.startswith(b"\x89PNG\r\n\x1a\n")

    def test_live_cookie_injection(
        self,
        default_sync_client: ScrapeDoClient,
        response_trace,
    ):
        """
        Ensures the `set_cookies` parameter correctly injects state into the
        target request.
        """
        injected_cookie = "session_token=secret_123;"

        response = default_sync_client.get(
            f"{HTTPBIN_BASE}/cookies",
            set_cookies=injected_cookie,
            super=True,
            disable_retry=True,
            transparent_response=True
        )
        response_trace(response)

        assert response.status_code == 200

        echoed_data = response.httpx_response.json()
        returned_cookies = echoed_data.get("cookies", {})

        assert returned_cookies.get("session_token") == "secret_123"


class TestLiveResponseParsing:
    """
    Verifies the SDK correctly parses every public field on
    `ScrapeDoResponse` against live Scrape.do responses. The unit suite
    asserts the parsing logic against synthetic payloads; this class
    asserts the live data actually populates those fields.
    """

    def test_telemetry_headers_populate(
        self,
        default_sync_client: ScrapeDoClient,
        response_trace,
    ):
        """Every documented Scrape.do telemetry property surfaces a
        non-None value on a successful request."""
        response = default_sync_client.get(
            f"{HTTPBIN_BASE}/anything",
            super=True,
            disable_retry=True,
            )
        response_trace(response)

        assert response.status_code == 200
        # Identity / routing
        assert response.target_url is not None
        assert response.resolved_url is not None
        assert response.request_id is not None
        assert response.rid is not None
        # Billing
        assert response.request_cost is not None
        assert response.request_cost >= 0
        assert response.remaining_credits is not None
        assert response.remaining_credits > 0
        # Status routing
        assert response.target_status_code == 200
        assert response.initial_status_code == 200
        # Auth + rate visible as integers
        assert response.auth is not None
        assert response.rate is not None

    def test_target_and_scrape_do_headers_split(
        self,
        default_sync_client: ScrapeDoClient,
        response_trace,
    ):
        """`target_headers` excludes Scrape.do telemetry headers, and
        `scrape_do_headers` excludes target headers. The two sets are
        disjoint."""
        response = default_sync_client.get(
            f"{HTTPBIN_BASE}/anything",
            super=True,
            disable_retry=True,
            )
        response_trace(
            response,
            verbatim_headers=True,
            include_body=False,
            )

        target_keys = {k.lower() for k in response.target_headers.keys()}
        sd_keys = {k.lower() for k in response.scrape_do_headers.keys()}

        # No target header should be a scrape.do-* key.
        assert not any(k.startswith("scrape.do-") for k in target_keys)
        # Every scrape.do header should be a scrape.do-* key.
        assert all(k.startswith("scrape.do-") for k in sd_keys)
        # The two sets are disjoint.
        assert target_keys.isdisjoint(sd_keys)

    def test_cookies_extracted_from_set_cookie_header(
        self,
        default_sync_client: ScrapeDoClient,
        response_trace,
    ):
        """`response.cookies` is populated when the target emits a
        `Set-Cookie` header (proxied to the SDK via the
        `scrape.do-cookies` header by default)."""
        # httpbin.co's /cookies/set actually emits Set-Cookie headers,
        # unlike /cookies which only echoes in the body.
        response = default_sync_client.get(
            f"{HTTPBIN_BASE}/cookies/set?session=abc123&user=alice",
            super=True,
            disable_retry=True,
            )
        response_trace(response, verbatim_cookies=True)

        assert response.status_code == 200
        cookies = response.cookies
        assert cookies is not None
        # The target sets both cookies; Scrape.do forwards them via
        # the `scrape.do-cookies` header which the SDK parses.
        cookies_dict = dict(cookies)
        assert "session" in cookies_dict
        assert cookies_dict["session"] == "abc123"
        assert "user" in cookies_dict
        assert cookies_dict["user"] == "alice"

    def test_to_dict_round_trips_live_response(
        self,
        default_sync_client: ScrapeDoClient,
        response_trace,
    ):
        """`response.to_dict()` produces a structurally-complete dict
        of every public field; `to_json()` round-trips through
        `json.loads`."""
        import json as json_m

        response = default_sync_client.get(
            f"{HTTPBIN_BASE}/anything",
            super=True,
            disable_retry=True,
            )
        response_trace(response, include_body=False)

        dumped = response.to_dict()
        rendered = response.to_json()
        parsed = json_m.loads(rendered)

        # Keys match between to_dict and the json roundtrip.
        assert set(dumped.keys()) == set(parsed.keys())
        # Live response has every expected key populated.
        expected_keys = {
            "target_status_code",
            "text",
            "target_headers",
            "cookies",
            "resolved_url",
            "target_url",
            "scrape_do_status_code",
            "request_cost",
            "remaining_credits",
            "rid",
            "rate",
            "request_id",
            "auth",
            "initial_status_code",
            "scrape_do_headers",
            "is_proxy_error",
            "frames",
            "network_requests",
            "websocket_requests",
            "action_results",
            "screenshots",
            }
        assert set(dumped.keys()) == expected_keys
        # Non-render call -> no rendered artifacts present.
        assert dumped["frames"] is None
        assert dumped["network_requests"] is None
        assert dumped["screenshots"] is None


class TestLiveExceptionRouting:
    """
    Verifies `raise_for_status` correctly routes to each exception
    subclass against live Scrape.do error conditions. The unit suite
    asserts the routing logic against synthetic responses; this class
    confirms the live data shape triggers the same routing.
    """

    def test_bad_token_raises_authentication_error(self, response_trace):
        """An invalid API token surfaces as `AuthenticationError`."""
        with ScrapeDoClient(
            api_token="invalid_token_xxx_xxx",
            max_retries=0,
        ) as bad_client:
            response = bad_client.get(
                f"{HTTPBIN_BASE}/anything",
                disable_retry=True,
                super=True
                )
            response_trace(response)

            with pytest.raises(AuthenticationError):
                response.raise_for_status()

    def test_target_403_raises_target_error_under_transparent(
        self,
        no_retry_sync_client: ScrapeDoClient,
        response_trace,
    ):
        """A 403 from the target under transparent mode routes to
        `TargetError` with `is_waf_block=True`."""
        response = no_retry_sync_client.get(
            f"{HTTPBIN_BASE}/status/403",
            super=True,
            disable_retry=True,
            transparent_response=True,
            )
        response_trace(response, expected_is_proxy_error=False)

        with pytest.raises(TargetError) as exc_info:
            response.raise_for_status()

        err = exc_info.value
        assert err.target_status_code == 403
        assert err.is_waf_block is True
        assert err.is_throttled is False

    def test_target_429_raises_target_error_throttled(
        self,
        no_retry_sync_client: ScrapeDoClient,
        response_trace,
    ):
        """A 429 from the target under transparent mode routes to
        `TargetError` with `is_throttled=True`."""
        response = no_retry_sync_client.get(
            f"{HTTPBIN_BASE}/status/429",
            super=True,
            disable_retry=True,
            transparent_response=True,
            )
        response_trace(response, expected_is_proxy_error=False)

        with pytest.raises(TargetError) as exc_info:
            response.raise_for_status()

        err = exc_info.value
        assert err.target_status_code == 429
        assert err.is_throttled is True
        assert err.is_waf_block is False

    def test_scrape_do_error_envelope_parses_live(
        self,
        no_retry_sync_client: ScrapeDoClient,
        response_trace,
    ):
        """A genuine Scrape.do policy rejection (unroutable hostname)
        returns a structured error envelope that
        `ScrapeDoJSONErrorMessage.try_from_response` parses cleanly."""
        response = no_retry_sync_client.get(
            "http://this-domain-is-guaranteed-to-fail-12345.com",
            super=True
            )
        response_trace(response, expected_is_proxy_error=True)

        envelope = ScrapeDoJSONErrorMessage.try_from_response(
            response.httpx_response
            )
        assert envelope is not None
        # The "private/internal/invalid hostname" rejection always
        # populates Message and PossibleCauses (manually verified).
        assert len(envelope.messages) >= 1
        assert "hostname" in envelope.messages[0].lower()
        assert len(envelope.possible_causes) >= 1
