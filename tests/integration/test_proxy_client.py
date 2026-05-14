import os
import pytest
from scrape_do.proxy_client import ScrapeDoProxyClient

pytestmark = pytest.mark.integration

HTTPBIN_BASE = os.getenv("HTTPBIN_BASE", "https://httpbin.co")


class TestLiveProxyClientHappyPath:
    """
    Verifies the sync proxy client connects through Scrape.do's Proxy
    Mode and delivers a clean response wrapper for the most common
    surfaces. The `response_trace` fixture (defined in conftest.py)
    emits a structured log trace of the full response surface.
    """

    def test_live_proxy_simple_get(
        self,
        default_sync_proxy_client: ScrapeDoProxyClient,
        response_trace,
    ):
        """
        Ensures a vanilla GET through Proxy Mode reaches the target and
        the response wrapper resolves with a 2xx status.
        """
        response = default_sync_proxy_client.get(
            f"{HTTPBIN_BASE}/anything",
            render=False,
            )
        response_trace(response)

        assert response.status_code == 200

    def test_live_proxy_params_propagate(
        self,
        default_sync_proxy_client: ScrapeDoProxyClient,
        response_trace,
    ):
        """
        Ensures Scrape.do-side parameters configured into the proxy URL
        (super=True, render=False) propagate correctly to Scrape.do
        and produce a successful target call.
        """
        response = default_sync_proxy_client.get(
            f"{HTTPBIN_BASE}/anything",
            super=True,
            render=False,
            )
        response_trace(response)

        assert response.status_code == 200

    def test_live_proxy_post_json_payload(
        self,
        default_sync_proxy_client: ScrapeDoProxyClient,
        response_trace,
    ):
        """
        Ensures dictionary bodies are serialized as JSON through the
        proxy and forwarded to the target.
        """
        test_payload = {
            "sdk_status": "operational",
            "proxy_mode": True
            }

        response = default_sync_proxy_client.post(
            f"{HTTPBIN_BASE}/anything",
            body=test_payload,
            payload_type="json",
            render=False,
            )
        response_trace(response)

        assert response.status_code == 200

        echoed = response.httpx_response.json()
        assert echoed.get("json") == test_payload
