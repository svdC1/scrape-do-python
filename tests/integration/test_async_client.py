import logging
import os
import re
import pytest
from scrape_do.async_client import AsyncScrapeDoClient
from scrape_do.models import (
    ScrapeDoResponse
    )

logger = logging.getLogger("integration_tests")

pytestmark = [pytest.mark.integration, pytest.mark.asyncio]

HTTPBIN_BASE = os.getenv("HTTPBIN_BASE", "https://httpbin.co")

_TOKEN_RE = re.compile(r"(?i)([?&]token=)[^&]+")


def _redact_token(url) -> str:
    """
    Strip the `token=...` query parameter from a URL string.
    """
    return _TOKEN_RE.sub(r"\1REDACTED", str(url))


class TestLiveAsyncProxyErrorDetection:
    """
    Verifies the async SDK correctly traverses its error detection logic
    tree against live Scrape.do gateway responses.
    """

    async def _validate_and_log_error_state(
        self,
        response: ScrapeDoResponse,
        expected_is_proxy_error: bool
    ):
        """
        Helper that logs the response decision tree and asserts the
        `is_proxy_error` property matches the expected value.
        """
        raw_resp = response.httpx_response

        logger.info("--- [Scrape.do Async Raw Response Trace] ---")
        logger.info(f"Target URL: {response.target_url}")
        logger.info(f"HTTPX Status: {raw_resp.status_code}")
        logger.info(f"Raw Headers: {dict(raw_resp.headers)}")
        logger.info(f"Raw Body (First 200 chars): {raw_resp.text[:200]}")

        is_json_parsable = False
        parsed_json = {}
        try:
            parsed_json = raw_resp.json()
            is_json_parsable = True
        except Exception:
            pass

        logger.info(f"State Check -> JSON Parsable: {is_json_parsable}")

        if is_json_parsable:
            json_status = parsed_json.get("statusCode", "Missing")
            logger.info(f"State Check -> JSON 'statusCode': {json_status}")

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

        assert response.is_proxy_error is expected_is_proxy_error

    async def test_target_rate_limit_logic(
        self,
        no_retry_async_client: AsyncScrapeDoClient
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
        await self._validate_and_log_error_state(
            response,
            expected_is_proxy_error=False
            )

    async def test_proxy_timeout_logic(
        self,
        no_retry_async_client: AsyncScrapeDoClient
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
        await self._validate_and_log_error_state(
            response,
            expected_is_proxy_error=True
            )

    async def test_unroutable_domain_logic(
        self,
        no_retry_async_client: AsyncScrapeDoClient
    ):
        """
        Checks logic when the proxy fails policy / DNS resolution.
        """
        response = await no_retry_async_client.get(
            "http://this-domain-is-guaranteed-to-fail-12345.com"
            )

        # True proxy error
        await self._validate_and_log_error_state(
            response,
            expected_is_proxy_error=True
            )

    async def test_transparent_target_error_logic(
        self,
        no_retry_async_client: AsyncScrapeDoClient
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
        await self._validate_and_log_error_state(
            response,
            expected_is_proxy_error=False
            )

    async def test_transparent_proxy_timeout_logic(
        self,
        no_retry_async_client: AsyncScrapeDoClient
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
        await self._validate_and_log_error_state(
            response,
            expected_is_proxy_error=True
            )


class TestLiveAsyncDataBoundaries:
    """
    Verifies the async SDK handles complex payloads, binary streams, and
    state injection against live Scrape.do calls.
    """

    async def test_live_post_json_payload(
        self,
        default_async_client: AsyncScrapeDoClient
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

        assert response.status_code == 200

        echoed_data = response.httpx_response.json()

        # httpbin puts JSON payloads inside the 'json' key of its response
        assert echoed_data.get("json") == test_payload

    async def test_live_binary_file_download(
        self,
        default_async_client: AsyncScrapeDoClient
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

        assert response.status_code == 200

        echoed_data = response.httpx_response.json()
        returned_cookies = echoed_data.get("cookies", {})

        assert returned_cookies.get("session_token") == "secret_123"
