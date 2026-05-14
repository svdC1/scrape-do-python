import os
import pytest
from scrape_do.async_client import AsyncScrapeDoClient

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
            "http://this-domain-is-guaranteed-to-fail-12345.com"
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
