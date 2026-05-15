import pytest
import httpx
import base64
import json
from scrape_do.models import (
    PreparedScrapeDoRequest,
    RequestParameters,
    ScrapeDoResponse,
    ScrapeDoScreenshot,
    ScrapeDoFrame,
    ScrapeDoNetworkRequest
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
    def test_response_header_telemetry_extraction(
        example_url,
        full_scrape_do_telemetry_headers
    ):
        """
        Ensures Scrape.do telemetry is accurately parsed and typed from the
        headers.
        """
        req = PreparedScrapeDoRequest(
            api_params=RequestParameters(url=example_url)
            )
        http_resp = httpx.Response(
            200,
            headers=full_scrape_do_telemetry_headers,
            text="Raw HTML"
            )
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
                "scrape.do-cookies": "cookie1=value1; cookie2=value2",
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
            (500, {"Message": ["Node failed"], "ErrorCode": 42}, None, True),
            (400, {"PossibleCauses": ["Invalid params"]}, None, True),
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

    @staticmethod
    def test_status_code_passthrough(example_url, mock_json_payload):
        """
        Ensures `status_code` is a raw passthrough to the underlying
        httpx.Response status code, distinct from envelope-aware accessors
        like `target_status_code`.
        """
        req = PreparedScrapeDoRequest(
            api_params=RequestParameters(
                url=example_url,
                render=True,
                return_json=True
                )
            )
        # JSON mode pulls the target's reported status (envelope) and the
        # proxy's gateway status (raw httpx) apart.
        headers = {"scrape.do-initial-status-code": "200"}
        http_resp = httpx.Response(
            202, json=mock_json_payload, headers=headers
            )
        response = ScrapeDoResponse(request=req, response=http_resp)

        # Raw outer status from api.scrape.do.
        assert response.status_code == 202
        # Envelope-aware: target reported 200 via JSON statusCode.
        assert response.target_status_code == 200
        assert response.scrape_do_status_code == 202

    @staticmethod
    def test_response_json_method(
        make_response,
        make_request,
        mock_json_payload
    ):
        """
        Ensures the `json` method returns the expected value depending
        on the `raw_response` argument.
        """

        # Modify to include nested json payload
        # shallow copy - pytest recalls the fixture for every function
        json_payload = dict(mock_json_payload)

        inner_payload = {"StatusCode": 200,
                         "Message": "Target-Site-Message"
                         }

        json_payload['content'] = json.dumps(inner_payload)
        req = make_request(render=True, return_json=True)
        resp = make_response(status_code=200, json_data=json_payload)

        scrape_resp = ScrapeDoResponse(req, resp)

        assert scrape_resp.json(raw_response=True) == json_payload
        assert scrape_resp.json(raw_response=False) == inner_payload

    @staticmethod
    def test_unsparsable_scrape_do_json_doesnt_raise(
        make_request,
        make_response
    ):
        """
        Ensures that an invalid JSON response when return_json=True
        doesn't raise an error.
        """

        req = make_request(render=True, return_json=True)
        resp = make_response(
            status_code=200,
            json_data="unparsable_json_payload"
            )

        scrape_resp = ScrapeDoResponse(req, resp)

        assert scrape_resp._parsed_json is None


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


class TestScrapeDoResponseReprAndSerialization:

    @staticmethod
    def test_repr_format(example_url):
        """`__repr__` returns the angle-bracket shorthand with status
        and proxy-error flag."""
        req = PreparedScrapeDoRequest(
            api_params=RequestParameters(url=example_url),
            method="GET"
            )
        http_resp = httpx.Response(200)
        response = ScrapeDoResponse(request=req, response=http_resp)

        assert repr(response) == (
            f"<ScrapeDoResponse [Status: 200, "
            f"Proxy Error: {response.is_proxy_error}]>"
            )

    @staticmethod
    def test_str_falls_back_to_repr(example_url):
        """`str()` should fall through to `__repr__` since `__str__`
        isn't separately defined."""
        req = PreparedScrapeDoRequest(
            api_params=RequestParameters(url=example_url),
            method="GET"
            )
        http_resp = httpx.Response(200)
        response = ScrapeDoResponse(request=req, response=http_resp)

        assert str(response) == repr(response)

    @staticmethod
    def test_to_dict_includes_public_fields(example_url, mock_json_payload):
        """`to_dict()` should expose every documented public property
        of a populated response."""
        req = PreparedScrapeDoRequest(
            api_params=RequestParameters(
                url=example_url,
                render=True,
                return_json=True,
                ),
            method="GET"
            )
        http_resp = httpx.Response(
            200,
            json=mock_json_payload,
            headers={
                "scrape.do-target-url": "https://example.com",
                "scrape.do-request-id": "req-1",
                "scrape.do-rid": "node-1",
                "scrape.do-cookies": "a=1",
                }
            )
        response = ScrapeDoResponse(request=req, response=http_resp)

        dumped = response.to_dict()

        expected_keys = {
            "target_status_code",
            "text",
            "target_headers",
            "cookies",
            "resolved_url",
            "target_url",
            "scrape_do_status_code",
            "request_cost",
            "remaining_credits",
            "rid",
            "rate",
            "request_id",
            "auth",
            "initial_status_code",
            "scrape_do_headers",
            "is_proxy_error",
            "frames",
            "network_requests",
            "websocket_requests",
            "action_results",
            "screenshots",
            }
        assert set(dumped.keys()) == expected_keys
        assert dumped["target_url"] == "https://example.com"
        assert dumped["request_id"] == "req-1"
        assert dumped["rid"] == "node-1"

    @staticmethod
    def test_to_dict_excludes_raw_response_and_request(example_url):
        """`to_dict()` must NOT leak the wrapped `httpx.Response` or
        the `PreparedScrapeDoRequest` - both are non-serializable
        helpers recoverable via the public attribute accessors."""
        req = PreparedScrapeDoRequest(
            api_params=RequestParameters(url=example_url),
            method="GET"
            )
        http_resp = httpx.Response(200)
        response = ScrapeDoResponse(request=req, response=http_resp)

        dumped = response.to_dict()

        assert "httpx_response" not in dumped
        assert "request" not in dumped
        # Internal attribute names must not leak either.
        assert all(not k.startswith("_") for k in dumped)

    @staticmethod
    def test_to_dict_recursively_serializes_nested_models(
        example_url, mock_json_payload
    ):
        """Nested pydantic sub-models (frames, network_requests,
        screenshots) are converted to dicts, not pydantic instances."""
        req = PreparedScrapeDoRequest(
            api_params=RequestParameters(
                url=example_url,
                render=True,
                return_json=True,
                ),
            method="GET"
            )
        http_resp = httpx.Response(200, json=mock_json_payload)
        response = ScrapeDoResponse(request=req, response=http_resp)

        dumped = response.to_dict()

        # Each nested list should be a list of plain dicts.
        for key in (
            "frames",
            "network_requests",
            "websocket_requests",
            "action_results",
            "screenshots",
        ):
            items = dumped[key]
            assert items is not None and len(items) >= 1
            assert all(isinstance(item, dict) for item in items)

    @staticmethod
    def test_to_dict_renders_empty_nested_lists_as_none(example_url):
        """A response with no nested-model data should render those
        slots as None rather than empty lists - matches how `frames`
        etc. behave on the property accessors."""
        req = PreparedScrapeDoRequest(
            api_params=RequestParameters(
                url=example_url, render=True, return_json=True
                ),
            method="GET"
            )
        http_resp = httpx.Response(
            200, json={"statusCode": 200, "content": "<html>x</html>"}
            )
        response = ScrapeDoResponse(request=req, response=http_resp)

        dumped = response.to_dict()

        for key in (
            "frames",
            "network_requests",
            "websocket_requests",
            "action_results",
            "screenshots",
        ):
            assert dumped[key] is None

    @staticmethod
    def test_to_json_round_trips(example_url, mock_json_payload):
        """`to_json()` -> json.loads should yield a dict equivalent to
        `to_dict()` (modulo the `default=str` coercion for httpx URL /
        bytes that don't have a native JSON shape)."""
        req = PreparedScrapeDoRequest(
            api_params=RequestParameters(
                url=example_url,
                render=True,
                return_json=True,
                ),
            method="GET"
            )
        http_resp = httpx.Response(200, json=mock_json_payload)
        response = ScrapeDoResponse(request=req, response=http_resp)

        rendered = response.to_json()
        parsed = json.loads(rendered)

        # Keys must match.
        assert set(parsed.keys()) == set(response.to_dict().keys())
        # Top-level scalar fields round-trip identically.
        assert parsed["scrape_do_status_code"] == (
            response.scrape_do_status_code
            )
        assert parsed["is_proxy_error"] == response.is_proxy_error

    @staticmethod
    def test_to_json_respects_indent_override(example_url):
        """User can override the default indent=2 by passing `indent`
        explicitly."""
        req = PreparedScrapeDoRequest(
            api_params=RequestParameters(url=example_url),
            method="GET"
            )
        http_resp = httpx.Response(200)
        response = ScrapeDoResponse(request=req, response=http_resp)

        rendered = response.to_json(indent=None)

        # indent=None produces no newlines, single-line output.
        assert "\n" not in rendered


class TestObservationalURLFields:
    """
    Regression tests for the observational URL fields on
    `ScrapeDoFrame` and `ScrapeDoNetworkRequest`. These fields used to
    be typed as `pydantic.HttpUrl`, which rejected real-world iframe
    and network-request URLs reported by Scrape.do (e.g., embeds with
    `?a=1?b=2`). Both fields are now plain `str` since the SDK does
    not act on them beyond returning them to the user.
    """

    @pytest.mark.parametrize(
        "url",
        ["https://example.com/",
         # double `?` - the breaking pattern from the wild
         "https://example.com/embed/abc?feature=oembed?wmode=transparent",
         # double `?` + later `&` (mixed separators)
         "https://example.com/embed/def?feature=oembed?wmode=transparent&x=y",
         # single `?`, single query param
         "https://example.com/embed/ghi?wmode=transparent",
         # proper `&`-separated multi-param (sanity)
         "https://example.com/embed/jkl?a=1&b=2"
         ]
        )
    @staticmethod
    def test_frame_accepts_quirky_urls(url):
        """`ScrapeDoFrame.url` accepts any string verbatim."""
        frame = ScrapeDoFrame(url=url)
        assert frame.url == url

    @pytest.mark.parametrize(
        "url",
        ["https://example.com/",
         "https://example.com/embed/abc?feature=oembed?wmode=transparent",
         "https://example.com/embed/def?feature=oembed?wmode=transparent&x=y",
         "https://example.com/embed/ghi?wmode=transparent",
         "https://example.com/embed/jkl?a=1&b=2"
         ]
        )
    @staticmethod
    def test_network_request_accepts_quirky_urls(url):
        """`ScrapeDoNetworkRequest.url` accepts any string verbatim."""
        net_req = ScrapeDoNetworkRequest(
            url=url, method="GET", status=200
            )
        assert net_req.url == url


class TestScrapeDoResponseEdgeCases:
    """
    Coverage-gap tests for branches that aren't reachable through the
    typical happy-path / error-path setups. Each test targets a single
    line or branch the broader suite doesn't otherwise exercise.
    """

    @staticmethod
    def test_init_swallows_json_decode_error_on_returnjson_true(
        example_url,
    ):
        """If Scrape.do crashes and returns HTML despite
        `return_json=True`, the constructor swallows the JSONDecodeError
        so `is_proxy_error` can still route the request correctly."""
        req = PreparedScrapeDoRequest(
            api_params=RequestParameters(
                url=example_url,
                render=True,
                return_json=True,
                ),
            method="GET",
            )
        # Body is HTML even though the caller requested JSON.
        http_resp = httpx.Response(
            502, text="<html>Bad Gateway from upstream</html>"
            )
        response = ScrapeDoResponse(request=req, response=http_resp)

        assert response._parsed_json is None
        # The crash routes as a proxy error - no initial-status header
        # and no parseable envelope.
        assert response.is_proxy_error is True

    @staticmethod
    def test_request_property_returns_original_request(example_url):
        """`response.request` exposes the original
        `PreparedScrapeDoRequest` instance verbatim (identity check)."""
        req = PreparedScrapeDoRequest(
            api_params=RequestParameters(url=example_url),
            method="GET",
            )
        http_resp = httpx.Response(200)
        response = ScrapeDoResponse(request=req, response=http_resp)

        assert response.request is req

    @staticmethod
    def test_cookies_uses_httpx_cookies_when_pure_cookies_true(
        example_url,
    ):
        """With `pure_cookies=True`, the SDK returns the underlying
        `httpx.Response.cookies` jar verbatim instead of parsing the
        `scrape.do-cookies` header."""
        req = PreparedScrapeDoRequest(
            api_params=RequestParameters(
                url=example_url,
                pure_cookies=True,
                ),
            method="GET",
            )
        # httpx.Response.cookies needs a Request attached to walk the
        # cookie jar; the SDK's own request fixture isn't an httpx one,
        # so attach a minimal one matching the target URL.
        http_resp = httpx.Response(
            200,
            headers={
                # A real Set-Cookie header. httpx parses it into the
                # response's own `cookies` jar.
                "set-cookie": "session=abc123; Path=/",
                # The scrape.do-cookies header is intentionally
                # different so we can prove the pure_cookies branch
                # ignored it.
                "scrape.do-cookies": "different=ignored",
                },
            request=httpx.Request("GET", example_url),
            )
        response = ScrapeDoResponse(request=req, response=http_resp)

        cookies = response.cookies
        # `pure_cookies=True` returned httpx's parsed Set-Cookie jar,
        # NOT the scrape.do-cookies header value.
        assert cookies is not None
        assert dict(cookies) == {"session": "abc123"}

    @staticmethod
    def test_cookies_returns_none_on_unparseable_header(example_url):
        """`scrape.do-cookies` header present but containing no
        `key=value` pairs - the regex returns no matches, so the
        property returns None rather than an empty `httpx.Cookies`."""
        req = PreparedScrapeDoRequest(
            api_params=RequestParameters(url=example_url),
            method="GET",
            )
        http_resp = httpx.Response(
            200,
            headers={"scrape.do-cookies": "garbage no equals sign"},
            )
        response = ScrapeDoResponse(request=req, response=http_resp)

        assert response.cookies is None

    @staticmethod
    def test_json_raw_false_falls_back_when_envelope_lacks_content(
        example_url,
    ):
        """`json(raw_response=False)` with a parsed envelope that has
        no `content` key falls through to `httpx_response.json()`
        rather than crashing on the missing key."""
        req = PreparedScrapeDoRequest(
            api_params=RequestParameters(
                url=example_url,
                render=True,
                return_json=True,
                ),
            method="GET",
            )
        # Parseable JSON dict but no `content` key.
        envelope = {"statusCode": 200, "frames": []}
        http_resp = httpx.Response(200, json=envelope)
        response = ScrapeDoResponse(request=req, response=http_resp)

        # Falls back to httpx_response.json() which returns the
        # envelope dict itself (not None, not a crash).
        result = response.json(raw_response=False)
        assert result == envelope
