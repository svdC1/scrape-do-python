import os
import pytest
from scrape_do.async_proxy_client import AsyncScrapeDoProxyClient

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

HTTPBIN_BASE = os.getenv("HTTPBIN_BASE", "https://httpbin.co")


class TestLiveAsyncProxyClientErrorDetection:
    """
    Mirrors `TestLiveAsyncProxyErrorDetection` from the API-mode suite
    against the async proxy client.

    `test_unroutable_domain_logic` is intentionally omitted - Scrape.do
    refuses internal/private/invalid hostnames at policy level before
    the proxy mode pipeline runs.
    """

    async def test_target_rate_limit_logic(
        self,
        no_retry_async_proxy_client: AsyncScrapeDoProxyClient,
        response_trace,
    ):
        """Target rate-limits the proxy; SDK reports `is_proxy_error=False`."""
        response = await no_retry_async_proxy_client.get(
            f"{HTTPBIN_BASE}/status/429",
            super=True,
            disable_retry=True,
            transparent_response=True,
            )
        response_trace(response, expected_is_proxy_error=False)

    async def test_proxy_timeout_logic(
        self,
        no_retry_async_proxy_client: AsyncScrapeDoProxyClient,
        response_trace,
    ):
        """Proxy times out waiting for the target; `is_proxy_error=True`."""
        response = await no_retry_async_proxy_client.get(
            f"{HTTPBIN_BASE}/delay/10",
            timeout=5000,
            super=True,
            disable_retry=True,
            transparent_response=True,
            )
        response_trace(response, expected_is_proxy_error=True)

    async def test_transparent_target_error_logic(
        self,
        no_retry_async_proxy_client: AsyncScrapeDoProxyClient,
        response_trace,
    ):
        """Target returns 500 under transparent mode; `is_proxy_error=False`.
        """
        response = await no_retry_async_proxy_client.get(
            f"{HTTPBIN_BASE}/status/500",
            transparent_response=True,
            super=True,
            disable_retry=True,
            )
        response_trace(response, expected_is_proxy_error=False)

    async def test_transparent_proxy_timeout_logic(
        self,
        no_retry_async_proxy_client: AsyncScrapeDoProxyClient,
        response_trace,
    ):
        """Proxy itself times out under transparent mode."""
        response = await no_retry_async_proxy_client.get(
            f"{HTTPBIN_BASE}/delay/10",
            timeout=5000,
            super=True,
            transparent_response=True,
            disable_retry=True,
            )
        response_trace(response, expected_is_proxy_error=True)


class TestLiveAsyncProxyClientDataBoundaries:
    """
    Mirrors `TestLiveAsyncDataBoundaries` from the API-mode suite
    against the async proxy client.
    """

    async def test_live_proxy_binary_file_download(
        self,
        default_async_proxy_client: AsyncScrapeDoProxyClient,
        response_trace,
    ):
        """Downloading a PNG through proxy mode returns uncorrupted bytes."""
        response = await default_async_proxy_client.get(
            f"{HTTPBIN_BASE}/image/png",
            disable_retry=True,
            super=True,
            transparent_response=True,
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

    async def test_live_proxy_cookie_injection(
        self,
        default_async_proxy_client: AsyncScrapeDoProxyClient,
        response_trace,
    ):
        """`set_cookies` parameter forwards through proxy mode.

        Proxy Mode defaults `customHeaders=True` server-side, which
        conflicts with `setCookies` - explicit `custom_headers=False`
        lifts that conflict.
        """
        injected_cookie = "session_token=secret_123"

        response = await default_async_proxy_client.get(
            f"{HTTPBIN_BASE}/cookies",
            set_cookies=injected_cookie,
            custom_headers=False,
            super=True,
            disable_retry=True,
            transparent_response=True,
            )
        response_trace(response)

        assert response.status_code == 200
        echoed = response.httpx_response.json()
        returned_cookies = echoed.get("cookies", {})
        assert returned_cookies.get("session_token") == "secret_123"


class TestLiveAsyncProxyClientHappyPath:
    """
    Verifies the async proxy client connects through Scrape.do's Proxy
    Mode and delivers a clean response wrapper. The `response_trace`
    fixture (defined in conftest.py) emits a structured log trace of
    the full response surface.
    """

    async def test_live_proxy_simple_get(
        self,
        default_async_proxy_client: AsyncScrapeDoProxyClient,
        response_trace,
    ):
        """
        Ensures a vanilla async GET through Proxy Mode reaches the
        target and the response wrapper resolves with a 2xx status.
        """
        response = await default_async_proxy_client.get(
            f"{HTTPBIN_BASE}/anything",
            render=False,
            super=True
            )
        response_trace(response)

        assert response.status_code == 200

    async def test_live_proxy_params_propagate(
        self,
        default_async_proxy_client: AsyncScrapeDoProxyClient,
        response_trace,
    ):
        """
        Ensures Scrape.do-side parameters configured into the proxy URL
        propagate correctly through the async client.
        """
        response = await default_async_proxy_client.get(
            f"{HTTPBIN_BASE}/anything",
            render=False,
            super=True
            )
        response_trace(response)

        assert response.status_code == 200

    async def test_live_proxy_post_json_payload(
        self,
        default_async_proxy_client: AsyncScrapeDoProxyClient,
        response_trace,
    ):
        """
        Ensures dictionary bodies are serialized as JSON through the
        async proxy client and forwarded to the target.
        """
        test_payload = {
            "sdk_status": "operational",
            "proxy_mode": True,
            "async": True,
            }

        response = await default_async_proxy_client.post(
            f"{HTTPBIN_BASE}/anything",
            body=test_payload,
            payload_type="json",
            render=False,
            super=True
            )
        response_trace(response)

        assert response.status_code == 200

        echoed = response.httpx_response.json()
        assert echoed.get("json") == test_payload
