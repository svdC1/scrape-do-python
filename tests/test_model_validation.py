import pytest
from pydantic import ValidationError
from scrape_do.models import (
    ScreenShotAction,
    ClickAction,
    RequestParameters,
    PreparedScrapeDoRequest
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


class TestScrapeDoPreparedRequest:

    @staticmethod
    def test_head_render(example_url):
        """
        Ensures that HEAD + Headless Browser is blocked.
        """
        params = RequestParameters(url=example_url, render=True)

        with pytest.raises(
            ValidationError,
            match="architectural anti-pattern"
        ):
            PreparedScrapeDoRequest(
                api_params=params,
                method="HEAD"
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
