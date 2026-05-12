import logging
import os
import pytest
from scrape_do.proxy_client import ScrapeDoProxyClient

logger = logging.getLogger("integration_tests")

pytestmark = pytest.mark.integration

HTTPBIN_BASE = os.getenv("HTTPBIN_BASE", "https://httpbin.co")


class TestLiveProxyClientHappyPath:
    """
    Verifies the sync proxy client connects through Scrape.do's Proxy
    Mode and delivers a clean response wrapper for the most common
    surfaces.
    """

    def test_live_proxy_simple_get(
        self,
        default_sync_proxy_client: ScrapeDoProxyClient
    ):
        """
        Ensures a vanilla GET through Proxy Mode reaches the target and
        the response wrapper resolves with a 2xx status.
        """
        logger.info(">>> Proxy Mode | simple GET <<<")
        try:
            response = default_sync_proxy_client.get(
                f"{HTTPBIN_BASE}/anything",
                render=False,
                )
        except Exception as e:
            logger.exception(f"Request failed: {type(e).__name__}: {e}")
            raise
        logger.info(f"Status: {response.status_code}")
        logger.info(f"Body (first 200): {response.text[:200]}")

        assert response.status_code == 200

    def test_live_proxy_params_propagate(
        self,
        default_sync_proxy_client: ScrapeDoProxyClient
    ):
        """
        Ensures Scrape.do-side parameters configured into the proxy URL
        (super=True, render=False) propagate correctly to Scrape.do
        and produce a successful target call.
        """
        logger.info(">>> Proxy Mode | params propagate <<<")
        try:
            response = default_sync_proxy_client.get(
                f"{HTTPBIN_BASE}/anything",
                super=True,
                render=False,
                )
        except Exception as e:
            logger.exception(f"Request failed: {type(e).__name__}: {e}")
            raise
        logger.info(f"Status: {response.status_code}")
        logger.info(f"Headers: {dict(response.httpx_response.headers)}")

        assert response.status_code == 200

    def test_live_proxy_post_json_payload(
        self,
        default_sync_proxy_client: ScrapeDoProxyClient
    ):
        """
        Ensures dictionary bodies are serialized as JSON through the
        proxy and forwarded to the target.
        """
        logger.info(">>> Proxy Mode | POST JSON payload <<<")
        test_payload = {
            "sdk_status": "operational",
            "proxy_mode": True
            }

        try:
            response = default_sync_proxy_client.post(
                f"{HTTPBIN_BASE}/anything",
                body=test_payload,
                payload_type="json",
                render=False,
                )
        except Exception as e:
            logger.exception(f"Request failed: {type(e).__name__}: {e}")
            raise
        logger.info(f"Status: {response.status_code}")

        assert response.status_code == 200

        echoed = response.httpx_response.json()
        assert echoed.get("json") == test_payload
