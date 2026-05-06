import pytest
import httpx
import base64
import json
from scrape_do.models import (
    PreparedScrapeDoRequest,
    RequestParameters,
    ScrapeDoResponse,
    ScrapeDoScreenshot
    )

pytestmark = pytest.mark.unit


class TestScrapeDoResponseValidation:

    @staticmethod
    def test_target_status_code_routing_transparent(example_url):
        """
        Aligns with the logic that transparent mode successfully relays the
        target if headers exist. Ensures properties extracted from JSON
        response and headers default to None when both are missing.
        """
        req = PreparedScrapeDoRequest(
            api_params=RequestParameters(
                url=example_url,
                transparent_response=True
                )
            )
        headers = {"scrape.do-initial-status-code": "404"}
        http_resp = httpx.Response(
            404,
            text="Target Not Found",
            headers=headers
            )
        response = ScrapeDoResponse(request=req, response=http_resp)
        expected_target_headers = httpx.Headers({
            "content-length": "16",
            "content-type": "text/plain; charset=utf-8"
            })

        expected_scrape_do_headers = httpx.Headers(headers)

        # Should pull directly from httpx.Response
        assert response.target_status_code == 404
        assert response.scrape_do_status_code is None
        assert response.text == "Target Not Found"

        # Test Default Behaviour
        assert response.action_results is None
        assert response.frames is None
        assert response.rid is None
        assert response.rate is None
        assert response.cookies is None
        assert response.remaining_credits is None
        assert response.network_requests is None
        assert response.request_id is None
        assert response.request_cost is None
        assert response.initial_status_code == 404
        assert response.resolved_url is None
        assert response.target_url is None
        assert response.screenshots is None
        assert response.scrape_do_headers == expected_scrape_do_headers
        assert response.target_headers == expected_target_headers
        assert response.websocket_requests is None

    @staticmethod
    def test_target_status_code_routing_json(example_url, mock_json_payload):
        """
        Proves JSON mode extracts status code and text from the nested payload.
        """
        req = PreparedScrapeDoRequest(
            api_params=RequestParameters(
                url=example_url,
                render=True,
                return_json=True
                )
            )
        headers = {"scrape.do-initial-status-code": "200"}
        http_resp = httpx.Response(
            202,
            json=mock_json_payload,
            headers=headers
            )
        response = ScrapeDoResponse(request=req, response=http_resp)

        assert response.target_status_code == 200
        assert response.scrape_do_status_code == 202
        assert "Target Data" in response.text

    @staticmethod
    def test_response_header_telemetry_extraction(example_url, mock_headers):
        """
        Ensures Scrape.do telemetry is accurately parsed and typed from the
        headers.
        """
        req = PreparedScrapeDoRequest(
            api_params=RequestParameters(url=example_url)
            )
        http_resp = httpx.Response(200, headers=mock_headers, text="Raw HTML")
        response = ScrapeDoResponse(request=req, response=http_resp)

        expected_target_headers = httpx.Headers(
            {
                "server": "cloudflare",
                "x-frame-options": "DENY",
                "transfer-encoding": "chunked",
                "content-length": "8",
                "content-type": "text/plain; charset=utf-8"
                }
            )

        expected_scrape_do_headers = httpx.Headers(
            {
                "scrape.do-auth": "0",
                "scrape.do-cookies": "cookie1=value1;cookie2=value2",
                "scrape.do-initial-status-code": "200",
                "scrape.do-rate": "0:0",
                "scrape.do-remaining-credits": "300000",
                "scrape.do-request-cost": "25",
                "scrape.do-request-id": "123e4567-e89b-12d3-a456-426614174000",
                "scrape.do-resolved-url": "https://example.com/final",
                "scrape.do-rid": "node-123",
                "scrape.do-target-url": "https://example.com"
                }
            )

        assert response.target_headers == expected_target_headers
        assert response.scrape_do_headers == expected_scrape_do_headers
        assert response.auth == 0
        assert response.initial_status_code == 200
        assert response.rate == "0:0"
        assert response.request_cost == 25.0
        assert response.remaining_credits == 300000.0
        assert response.rid == "node-123"
        assert response.request_id == "123e4567-e89b-12d3-a456-426614174000"
        assert response.resolved_url == "https://example.com/final"
        assert response.target_url == "https://example.com"

    @staticmethod
    def test_cookie_parsing_custom_string(example_url):
        """
        Ensures the custom scrape.do-cookies header is correctly regex-parsed
        into httpx.Cookies.
        """
        req = PreparedScrapeDoRequest(
            api_params=RequestParameters(url=example_url)
            )
        http_resp = httpx.Response(
            200,
            headers={
                "scrape.do-cookies": "session_id=xyz123;preferences=dark_mode"
                }
            )
        response = ScrapeDoResponse(request=req, response=http_resp)

        cookies = response.cookies
        assert cookies is not None
        assert cookies["session_id"] == "xyz123"
        assert cookies["preferences"] == "dark_mode"

    @staticmethod
    def test_screenshot_to_bytes_validation():
        """
        Ensures the convenience method halts if image data is
        missing.
        """
        shot = ScrapeDoScreenshot(screenshot_type="FullScreenShot",
                                  error="Timeout reached"
                                  )

        with pytest.raises(
            ValueError,
            match="No image data was found"
        ):
            shot.to_bytes()

    @staticmethod
    def test_screenshot_to_file(tmp_path):
        """
        Ensures valid base64 data is correctly decoded and safely written to
        disk.
        """
        # Mocking standard base64 byte conversion
        fake_b64 = base64.b64encode(b"fake_png_header_data").decode('utf-8')
        shot = ScrapeDoScreenshot(screenshot_type="FullScreenShot",
                                  b64_image=fake_b64
                                  )

        # Pytest's built-in tmp_path fixture automatically handles cleanup
        file_path = tmp_path / "test_capture.png"
        resolved_path = shot.to_file(file_path)

        assert resolved_path.exists()
        assert resolved_path.read_bytes() == b"fake_png_header_data"

    @pytest.mark.parametrize(
        "status_code, json_data, proxy_status_header, expected_is_proxy_error",
        [
            # JSON has explicit Scrape.do error keys -> True
            (500, {"errorMessage": "Node failed"}, None, True),
            (400, {"detail": "Invalid parameters"}, None, True),
            # JSON 'statusCode' matches raw status -> False
            (403, {"statusCode": 403, "content": "WAF"}, "403", False),
            # JSON 'statusCode' mismatches raw status -> True
            (502, {"statusCode": 200}, None, True),
            # No JSON + NO Header -> True
            (504, None, None, True),
            # No JSON + Header Exists -> False
            (404, None, "404", False)
            ]
        )
    @staticmethod
    def test_is_proxy_error_branches(
        make_request,
        make_response,
        status_code,
        json_data,
        proxy_status_header,
        expected_is_proxy_error
    ):
        """
        Tests every branch of the is_proxy_error heuristic.
        """
        req = make_request(render=True, return_json=True)
        json_data = json.dumps(json_data)
        resp = make_response(
            status_code,
            json_data=json_data,
            proxy_status_header=proxy_status_header
            )

        scrape_resp = ScrapeDoResponse(req, resp)
        assert scrape_resp.is_proxy_error is expected_is_proxy_error

    @staticmethod
    def test_target_status_code_suppression_on_proxy_error(
        make_request,
        make_response
    ):
        """
        Ensures target_status_code returns None if the proxy crashed,
        preventing misleading data.
        """
        req = make_request()
        # 500 status with NO proxy headers -> Proxy crash
        resp = make_response(
            500,
            text="Gateway Timeout",
            proxy_status_header=None
            )

        scrape_resp = ScrapeDoResponse(req, resp)

        assert scrape_resp.is_proxy_error is True
        assert scrape_resp.target_status_code is None

    @staticmethod
    def test_target_status_code_extraction(make_request, make_response):
        """
        Ensures the target status code is correctly extracted depending on the
        request mode.
        """
        # JSON Mode
        req_json = make_request(render=True, return_json=True)
        resp_json = make_response(
            200,
            json_data={"statusCode": 201},
            proxy_status_header="201"
            )
        assert ScrapeDoResponse(req_json, resp_json).target_status_code == 201

        # Standard/Transparent Mode
        req_std = make_request()
        resp_std = make_response(200, proxy_status_header="418")
        assert ScrapeDoResponse(req_std, resp_std).target_status_code == 418

    @staticmethod
    def test_raise_for_status_success(make_request, make_response):
        """
        Ensures that `raise_for_status` doesn't raise an error for
        2xx status codes
        """

        req = make_request()
        resp = make_response(200, proxy_status_header=200)

        resp = ScrapeDoResponse(req, resp).raise_for_status()


class TestScrapeDoResponseSerialization:

    @staticmethod
    def test_lazy_json_parsing_nested_models(example_url, mock_json_payload):
        """
        Validates that the model correctly deserializes camelCase JSON payloads
        into Pydantic models.
        """
        req = PreparedScrapeDoRequest(
            api_params=RequestParameters(
                url=example_url,
                render=True,
                return_json=True
                ),
            method="GET"
        )

        http_resp = httpx.Response(200, json=mock_json_payload)
        response = ScrapeDoResponse(request=req, response=http_resp)

        # Network Requests Extraction
        net_reqs = response.network_requests
        assert net_reqs is not None
        assert len(net_reqs) == 1
        assert str(net_reqs[0].url) == "https://example.com/api"
        assert net_reqs[0].method == "POST"

        # WebSocket Extraction
        ws_reqs = response.websocket_requests
        assert ws_reqs is not None
        assert len(ws_reqs) == 1
        assert ws_reqs[0].type == "received"
        assert ws_reqs[0].is_text is True
        assert (
            ws_reqs[0].event.response.payload_data ==
            '{"live_price": 65000.00}'
            )

        # Action Results Extraction
        actions = response.action_results
        assert actions is not None
        assert len(actions) == 2
        assert actions[0].action == "Click"
        assert actions[0].success is False

        # Screenshots Extraction
        shots = response.screenshots
        assert len(shots) == 1
        assert shots[0].screenshot_type == "FullScreenShot"

        # Frames Extraction
        frames = response.frames
        assert len(frames) == 1
        assert frames[0].content == "<html>Iframe Content</html>"

    @staticmethod
    def test_missing_optional_json_arrays_safe_fallback(example_url):
        """
        Ensures the properties return None when the arrays are missing
        from the payload.
        """
        req = PreparedScrapeDoRequest(
            api_params=RequestParameters(
                url=example_url,
                render=True,
                return_json=True
                ),
            method="GET"
        )
        http_resp = httpx.Response(
            200, json={"statusCode": 200, "content": "<html>Data</html>"}
            )
        response = ScrapeDoResponse(request=req, response=http_resp)

        assert response.network_requests is None
        assert response.websocket_requests is None
        assert response.action_results is None
        assert response.screenshots is None
        assert response.frames is None
