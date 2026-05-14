import os
import pytest
from scrape_do.client import ScrapeDoClient

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
            "http://this-domain-is-guaranteed-to-fail-12345.com"
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
