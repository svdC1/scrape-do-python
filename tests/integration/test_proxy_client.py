import os
import pytest
from scrape_do.proxy_client import ScrapeDoProxyClient

pytestmark = pytest.mark.integration

HTTPBIN_BASE = os.getenv("HTTPBIN_BASE", "https://httpbin.co")


class TestLiveProxyClientErrorDetection:
    """
    Mirrors `TestLiveProxyErrorDetection` from the API-mode suite
    against the sync proxy client. Confirms the proxy-mode code path
    traverses the same error decision tree as the API-mode path.

    `test_unroutable_domain_logic` is intentionally omitted - Scrape.do
    refuses internal/private/invalid hostnames at policy level before
    the proxy mode pipeline runs, identically to API mode, so adding
    the same test here would duplicate coverage.
    """

    def test_target_rate_limit_logic(
        self,
        no_retry_sync_proxy_client: ScrapeDoProxyClient,
        response_trace,
    ):
        """Target rate-limits the proxy; SDK reports `is_proxy_error=False`."""
        response = no_retry_sync_proxy_client.get(
            f"{HTTPBIN_BASE}/status/429",
            super=True,
            disable_retry=True,
            transparent_response=True,
            )
        response_trace(response, expected_is_proxy_error=False)

    def test_proxy_timeout_logic(
        self,
        no_retry_sync_proxy_client: ScrapeDoProxyClient,
        response_trace,
    ):
        """Proxy times out waiting for the target; `is_proxy_error=True`."""
        response = no_retry_sync_proxy_client.get(
            f"{HTTPBIN_BASE}/delay/10",
            timeout=5000,
            super=True,
            disable_retry=True,
            transparent_response=True,
            )
        response_trace(response, expected_is_proxy_error=True)

    def test_transparent_target_error_logic(
        self,
        no_retry_sync_proxy_client: ScrapeDoProxyClient,
        response_trace,
    ):
        """Target returns 500 under transparent mode; `is_proxy_error=False`.
        """
        response = no_retry_sync_proxy_client.get(
            f"{HTTPBIN_BASE}/status/500",
            transparent_response=True,
            super=True,
            disable_retry=True,
            )
        response_trace(response, expected_is_proxy_error=False)

    def test_transparent_proxy_timeout_logic(
        self,
        no_retry_sync_proxy_client: ScrapeDoProxyClient,
        response_trace,
    ):
        """Proxy itself times out under transparent mode; still
        `is_proxy_error=True`."""
        response = no_retry_sync_proxy_client.get(
            f"{HTTPBIN_BASE}/delay/10",
            timeout=5000,
            transparent_response=True,
            super=True,
            disable_retry=True,
            )
        response_trace(response, expected_is_proxy_error=True)


class TestLiveProxyClientDataBoundaries:
    """
    Mirrors `TestLiveDataBoundaries` from the API-mode suite against
    the sync proxy client. Binary downloads and cookie injection should
    behave identically since the SDK shares the same response-wrapping
    code path between API and Proxy modes.
    """

    def test_live_proxy_binary_file_download(
        self,
        default_sync_proxy_client: ScrapeDoProxyClient,
        response_trace,
    ):
        """Downloading a PNG through proxy mode returns uncorrupted bytes."""
        response = default_sync_proxy_client.get(
            f"{HTTPBIN_BASE}/image/png",
            super=True,
            disable_retry=True,
            transparent_response=True,
            )
        response_trace(response)

        assert response.status_code == 200
        assert "image/png" in response.httpx_response.headers.get(
            "content-type", ""
            )
        assert isinstance(response.httpx_response.content, bytes)
        # PNG byte signature.
        assert response.httpx_response.content.startswith(
            b"\x89PNG\r\n\x1a\n"
            )

    def test_live_proxy_cookie_injection(
        self,
        default_sync_proxy_client: ScrapeDoProxyClient,
        response_trace,
    ):
        """`set_cookies` parameter forwards through proxy mode to the
        target request.

        Proxy Mode defaults `customHeaders=True` server-side, which
        conflicts with `setCookies` - the SDK's
        `validate_proxy_params` raises a `ValueError` if both are set
        without explicit `custom_headers=False`.
        """
        injected_cookie = "session_token=secret_123"

        response = default_sync_proxy_client.get(
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
            super=True
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
            super=True
            )
        response_trace(response)

        assert response.status_code == 200

        echoed = response.httpx_response.json()
        assert echoed.get("json") == test_payload
