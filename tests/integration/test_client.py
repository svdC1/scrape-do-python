import logging
import pytest
from scrape_do.client import ScrapeDoClient
from scrape_do.models import (
    ScrapeDoResponse
    )

logger = logging.getLogger("integration_tests")

pytestmark = pytest.mark.integration

HTTPBIN_BASE = "https://httpbingo.org"


class TestLiveProxyErrorDetection:
    """
    Verifies the SDK correctly traverses its error detection logic tree.
    """

    def _validate_and_log_error_state(
        self,
        response: ScrapeDoResponse,
        expected_is_proxy_error: bool
    ):
        """
        Helper method to explicitly log and assert the decision tree of the
        `is_proxy_error` property based on the raw HTTPX response.
        """
        raw_resp = response.httpx_response

        logger.info("\n--- [Scrape.do Raw Response Trace] ---")
        logger.info(f"Target URL: {raw_resp.request.url}")
        logger.info(f"HTTPX Status: {raw_resp.status_code}")
        logger.info(f"Raw Headers: {dict(raw_resp.headers)}")
        logger.info(f"Raw Body (First 200 chars): {raw_resp.text[:200]}")

        # JSON Parsability Check
        is_json_parsable = False
        parsed_json = {}
        try:
            parsed_json = raw_resp.json()
            is_json_parsable = True
        except Exception:
            pass

        logger.info(f"State Check -> JSON Parsable: {is_json_parsable}")

        if is_json_parsable:
            # JSON Key / Status Match Check
            json_status = parsed_json.get("statusCode", "Missing")
            logger.info(f"State Check -> JSON 'statusCode': {json_status}")

            # Identify error keys
            error_keys = [
                "message",
                "Error",
                "detail",
                "Message",
                "errorMessage"
                ]
            has_error_keys = any(k in parsed_json for k in error_keys)
            logger.info(
                f"State Check -> Contains Error Keys: {has_error_keys}"
                )

            status_match = (json_status == raw_resp.status_code)
            logger.info(
                f"State Check -> JSON statusCode matches HTTPX status:"
                f"{status_match}"
                )
        # Header Fallback Check
        initial_status = raw_resp.headers.get(
            "scrape.do-initial-status-code", "Missing"
            )
        logger.info(
            f"State Check -> Header 'scrape.do-initial-status-code': "
            f"{initial_status}"
            )

        logger.info(
            f"SDK Conclusion -> is_proxy_error: {response.is_proxy_error}"
            )
        logger.info("--------------------------------------\n")

        assert response.is_proxy_error is expected_is_proxy_error

    def test_target_rate_limit_logic(
        self,
        no_retry_sync_client: ScrapeDoClient
    ):
        """
        Checks logic when the target explicitly rate-limits the proxy.
        """
        response = no_retry_sync_client.get(f"{HTTPBIN_BASE}/status/429")

        # Target error, proxy succeeded
        self._validate_and_log_error_state(
            response,
            expected_is_proxy_error=False
            )

    def test_proxy_timeout_logic(
        self,
        no_retry_sync_client: ScrapeDoClient
    ):
        """
        Checks logic when the proxy worker times out waiting for the target.
        """
        response = no_retry_sync_client.get(
            f"{HTTPBIN_BASE}/delay/10",
            timeout=5000
            )

        # True proxy error
        self._validate_and_log_error_state(
            response,
            expected_is_proxy_error=True
            )

    def test_unroutable_domain_logic(
        self,
        no_retry_sync_client: ScrapeDoClient
    ):
        """
        Checks logic when the proxy fails DNS resolution.
        """
        response = no_retry_sync_client.get(
            "http://this-domain-is-guaranteed-to-fail-12345.com"
            )

        # True proxy error
        self._validate_and_log_error_state(
            response,
            expected_is_proxy_error=True
            )

    # --- Transparent Response Calls (Header-only logic) ---

    def test_transparent_target_error_logic(
        self,
        no_retry_sync_client: ScrapeDoClient
    ):
        """
        Checks logic when transparentResponse=True.
        """
        response = no_retry_sync_client.get(
            f"{HTTPBIN_BASE}/status/500",
            transparent_response=True
        )

        # The target failed, not the proxy.
        self._validate_and_log_error_state(
            response,
            expected_is_proxy_error=False
            )

    def test_transparent_proxy_timeout_logic(
        self,
        no_retry_sync_client: ScrapeDoClient
    ):
        """
        Checks logic when transparentResponse=True but the proxy itself fails.
        """
        response = no_retry_sync_client.get(
            f"{HTTPBIN_BASE}/delay/10",
            timeout=5000,
            transparent_response=True
        )

        # The proxy timed out.
        self._validate_and_log_error_state(
            response,
            expected_is_proxy_error=True
            )


class TestLiveDataBoundaries:
    """
    Verifies the SDK can handle complex data payloads, binary streams, and
    state injection.
    """

    def test_live_post_json_payload(
        self,
        default_sync_client: ScrapeDoClient
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
            payload_type="json"
        )

        assert response.status_code == 200

        # Parse the echo response
        echoed_data = response.httpx_response.json()

        # httpbin puts JSON payloads inside the 'json' key of its response
        assert echoed_data.get("json") == test_payload

    def test_live_binary_file_download(
        self,
        default_sync_client: ScrapeDoClient
    ):
        """
        Ensures downloading images or files returns uncorrupted raw bytes.
        """

        # Request a raw PNG image
        response = default_sync_client.get(f"{HTTPBIN_BASE}/image/png")

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
    ):
        """
        Ensures the `set_cookies` parameter correctly injects state into the
        target request.
        """
        injected_cookie = "session_token=secret_123"

        response = default_sync_client.get(
            f"{HTTPBIN_BASE}/cookies",
            set_cookies=injected_cookie
        )

        assert response.status_code == 200

        echoed_data = response.httpx_response.json()
        returned_cookies = echoed_data.get("cookies", {})

        assert returned_cookies.get("session_token") == "secret_123"
