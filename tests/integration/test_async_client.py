import os
import pytest
from scrape_do.async_client import AsyncScrapeDoClient
from scrape_do.exceptions import (
    AuthenticationError,
    ScrapeDoJSONErrorMessage,
    TargetError,
    )

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

HTTPBIN_BASE = os.getenv("HTTPBIN_BASE", "https://httpbin.co")


class TestLiveAsyncProxyErrorDetection:
    """
    Verifies the async SDK correctly traverses its error detection logic
    tree against live Scrape.do gateway responses. The `response_trace`
    fixture (defined in conftest.py) emits a structured log trace of
    the full response surface and asserts `is_proxy_error` against the
    expected value.
    """

    async def test_target_rate_limit_logic(
        self,
        no_retry_async_client: AsyncScrapeDoClient,
        response_trace,
    ):
        """
        Checks logic when the target explicitly rate-limits the proxy.
        """
        response = await no_retry_async_client.get(
            f"{HTTPBIN_BASE}/status/429",
            super=True,
            disable_retry=True,
            transparent_response=True
            )
        # Target error, proxy succeeded
        response_trace(response, expected_is_proxy_error=False)

    async def test_proxy_timeout_logic(
        self,
        no_retry_async_client: AsyncScrapeDoClient,
        response_trace,
    ):
        """
        Checks logic when the proxy worker times out waiting for the target.
        """
        response = await no_retry_async_client.get(
            f"{HTTPBIN_BASE}/delay/10",
            timeout=5000,
            super=True,
            disable_retry=True,
            transparent_response=True
            )
        # True proxy error
        response_trace(response, expected_is_proxy_error=True)

    async def test_unroutable_domain_logic(
        self,
        no_retry_async_client: AsyncScrapeDoClient,
        response_trace,
    ):
        """
        Checks logic when the proxy fails policy / DNS resolution.
        """
        response = await no_retry_async_client.get(
            "http://this-domain-is-guaranteed-to-fail-12345.com",
            super=True
            )
        # True proxy error
        response_trace(response, expected_is_proxy_error=True)

    async def test_transparent_target_error_logic(
        self,
        no_retry_async_client: AsyncScrapeDoClient,
        response_trace,
    ):
        """
        Checks logic when transparentResponse=True.
        """
        response = await no_retry_async_client.get(
            f"{HTTPBIN_BASE}/status/500",
            transparent_response=True,
            super=True,
            disable_retry=True
        )
        # The target failed, not the proxy.
        response_trace(response, expected_is_proxy_error=False)

    async def test_transparent_proxy_timeout_logic(
        self,
        no_retry_async_client: AsyncScrapeDoClient,
        response_trace,
    ):
        """
        Checks logic when transparentResponse=True but the proxy itself fails.
        """
        response = await no_retry_async_client.get(
            f"{HTTPBIN_BASE}/delay/10",
            timeout=5000,
            transparent_response=True,
            super=True,
            disable_retry=True
        )
        # The proxy timed out.
        response_trace(response, expected_is_proxy_error=True)


class TestLiveAsyncDataBoundaries:
    """
    Verifies the async SDK handles complex payloads, binary streams, and
    state injection against live Scrape.do calls.
    """

    async def test_live_post_json_payload(
        self,
        default_async_client: AsyncScrapeDoClient,
        response_trace,
    ):
        """
        Ensures dictionary bodies are correctly serialized as JSON and
        forwarded by the Scrape.do proxy to the target website.
        """
        test_payload = {"sdk_status": "operational", "retries_tested": True}

        response = await default_async_client.post(
            f"{HTTPBIN_BASE}/post",
            body=test_payload,
            payload_type="json",
            super=True,
            disable_retry=True,
            transparent_response=True
        )
        response_trace(response)

        assert response.status_code == 200

        echoed_data = response.httpx_response.json()

        # httpbin puts JSON payloads inside the 'json' key of its response
        assert echoed_data.get("json") == test_payload

    async def test_live_binary_file_download(
        self,
        default_async_client: AsyncScrapeDoClient,
        response_trace,
    ):
        """
        Ensures downloading images or files returns uncorrupted raw bytes.
        """
        response = await default_async_client.get(
            f"{HTTPBIN_BASE}/image/png",
            super=True,
            disable_retry=True,
            transparent_response=True
            )
        response_trace(response)

        assert response.status_code == 200

        assert "image/png" in response.httpx_response.headers.get(
            "content-type", ""
            )

        assert isinstance(response.httpx_response.content, bytes)
        assert response.httpx_response.content.startswith(
            b"\x89PNG\r\n\x1a\n"
            )

    async def test_live_cookie_injection(
        self,
        default_async_client: AsyncScrapeDoClient,
        response_trace,
    ):
        """
        Ensures the `set_cookies` parameter correctly injects state into the
        target request.
        """
        injected_cookie = "session_token=secret_123"

        response = await default_async_client.get(
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


class TestLiveAsyncResponseParsing:
    """
    Verifies the async SDK correctly parses every public field on
    `ScrapeDoResponse` against live Scrape.do responses.
    """

    async def test_telemetry_headers_populate(
        self,
        default_async_client: AsyncScrapeDoClient,
        response_trace,
    ):
        """Every documented Scrape.do telemetry property surfaces a
        non-None value on a successful async request."""
        response = await default_async_client.get(
            f"{HTTPBIN_BASE}/anything",
            super=True,
            disable_retry=True,
            )
        response_trace(response)

        assert response.status_code == 200
        assert response.target_url is not None
        assert response.resolved_url is not None
        assert response.request_id is not None
        assert response.rid is not None
        assert response.request_cost is not None
        assert response.request_cost >= 0
        assert response.remaining_credits is not None
        assert response.remaining_credits > 0
        assert response.target_status_code == 200
        assert response.initial_status_code == 200
        assert response.auth is not None
        assert response.rate is not None

    async def test_target_and_scrape_do_headers_split(
        self,
        default_async_client: AsyncScrapeDoClient,
        response_trace,
    ):
        """`target_headers` excludes Scrape.do telemetry headers, and
        `scrape_do_headers` excludes target headers."""
        response = await default_async_client.get(
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

        assert not any(k.startswith("scrape.do-") for k in target_keys)
        assert all(k.startswith("scrape.do-") for k in sd_keys)
        assert target_keys.isdisjoint(sd_keys)

    async def test_cookies_extracted_from_set_cookie_header(
        self,
        default_async_client: AsyncScrapeDoClient,
        response_trace,
    ):
        """`response.cookies` is populated when the target emits a
        `Set-Cookie` header."""
        response = await default_async_client.get(
            f"{HTTPBIN_BASE}/cookies/set?session=abc123&user=alice",
            super=True,
            disable_retry=True,
            )
        response_trace(response, verbatim_cookies=True)

        assert response.status_code == 200
        cookies = response.cookies
        assert cookies is not None
        cookies_dict = dict(cookies)
        assert cookies_dict.get("session") == "abc123"
        assert cookies_dict.get("user") == "alice"

    async def test_to_dict_round_trips_live_response(
        self,
        default_async_client: AsyncScrapeDoClient,
        response_trace,
    ):
        """`response.to_dict()` and `to_json()` work on a real async
        response."""
        import json as json_m

        response = await default_async_client.get(
            f"{HTTPBIN_BASE}/anything",
            super=True,
            disable_retry=True,
            )
        response_trace(response, include_body=False)

        dumped = response.to_dict()
        rendered = response.to_json()
        parsed = json_m.loads(rendered)

        assert set(dumped.keys()) == set(parsed.keys())
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
        assert dumped["frames"] is None
        assert dumped["network_requests"] is None
        assert dumped["screenshots"] is None


class TestLiveAsyncExceptionRouting:
    """
    Verifies `raise_for_status` correctly routes to each exception
    subclass against live Scrape.do error conditions on the async
    client.
    """

    async def test_bad_token_raises_authentication_error(
        self, response_trace
    ):
        """An invalid API token surfaces as `AuthenticationError`."""
        async with AsyncScrapeDoClient(
            api_token="invalid_token_xxx_xxx",
            max_retries=0,
        ) as bad_client:
            response = await bad_client.get(
                f"{HTTPBIN_BASE}/anything",
                disable_retry=True,
                super=True
                )
            response_trace(response)

            with pytest.raises(AuthenticationError):
                response.raise_for_status()

    async def test_target_403_raises_target_error_under_transparent(
        self,
        no_retry_async_client: AsyncScrapeDoClient,
        response_trace,
    ):
        """A 403 from the target under transparent mode routes to
        `TargetError` with `is_waf_block=True`."""
        response = await no_retry_async_client.get(
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

    async def test_target_429_raises_target_error_throttled(
        self,
        no_retry_async_client: AsyncScrapeDoClient,
        response_trace,
    ):
        """A 429 from the target under transparent mode routes to
        `TargetError` with `is_throttled=True`."""
        response = await no_retry_async_client.get(
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

    async def test_scrape_do_error_envelope_parses_live(
        self,
        no_retry_async_client: AsyncScrapeDoClient,
        response_trace,
    ):
        """A Scrape.do policy rejection returns a structured error
        envelope that the SDK parses cleanly."""
        response = await no_retry_async_client.get(
            "http://this-domain-is-guaranteed-to-fail-12345.com",
            super=True
            )
        response_trace(response, expected_is_proxy_error=True)

        envelope = ScrapeDoJSONErrorMessage.try_from_response(
            response.httpx_response
            )
        assert envelope is not None
        assert len(envelope.messages) >= 1
        assert "hostname" in envelope.messages[0].lower()
        assert len(envelope.possible_causes) >= 1
