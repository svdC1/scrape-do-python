import pytest
from pydantic import ValidationError
from scrape_do.constants import (
    _SUPER_SUPPORTED_COUNTRIES,
    _DATACENTER_SUPPORTED_COUNTRIES,
    _ZIPCODE_NOT_ALLOWED_COUNTRIES
    )
from scrape_do.models import (
    RequestParameters,
    ClickAction
    )


pytestmark = pytest.mark.unit


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


class TestRequestParametersSerialization:

    @staticmethod
    def test_serialize_minimal_request(example_url):
        """
        Ensures default/None parameters are cleanly dropped
        (exclude_none=True).
        """
        params = RequestParameters(url=example_url)
        payload = params.to_api_params()

        assert payload == {"url": example_url}

    @pytest.mark.parametrize(
        "field_dict, expected_dict",
        [({"wait_until": "networkidle0"},
          {"waitUntil": "networkidle0"}
          ),
         ({"custom_wait": 5000},
          {"customWait": 5000}
          ),
         ({"wait_selector": "#example"},
          {"waitSelector": "#example"}
          ),
         ({"width": 1920},
          {"width": 1920}
          ),
         ({"height": 1080},
          {"height": 1080}
          ),
         ({"return_json": True},
          {"returnJSON": "true"}
          ),
         ({"block_resources": True},
          {"blockResources": "true"}
          ),
         ({"screenshot": True, "return_json": "true"},
          {"screenShot": "true", "returnJSON": "true"}
          ),
         ({"full_screenshot": True, "return_json": True},
          {"fullScreenShot": "true", "returnJSON": "true"}
          ),
         ({"particular_screenshot": "#example", "return_json": True},
          {"particularScreenShot": "#example", "returnJSON": "true"}
          ),
         ({"show_frames": True, "return_json": True},
          {"showFrames": "true", "returnJSON": "true"}
          ),
         ({"show_websocket_requests": True, "return_json": True},
          {"showWebsocketRequests": "true", "returnJSON": "true"})
         ]
        )
    @staticmethod
    def test_serialize_render_params(field_dict, expected_dict, example_url):
        """
        Ensures render-dependent fields are serialized
        correctly
        """
        params = RequestParameters(
            url=example_url,
            render=True,
            **field_dict
        )
        payload = params.to_api_params()

        expected_payload = {"url": example_url, "render": "true"}
        expected_payload.update(expected_dict)
        assert payload == expected_payload

    @pytest.mark.parametrize(
        "field_dict, expected_dict",
        [({"custom_headers": True}, {"customHeaders": "true"}),
         ({"extra_headers": True}, {"extraHeaders": "true"}),
         ({"forward_headers": True}, {"forwardHeaders": "true"}),
         ({"set_cookies": "cookie1=value"}, {"setCookies": "cookie1=value"})
         ]
        )
    @staticmethod
    def test_serialize_header_and_cookies(
        field_dict,
        expected_dict,
        example_url
    ):
        """
        Ensures that headers and cookies parameters are serialized correctly
        """
        params = RequestParameters(
            url=example_url,
            **field_dict
        )
        payload = params.to_api_params()

        expected_payload = {"url": example_url}
        expected_payload.update(expected_dict)
        assert payload == expected_payload

    @pytest.mark.parametrize(
        "field_dict, expected_dict",
        [({"disable_redirection": True}, {"disableRedirection": "true"}),
         ({"timeout": 5000}, {"timeout": 5000}),
         ({"retry_timeout": 5000}, {"retryTimeout": 5000}),
         ({"disable_retry": False}, {"disableRetry": "false"}),
         ({"super": True}, {"super": "true"}),
         ({"session_id": 1000}, {"sessionId": 1000}),
         ({"device": "desktop"}, {"device": "desktop"}),
         ({"transparent_response": True}, {"transparentResponse": "true"}),
         ({"pure_cookies": True}, {"pureCookies": "true"}),
         ({"output": "raw"}, {"output": "raw"})
         ]
        )
    @staticmethod
    def test_serialize_network_and_output_parameters(
        field_dict,
        expected_dict,
        example_url
    ):
        """
        Ensures network, routing and output parameters are serialized correctly
        """
        params = RequestParameters(
            url=example_url,
            **field_dict
        )
        payload = params.to_api_params()

        expected_payload = {"url": example_url}
        expected_payload.update(expected_dict)
        assert payload == expected_payload

    @pytest.mark.parametrize(
        "field_dict, expected_dict",
        [({"geo_code": "us"}, {"geoCode": "us"}),
         ({"regional_geo_code": "europe"}, {"regionalGeoCode": "europe"}),
         ({"geo_code": "us", "postal_code": "90210"},
          {"geoCode": "us", "postalcode": "90210"}
          )
         ]
        )
    @staticmethod
    def test_serialize_location_parameters(
        field_dict,
        expected_dict,
        example_url
    ):
        """
        Ensures that geo-targeting parameters are serialized correctly
        """
        params = RequestParameters(
            url=example_url,
            super=True,
            **field_dict
        )
        payload = params.to_api_params()

        expected_payload = {"url": example_url, "super": "true"}
        expected_payload.update(expected_dict)
        assert payload == expected_payload


class TestProxyModeSerialization:

    @staticmethod
    def test_to_proxy_url_no_params(example_url):
        """
        Ensures that to_proxy_url with only the target URL produces an
        empty password field (per Scrape.do's cURL example).
        """
        params = RequestParameters(url=example_url)
        template = params.to_proxy_url()

        assert template == "http://{api_token}:@proxy.scrape.do:8080"

        finalized = template.format(api_token="MYTOKEN")
        assert finalized == "http://MYTOKEN:@proxy.scrape.do:8080"

    @staticmethod
    def test_to_proxy_url_strips_target_url(example_url):
        """
        Ensures the target URL is not encoded into the password field —
        only proxy-mode parameters belong there.
        """
        params = RequestParameters(url=example_url, super=True)
        template = params.to_proxy_url()

        assert example_url not in template
        assert "url=" not in template
        assert "super=true" in template

    @staticmethod
    def test_to_proxy_url_multiple_params(example_url):
        """
        Ensures multiple params are &-joined and URL-encoded as
        documented (matches `render=false&super=true&geoCode=us` example).
        """
        params = RequestParameters(
            url=example_url,
            super=True,
            geo_code="us",
            render=False
            )
        template = params.to_proxy_url()
        finalized = template.format(api_token="MYTOKEN")

        # Order-independent membership checks (Pydantic dump order isn't
        # contractually stable across model_dump implementations).
        assert finalized.startswith("http://MYTOKEN:")
        assert finalized.endswith("@proxy.scrape.do:8080")
        assert "super=true" in finalized
        assert "geoCode=us" in finalized
        assert "render=false" in finalized

    @staticmethod
    def test_to_proxy_url_format_safe_with_browser_actions(example_url):
        """
        Regression: browser-action JSON payloads contain `{` and `}`
        characters. The param string must be encoded so the template's
        `.format()` doesn't mistake them for additional placeholders.

        The encoding is intentionally double-pass so that httpx's
        URL-decode of the proxy password (during Basic auth header
        construction) leaves the value still URL-encoded for Scrape.do
        to parse. Concretely: a raw `{` becomes `%7B` after urlencode,
        then `%257B` after the outer quote() pass.
        """
        params = RequestParameters(
            url=example_url,
            render=True,
            play_with_browser=[ClickAction(selector="#submit")]
            )
        # render=True legitimately triggers the proxy-mode warning;
        # acknowledge it so the test output stays clean.
        with pytest.warns(UserWarning, match=r"render=false"):
            template = params.to_proxy_url()

        # The template should only have one {api_token} placeholder.
        # Calling format(api_token=...) must not raise KeyError on a
        # leaked {selector} or similar.
        finalized = template.format(api_token="TOKEN")
        assert "TOKEN" in finalized
        # No raw `{` or `}` survive into the finalized string outside
        # of the now-substituted {api_token} placeholder.
        rest = finalized.replace("TOKEN", "")
        assert "{" not in rest
        assert "}" not in rest
        # Double-encoded brace bodies present
        assert "%257B" in finalized or "%257b" in finalized  # `{`
        assert "%257D" in finalized or "%257d" in finalized  # `}`

    @staticmethod
    def test_set_cookies_without_explicit_custom_headers_raises(
        example_url
    ):
        """
        Ensures the proxy-mode validator rejects `setCookies=True` when
        `customHeaders` is left unset (proxy mode would auto-set it to
        True, producing a conflicting header configuration).
        """
        params = RequestParameters(
            url=example_url,
            set_cookies="foo=bar"
            )
        with pytest.raises(
            ValueError,
            match=r"customHeaders=false"
        ):
            params.validate_proxy_params()

    @staticmethod
    def test_extra_headers_without_explicit_custom_headers_raises(
        example_url
    ):
        """
        Ensures `extraHeaders=True` requires explicit `customHeaders=false`
        in proxy mode.
        """
        params = RequestParameters(
            url=example_url,
            extra_headers=True
            )
        with pytest.raises(
            ValueError,
            match=r"customHeaders=false"
        ):
            params.validate_proxy_params()

    @staticmethod
    def test_forward_headers_without_explicit_custom_headers_raises(
        example_url
    ):
        """
        Ensures `forwardHeaders=True` requires explicit `customHeaders=false`
        in proxy mode.
        """
        params = RequestParameters(
            url=example_url,
            forward_headers=True
            )
        with pytest.raises(
            ValueError,
            match=r"customHeaders=false"
        ):
            params.validate_proxy_params()

    @staticmethod
    def test_explicit_custom_headers_false_passes(
        example_url
    ):
        """
        Ensures the validator accepts the canonical workaround — explicitly
        setting `customHeaders=False` alongside the conflicting parameters.
        """
        params = RequestParameters(
            url=example_url,
            set_cookies="foo=bar",
            custom_headers=False
            )
        # Should not raise
        params.validate_proxy_params()

    @staticmethod
    def test_warns_on_render(example_url):
        """
        Ensures the validator emits a UserWarning when render=True is set,
        per Scrape.do's recommendation against headless rendering via
        proxy mode.
        """
        params = RequestParameters(url=example_url, render=True)
        with pytest.warns(UserWarning, match=r"render=false"):
            params.validate_proxy_params()

    @staticmethod
    def test_to_proxy_url_invokes_validate(example_url):
        """
        Ensures to_proxy_url runs validate_proxy_params — invalid configs
        raise instead of producing a broken proxy URL.
        """
        params = RequestParameters(
            url=example_url,
            set_cookies="foo=bar"
            )
        with pytest.raises(ValueError):
            params.to_proxy_url()
