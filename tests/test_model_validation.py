import pytest
from pydantic import ValidationError
import httpx
import base64
import json
from scrape_do.models import (
    ScreenShotAction,
    ClickAction,
    RequestParameters,
    PreparedScrapeDoRequest,
    ScrapeDoResponse,
    ScrapeDoScreenshot
    )
from scrape_do.constants import (
    _SUPER_SUPPORTED_COUNTRIES,
    _DATACENTER_SUPPORTED_COUNTRIES,
    _ZIPCODE_NOT_ALLOWED_COUNTRIES
    )


class TestBrowserActionValidation:
    @staticmethod
    def test_screenshot_validation():
        """
        Ensures the mutually exclusive parameters of the ScreenShot action
        can't be used together.
        """
        with pytest.raises(
            ValidationError,
            match="simultaneously"
        ):
            ScreenShotAction(
                full_screenshot=True,
                particular_screenshot="#example"
            )


class TestRequestParametersValidation:

    @pytest.mark.parametrize(
        "field_name, field_value",
        [("wait_until", "domcontentloaded"),
         ("custom_wait", 1000),
         ("wait_selector", "#example"),
         ("width", 1920),
         ("height", 1080),
         ("return_json", True),
         ("block_resources", True),
         ("screenshot", True),
         ("full_screenshot", True),
         ("particular_screenshot", "#example"),
         ("playWithBrowser", [ClickAction(selector="#exmaple")]),
         ("show_frames", True),
         ("show_websocket_requests", True)
         ])
    @staticmethod
    def test_render_dependent_fields(field_name, field_value, example_url):
        """
        Ensures that using render-dependent fields while render=false is not
        allowed
        """
        with pytest.raises(
            ValidationError,
            match="require 'render=true'"
        ):
            RequestParameters(
                url=example_url,
                render=False,
                **{field_name: field_value}
            )

    @pytest.mark.parametrize(
        "field_name, field_value",
        [("screenshot", True),
         ("full_screenshot", True),
         ("particular_screenshot", "#example"),
         ("show_frames", True),
         ("show_websocket_requests", True)
         ]
        )
    @staticmethod
    def test_json_dependent_fields(field_name, field_value, example_url):
        """
        Ensures that using returnJSON-dependent fields while return_json=false
        is not allowed
        """
        with pytest.raises(
            ValidationError,
            match="'returnJSON=true' to be set"
        ):
            RequestParameters(
                url=example_url,
                render=True,
                returnJSON=False,
                **{field_name: field_value}
            )

    @pytest.mark.parametrize(
        "field_name, field_value",
        [("screenshot", True),
         ("full_screenshot", True),
         ("particular_screenshot", "#example")
         ]
        )
    @staticmethod
    def test_screenshot_dependencies(field_name, field_value, example_url):
        """
        Ensures screenshot fields cannot be used with blockResources=True
        """
        with pytest.raises(
            ValidationError,
            match="'blockResources=false'"
        ):
            RequestParameters(
                url=example_url,
                render=True,
                return_json=True,
                block_resources=True,
                **{field_name: field_value}
                )

    @pytest.mark.parametrize(
        "field_dict, match",
        [({"render": True,
           "retry_timeout": 5000
           },
          "used concurrently"
          ),
         ({"render": True,
           "return_json": True,
           "particular_screenshot": "#example",
           "play_with_browser": [ClickAction(selector="#example")]
           },
          "'particular_screenshot' parameter"
          ),
         ({"geo_code": "us",
           "regional_geo_code": "europe"
           },
          "used simultaneously"
          ),
         ({"super": False,
           "regional_geo_code": "europe"
           },
          "'super=true'"
          ),
         ({"render": True,
           "return_json": True,
           "screenshot": True,
           "particular_screenshot": "#example"
           },
          "Only one screenshot"
          ),
         ({"render": True,
           "return_json": True,
           "screenshot": True,
           "full_screenshot": True
           },
          "Only one screenshot"
          ),
         ({"render": True,
           "return_json": True,
           "full_screenshot": True,
           "particular_screenshot": "#example"
           },
          "Only one screenshot"
          ),
         ({"render": True,
           "return_json": True,
           "screenshot": True,
           "full_screenshot": True,
           "particular_screenshot": "#example"
           },
          "Only one screenshot"
          ),
         ({"custom_headers": True,
           "extra_headers": True
           },
          "Only one header"
          ),
         ({"custom_headers": True,
           "forward_headers": True
           },
          "Only one header"
          ),
         ({"extra_headers": True,
           "forward_headers": True
           },
          "Only one header"
          ),
         ({"custom_headers": True,
           "extra_headers": True,
           "forward_headers": True
           }, "Only one header"
          ),
         ({"custom_headers": True,
           "set_cookies": "cookie1=value1"
           },
          "with the set_cookies parameter"
          ),
         ({"extra_headers": True,
           "set_cookies": "cookie1=value1"
           },
          "with the set_cookies parameter"
          ),
         ({"forward_headers": True,
           "set_cookies": "cookie1=value1"
           },
          "with the set_cookies parameter"
          ),
         ]
        )
    @staticmethod
    def test_mutually_exclusive(field_dict, match, example_url):
        """
        Ensures that none of the mutually exclusive parameter combinations can
        be used together
        """

        with pytest.raises(
            ValidationError,
            match=match
        ):
            RequestParameters(
                url=example_url,
                **field_dict
                )

    @pytest.mark.parametrize(
        "field_dict",
        [{"geo_code": "us", "postal_code": "9012"},
         {"postal_code": "9012"},
         {"super": True, "postal_code": "9012"}
         ]
        )
    @staticmethod
    def test_postal_code_dependencies(field_dict, example_url):
        with pytest.raises(
            ValidationError,
            match="'super=true' and a valid 'geoCode'"
        ):
            """
            Ensures using the 'postal_code' parameter requires both super=True
            and a geo_code.
            """
            RequestParameters(
                url=example_url,
                **field_dict
            )

    @pytest.mark.parametrize("country_code", _SUPER_SUPPORTED_COUNTRIES)
    @staticmethod
    def test_geo_code_super_proxy_validation(country_code, example_url):
        """
        Ensures standard datacenter proxies reject super-proxy-only country
        codes for geo-targeting
        """
        if country_code in _DATACENTER_SUPPORTED_COUNTRIES:
            RequestParameters(
                url=example_url,
                super=False,
                geo_code=country_code
            )
        else:
            with pytest.raises(
                ValidationError,
                match="not a supported country code when 'super=false'"
            ):
                RequestParameters(
                    url=example_url,
                    super=False,
                    geo_code=country_code
                )

    @pytest.mark.parametrize(
        "invalid_country_code",
        ["aa", "zz", "qm", "qn", "qo", "qp", "qq", "qr"]
        )
    @staticmethod
    def test_invalid_country_codes(invalid_country_code, example_url):
        """
        Ensures that all proxies reject invalid country codes
        """
        with pytest.raises(
            ValidationError,
            match="not a supported country code"
        ):
            RequestParameters(
                url=example_url,
                super=True,
                geo_code=invalid_country_code
            )

        with pytest.raises(
            ValidationError,
            match="not a supported country code"
        ):
            RequestParameters(
                url=example_url,
                super=False,
                geo_code=invalid_country_code
            )

    @pytest.mark.parametrize("country_code", _ZIPCODE_NOT_ALLOWED_COUNTRIES)
    @staticmethod
    def test_invalid_postal_code_countries(country_code, example_url):
        """
        Ensures that supplying a zip code for a country that is not mapped in
        _ZIPCODE_FORMATS throws the correct unsupported error.
        """

        with pytest.raises(
            ValidationError,
            match="targeting is not supported for country"
        ):
            RequestParameters(
                url=example_url,
                super=True,
                geo_code=country_code,
                postal_code="9012"
                )

    @pytest.mark.parametrize(
        "geo_code, valid_zip, invalid_zip",
        [("us", "90210", "ABCDE"),
         ("gb", "SW1A1AA", "TOOLONGZIPCODE"),
         ("de", "10115", "101156"),
         ("fr", "31000", "750012"),
         ("ca", "M5V3L9", "M5V 3L"),
         ("au", "2000", "20001"),
         ("in", "110001", "1100012"),
         ("nl", "1012AB", "1012ABC"),
         ("it", "00100", "001001",),
         ("es", "28001", "280012"),
         ("br", "01001", "0100100"),
         ("jp", "100-0001", "10-0001")
         ]
        )
    @staticmethod
    def test_zipcode_regex_validation(
        geo_code,
        valid_zip,
        invalid_zip,
        example_url
    ):
        """
        Ensures every supported country correctly accepts its valid postal code
        formats and rejects invalid formats.
        """
        RequestParameters(
            url=example_url,
            super=True,
            geo_code=geo_code,
            postal_code=valid_zip
            )

        with pytest.raises(
            ValidationError,
            match="does not match the required pattern"
        ):
            RequestParameters(
                url=example_url,
                super=True,
                geo_code=geo_code,
                postal_code=invalid_zip
                )

    @pytest.mark.parametrize(
        "raw_url, expected_url, expected_render, expected_json",
        [(
            ("https://api.scrape.do/?url=https://example.com&render=true&"
             "returnJSON=true"
             ),
            "https://example.com/",
            True,
            True
            ),
         ("https://api.scrape.do/?token=DROP_ME&url=http://test.com",
          "http://test.com/",
          None,
          None
          ),
         (
             ("https://api.scrape.do/?url=https://example.com&"
              "transparentResponse=true"
              ),
             "https://example.com/",
             None,
             None
             )
         ]
        )
    @staticmethod
    def test_from_url_standard_parameters(
        raw_url,
        expected_url,
        expected_render,
        expected_json
    ):
        """
        Tests basic parameter extraction and boolean casting from query
        strings.
        """
        params = RequestParameters.from_url(raw_url)

        assert str(params.url) == expected_url
        assert params.render == expected_render
        assert params.return_json == expected_json
        assert getattr(params, "token", None) is None

    @staticmethod
    def test_from_url_play_with_browser_parsing():
        """
        Ensures the URL-encoded JSON string is correctly decoded and mapped to
        Action models.
        """
        encoded_actions = ("%5B%7B%22Action%22%3A%22Click%22%2C%22Selector%22%"
                           "3A%22body%22%7D%5D"
                           )
        url = (f"https://api.scrape.do/?url=https://example.com&render=true&"
               f"playWithBrowser={encoded_actions}"
               )

        params = RequestParameters.from_url(url)

        assert params.play_with_browser is not None
        assert len(params.play_with_browser) == 1
        assert params.play_with_browser[0].action == "Click"
        assert params.play_with_browser[0].selector == "body"

    @staticmethod
    def test_from_url_invalid_json_raises():
        """
        Ensures malformed JSON in the URL fails loudly with a clear message.
        """
        url = ("https://api.scrape.do/?url=https://example.com&playWithBrowser"
               "=[bad_json}"
               )
        with pytest.raises(
            ValueError,
            match="Failed to decode `playWithBrowser` parameter from URL"
        ):
            RequestParameters.from_url(url)


class TestPreparedScrapeDoRequestValidation:

    @pytest.mark.parametrize(
        "method",
        ["GET",
         "POST",
         "PUT",
         "PATCH",
         "DELETE",
         "HEAD",
         "OPTIONS"
         ]
    )
    @staticmethod
    def test_render_method(method, example_url):
        """
        Ensures that only the "GET" method is allowed when `render=True`
        """
        params = RequestParameters(url=example_url, render=True)

        if method == "GET":
            PreparedScrapeDoRequest(
                api_params=params,
                method=method
            )
        else:

            with pytest.raises(
                ValidationError,
                match="'GET' method"
            ):
                PreparedScrapeDoRequest(
                    api_params=params,
                    method=method
                )

    @staticmethod
    def test_get_body_warning(example_url):
        """
        Ensures supplying a payload body with a GET request raises
        a UserWarning.
        """
        params = RequestParameters(url=example_url)

        with pytest.warns(
            UserWarning,
            match="violates standard HTTP specifications"
        ):
            PreparedScrapeDoRequest(
                api_params=params,
                method="GET",
                body={"search": "shoes"}
            )

    @staticmethod
    def test_orphaned_headers(example_url):
        """
        Ensures passing headers without enabling a header flag throws an error.
        """
        params = RequestParameters(url=example_url)

        with pytest.raises(
            ValidationError,
            match="no header routing flag"
        ):
            PreparedScrapeDoRequest(
                api_params=params,
                headers={"Authorization": "Bearer secret"}
            )

    @pytest.mark.parametrize(
        "header_field",
        [{"custom_headers": True},
         {"extra_headers": True},
         {"forward_headers": True}
         ]
        )
    @staticmethod
    def test_missing_headers_for_flag(header_field, example_url):
        """
        Ensures enabling a header flag without providing headers throws
        an error.
        """
        params = RequestParameters(
            url=example_url,
            **header_field
            )

        with pytest.raises(
            ValidationError,
            match="no 'headers' were provided"
        ):
            PreparedScrapeDoRequest(
                api_params=params,
            )

    @staticmethod
    def test_invalid_extra_headers(example_url):
        """
        Ensures extra_headers enforce the strict 'sd-' prefix rule.
        """
        params = RequestParameters(
            url=example_url,
            extra_headers=True
            )

        with pytest.raises(
            ValidationError,
            match="prefixed with 'sd-'"
        ):
            PreparedScrapeDoRequest(
                api_params=params,
                headers={
                    "sd-Authorization": "Bearer secret",
                    "User-Agent": "MyBot"
                }
            )

    @staticmethod
    def test_valid_extra_headers(example_url):
        """
        Ensures properly prefixed extra_headers pass validation.
        """
        params = RequestParameters(
            url=example_url,
            extra_headers=True
            )

        req = PreparedScrapeDoRequest(
            api_params=params,
            headers={"sd-User-Agent": "MyBot", "sd-Accept": "application/json"}
        )

        assert req.headers["sd-User-Agent"] == "MyBot"
        assert req.headers["sd-Accept"] == "application/json"

    @pytest.mark.parametrize(
        "payload_type, body, att_name",
        [("form", {"user": "test"}, "data"),
         ("json", {"user": "test"}, "json"),
         ("raw", b"raw_bytes", "content")
         ]
        )
    @staticmethod
    def test_payload_routing(payload_type, body, att_name, example_url):
        """
        Ensures payloads are routed to the correct httpx argument based on
        payload_type.
        """
        params = RequestParameters(url=example_url)

        req_form = PreparedScrapeDoRequest(
            api_params=params,
            method="POST",
            body=body,
            payload_type=payload_type
        )
        assert att_name in req_form.to_httpx_kwargs()

    @pytest.mark.parametrize(
        "payload_type, body, error_msg",
        [("json", "<xml></xml>", "must be a Python dictionary"),
         ("raw", {"key": "value"}, "must be a string or bytes")
         ]
    )
    @staticmethod
    def test_payload_type_mismatch(payload_type, body, error_msg, example_url):
        """
        Ensures mismatched bodies and payload_types crash before execution.
        """
        params = RequestParameters(url=example_url)

        with pytest.raises(
            ValidationError,
            match=error_msg
        ):
            PreparedScrapeDoRequest(
                api_params=params,
                method="POST",
                body=body,
                payload_type=payload_type
            )

    @staticmethod
    def test_token_insertion(example_url):
        """
        Ensures Scrape.do API key is optionally included if `token` parameter
        is provided
        """
        params = RequestParameters(url=example_url)

        req = PreparedScrapeDoRequest(
            api_params=params,
            method="GET"
            )

        token_included = req.to_httpx_kwargs("API_KEY")
        no_token = req.to_httpx_kwargs()

        assert "token" in token_included["params"]
        assert "token" not in no_token["params"]


class TestScrapeDoResponse:

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
