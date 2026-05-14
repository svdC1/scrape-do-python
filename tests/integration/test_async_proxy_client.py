import os
import pytest
from scrape_do.async_proxy_client import AsyncScrapeDoProxyClient

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

HTTPBIN_BASE = os.getenv("HTTPBIN_BASE", "https://httpbin.co")


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
            super=True,
            render=False,
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
            )
        response_trace(response)

        assert response.status_code == 200

        echoed = response.httpx_response.json()
        assert echoed.get("json") == test_payload
