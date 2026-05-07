import logging
import pytest
import time
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


class TestLiveSessionTelemetry:
    """
    Verifies that Scrape.do session IDs physically map to static proxy IPs.
    """

    def test_live_session_stickiness_and_ip_validation(
        self,
        default_sync_client: ScrapeDoClient
    ):
        """
        Proves that keeping the same session_id maintains the same
        scrape.do-rid
        """

        logger.info(">>> Testing Live IP Validation <<<")

        # Request 1
        resp1 = default_sync_client.get(
            f"{HTTPBIN_BASE}/ip",
            session_id=888,
            super=True
            )
        ip1 = resp1.httpx_response.json().get("origin")
        rid1 = resp1.rid

        logger.info(f"Session 888 (Req 1) -> RID: {rid1} | IP: {ip1}")

        # Request 2
        resp2 = default_sync_client.get(
            f"{HTTPBIN_BASE}/ip",
            session_id=888,
            super=True
            )
        ip2 = resp2.httpx_response.json().get("origin")
        rid2 = resp2.rid

        logger.info(f"Session 888 (Req 2) -> RID: {rid2} | IP: {ip2}")

        assert resp1.status_code == 200
        assert resp2.status_code == 200

        assert rid1 is not None
        assert rid1 == rid2

        assert ip1 is not None
        assert ip1 == ip2

    def test_live_session_isolation(
        self,
        default_sync_client: ScrapeDoClient
    ):
        """
        Proves that different session IDs have different RIDs
        """
        logger.info(">>> Testing Live Session Isolaion <<<")
        resp_a = default_sync_client.get(
            f"{HTTPBIN_BASE}/ip",
            session_id=101,
            super=True
            )
        ip_a = resp_a.httpx_response.json().get("origin")
        rid_a = resp_a.rid

        logger.info(f"Session 101 -> RID: {rid_a} | IP: {ip_a}")

        resp_b = default_sync_client.get(
            f"{HTTPBIN_BASE}/ip",
            session_id=909,
            super=True
            )
        ip_b = resp_b.httpx_response.json().get("origin")
        rid_b = resp_b.rid

        logger.info(f"Session 909 -> RID: {rid_b} | IP: {ip_b}")

        assert resp_a.status_code == 200
        assert resp_b.status_code == 200

        assert rid_a != rid_b
        assert ip_a != ip_b

    def test_live_session_exhaustion_and_rotation(
        self,
        default_sync_client: ScrapeDoClient
    ):
        """
        Continuously polls the proxy with a single session ID until it forces
        a rotation. Proves that a constant RID guarantees a constant IP, and a
        changed RID guarantees a changed IP.
        """

        logger.info(">>> Testing Live Session RID Rotation <<<")
        target_url = f"{HTTPBIN_BASE}/ip"
        session_id = 777
        # Prevent infinite CI hanging
        max_attempts = 15

        # 1. Establish the baseline
        resp_baseline = default_sync_client.get(
            target_url,
            session_id=session_id,
            super=True
            )
        initial_ip = resp_baseline.httpx_response.json().get("origin")
        initial_rid = resp_baseline.rid

        logger.info(
            f"Baseline (Attempt 1) -> RID: {initial_rid} | IP: {initial_ip}"
            )

        assert initial_ip is not None
        assert initial_rid is not None

        rotation_detected = False

        # Request until rotation
        for attempt in range(2, max_attempts + 1):
            time.sleep(2.5)

            resp_next = default_sync_client.get(
                target_url,
                session_id=session_id,
                super=True
                )
            current_ip = resp_next.httpx_response.json().get("origin")
            current_rid = resp_next.rid

            logger.info((
                f"Polling (Attempt {attempt}) -> RID: {current_rid} | IP: "
                f"{current_ip}"
                ))

            if current_rid == initial_rid:
                # As long as the RID is unchanged
                # the physical IP must be identical.
                assert current_ip == initial_ip
            else:
                # The RID changed.
                # Therefore, the physical IP must be different.
                rotation_detected = True
                logger.info("\n>>> PHYSICAL NODE ROTATION DETECTED! <<<")
                logger.info(f"Old IP: {initial_ip} -> New IP: {current_ip}")

                assert current_ip != initial_ip
                break

        if not rotation_detected:
            # If we hit the max attempts without a rotation, skip this test
            pytest.skip(
                f"No rotation occurred after {max_attempts} attempts."
                )
