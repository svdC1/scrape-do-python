import logging
import os
import pytest
from scrape_do.async_proxy_client import AsyncScrapeDoProxyClient

logger = logging.getLogger("integration_tests")

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

HTTPBIN_BASE = os.getenv("HTTPBIN_BASE", "https://httpbin.co")


class TestLiveAsyncProxyClientHappyPath:
    """
    Verifies the async proxy client connects through Scrape.do's Proxy
    Mode and delivers a clean response wrapper.
    """

    async def test_live_proxy_simple_get(
        self,
        default_async_proxy_client: AsyncScrapeDoProxyClient
    ):
        """
        Ensures a vanilla async GET through Proxy Mode reaches the
        target and the response wrapper resolves with a 2xx status.
        """
        logger.info(">>> Async Proxy Mode | simple GET <<<")
        try:
            response = await default_async_proxy_client.get(
                f"{HTTPBIN_BASE}/anything",
                render=False,
                )
        except Exception as e:
            logger.exception(f"Request failed: {type(e).__name__}: {e}")
            raise
        logger.info(f"Status: {response.status_code}")

        assert response.status_code == 200

    async def test_live_proxy_params_propagate(
        self,
        default_async_proxy_client: AsyncScrapeDoProxyClient
    ):
        """
        Ensures Scrape.do-side parameters configured into the proxy URL
        propagate correctly through the async client.
        """
        logger.info(">>> Async Proxy Mode | params propagate <<<")
        try:
            response = await default_async_proxy_client.get(
                f"{HTTPBIN_BASE}/anything",
                super=True,
                render=False,
                )
        except Exception as e:
            logger.exception(f"Request failed: {type(e).__name__}: {e}")
            raise
        logger.info(f"Status: {response.status_code}")

        assert response.status_code == 200

    async def test_live_proxy_post_json_payload(
        self,
        default_async_proxy_client: AsyncScrapeDoProxyClient
    ):
        """
        Ensures dictionary bodies are serialized as JSON through the
        async proxy client and forwarded to the target.
        """
        logger.info(">>> Async Proxy Mode | POST JSON payload <<<")
        test_payload = {
            "sdk_status": "operational",
            "proxy_mode": True,
            "async": True,
            }

        try:
            response = await default_async_proxy_client.post(
                f"{HTTPBIN_BASE}/anything",
                body=test_payload,
                payload_type="json",
                render=False,
                )
        except Exception as e:
            logger.exception(f"Request failed: {type(e).__name__}: {e}")
            raise

        assert response.status_code == 200

        echoed = response.httpx_response.json()
        assert echoed.get("json") == test_payload
