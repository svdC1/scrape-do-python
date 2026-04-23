import pytest
from itertools import combinations
import json
from pydantic import ValidationError
from scrape_do.models import (
    RequestParameters,
    ClickAction,
    WaitAction,
    WaitSelectorAction,
    ExecuteAction,
    ScreenShotAction,
    FillAction,
    ScrollToAction,
    ScrollXAction,
    ScrollYAction,
    WaitForRequestCompletionAction
    )

from scrape_do.constants import (
    _SUPER_SUPPORTED_COUNTRIES,
    _DATACENTER_SUPPORTED_COUNTRIES,
    _ZIPCODE_FORMATS
    )

# --- BrowserAction Tests ---


def test_browser_action_string_boundaries():
    """
    Ensures empty strings are rejected for CSS selectors and JS execution.
    """

    empty_string_actions = [
        lambda: ClickAction(selector=""),
        lambda: WaitSelectorAction(wait_selector=""),
        lambda: ScrollToAction(selector=""),
        lambda: FillAction(selector="", value="text"),
        lambda: ExecuteAction(execute=""),
        lambda: WaitForRequestCompletionAction(url_pattern="", timeout=1000)
    ]

    for action_constructor in empty_string_actions:
        with pytest.raises(
            ValidationError,
            match="String should have at least 1 character"
        ):
            action_constructor()


def test_browser_action_integer_boundaries():
    """
    Ensures negative timeouts are rejected.
    """

    negative_time_actions = [
        lambda: WaitAction(timeout=-50),
        lambda: WaitSelectorAction(wait_selector="#hero", timeout=-1),
        lambda: WaitForRequestCompletionAction(url_pattern="api",
                                               timeout=-5000
                                               )
    ]

    for action_constructor in negative_time_actions:
        with pytest.raises(
            ValidationError,
            match="Input should be greater than or equal to 0"
        ):
            action_constructor()


def test_screenshot_action_internal_conflict():
    """
    Ensures the internal screenshot validator catches conflicting targeting.
    """
    with pytest.raises(
        ValidationError,
        match="'full_screenshot' and 'particular_screenshot' simultaneously"
    ):
        ScreenShotAction(
            full_screenshot=True,
            particular_screenshot="#hero-banner"
        )

# --- Request Parameters Tests ---

# --- Serialization Tests ---


def test_invalid_browser_action_rejection():
    """
    Ensures unsupported headless browser actions are rejected before
    serialization.
    """
    with pytest.raises(
        ValidationError,
        match="does not match any of the expected tags"
    ):
        RequestParameters(
            url="https://example.com",
            render=True,
            play_with_browser=[
                {"action": "Hover", "selector": "#menu"}
            ]
        )


def test_browser_action_dict_parsing():
    """
    Ensures Pydantic's discriminator can successfully parse raw dictionaries
    into the correct Action models using both snake_case and camelCase.
    """
    req = RequestParameters(
        url="https://example.com",
        render=True,
        play_with_browser=[
            {"Action": "Click", "Selector": "#btn"},
            {"action": "Wait", "timeout": 2000}
        ]
    )

    assert isinstance(req.play_with_browser[0], ClickAction)
    assert isinstance(req.play_with_browser[1], WaitAction)

    params = req.to_api_params()
    actions_json = json.loads(params["playWithBrowser"])
    assert actions_json[0] == {"Action": "Click", "Selector": "#btn"}
    assert actions_json[1] == {"Action": "Wait", "Timeout": 2000}


def test_minimal_request_serialization():
    """
    Ensures that an empty request strips all None values and only serializes
    the absolute minimum required parameters.
    """
    req = RequestParameters(url="https://example.com")
    params = req.to_api_params()

    assert params == {"url": "https://example.com/"}


def test_serialization_group_a_browser():
    """
    Ensures rendering, super-proxy targeting, and browser actions serialize
    correctly.
    """

    actions = [
        WaitAction(timeout=10000),
        WaitSelectorAction(wait_selector="#example"),
        ClickAction(selector="#example"),
        ExecuteAction(execute="example"),
        ScreenShotAction(full_screenshot=False),
        FillAction(selector="#example", value="example"),
        ScrollToAction(selector="#example"),
        ScrollXAction(value=100),
        ScrollYAction(value=100),
        WaitForRequestCompletionAction(url_pattern="example.com",
                                       timeout=10000
                                       )
        ]

    expected_actions_json = json.dumps([
        {"Action": "Wait", "Timeout": 10000},
        {"Action": "WaitSelector", "WaitSelector": "#example"},
        {"Action": "Click", "Selector": "#example"},
        {"Action": "Execute", "Execute": "example"},
        {"Action": "ScreenShot", "fullScreenShot": False},
        {"Action": "Fill", "Selector": "#example", "Value": "example"},
        {"Action": "ScrollTo", "Selector": "#example"},
        {"Action": "ScrollX", "Value": 100},
        {"Action": "ScrollY", "Value": 100},
        {"Action": "WaitForRequestCompletion",
         "UrlPattern": "example.com",
         "Timeout": 10000
         }
    ])

    req_kwargs = {
        "url": "https://example.com/data",
        "super": True,
        "render": True,
        "device": "mobile",
        "session_id": 1234,
        "geo_code": "us",
        "postal_code": "90210",
        "wait_until": "networkidle0",
        "wait_selector": "#example",
        "custom_wait": 10000,
        "width": 1920,
        "height": 1080,
        "return_json": True,
        "block_resources": False,
        "screenshot": True,
        "play_with_browser": actions,
        "show_frames": True,
        "show_websocket_requests": True,
        "custom_headers": True,
        "disable_redirection": True,
        "timeout": 60000,
        "disable_retry": True,
        "output": "raw",
        "transparent_response": False,
        "pure_cookies": True
    }

    expected_params = {
        "url": "https://example.com/data",
        "super": "true",
        "render": "true",
        "device": "mobile",
        "sessionId": 1234,
        "geoCode": "us",
        "postalcode": "90210",
        "waitUntil": "networkidle0",
        "waitSelector": "#example",
        "customWait": 10000,
        "width": 1920,
        "height": 1080,
        "returnJSON": "true",
        "blockResources": "false",
        "screenShot": "true",
        "playWithBrowser": expected_actions_json,
        "showFrames": "true",
        "showWebsocketRequests": "true",
        "customHeaders": "true",
        "disableRedirection": "true",
        "timeout": 60000,
        "disableRetry": "true",
        "output": "raw",
        "transparentResponse": "false",
        "pureCookies": "true"
    }

    req = RequestParameters(**req_kwargs)
    assert req.to_api_params() == expected_params


def test_serialization_group_b_network():
    """
    Ensures alternative mutually exclusive parameters serialize correctly.
    """
    req_kwargs = {
        "url": "https://example.com/api",
        "super": True,
        "regional_geo_code": "europe",
        "retry_timeout": 15000,
        "set_cookies": "session=abc",
        "output": "markdown",
        "transparent_response": True
    }

    expected_params = {
        "url": "https://example.com/api",
        "super": "true",
        "regionalGeoCode": "europe",
        "retryTimeout": 15000,
        "setCookies": "session=abc",
        "output": "markdown",
        "transparentResponse": "true"
    }

    req = RequestParameters(**req_kwargs)
    assert req.to_api_params() == expected_params

# --- Headless Browser Dependency Tests ---


def test_render_dependency_failure():
    """
    Ensures render-dependent parameters crash if render=True is missing.
    """

    render_dependent_fields = [
        {"wait_until": "domcontentloaded"},
        {"custom_wait": 1000},
        {"wait_selector": "#example"},
        {"width": 1920},
        {"height": 1080},
        {"return_json": True},
        {"block_resources": True},
        {"screenshot": True},
        {"full_screenshot": True},
        {"particular_screenshot": "#example"},
        {"play_with_browser": [ClickAction(selector="#example")]},
        {"show_frames": True},
        {"show_websocket_requests": True}
    ]

    for field in render_dependent_fields:
        with pytest.raises(
            ValidationError,
            match="require 'render=true' to be set"
        ):
            RequestParameters(
                url="https://example.com",
                **field
            )


def test_return_json_dependency_failure():
    """
    Ensures specific fields crash if return_json=True is missing.
    """

    json_dependent_fields = [
        {"show_frames": True},
        {"show_websocket_requests": True},
        {"particular_screenshot": "#example"},
        {"full_screenshot": True},
        {"screenshot": True}
    ]

    for field in json_dependent_fields:
        with pytest.raises(
            ValidationError,
            match="require both 'render=true' AND 'returnJSON=true'"
        ):
            RequestParameters(
                url="https://example.com",
                render=True,
                **field
            )

# --- Mutually Exclusive Parameter Tests ---


def test_mutually_exclusive_headers():
    """
    Ensures the SDK rejects requests attempting to use conflicting header
    types.
    """
    header_fields = [
        {"custom_headers": True},
        {"extra_headers": True},
        {"forward_headers": True}
    ]

    header_combinations = [
        list(combo) for combo in combinations(header_fields, 2)
        ]

    for combo in header_combinations:
        kwargs = {v: k for d in combo for v, k in d.items()}
        with pytest.raises(
            ValidationError,
            match="Only one header parameter can be used"
        ):
            RequestParameters(
                url="https://example.com",
                **kwargs
            )


def test_render_and_retry_timeout_conflict():
    """
    Ensures retry_timeout is blocked when render=True.
    """
    with pytest.raises(
        ValidationError,
        match="cannot be used concurrently with 'render=true'"
    ):
        RequestParameters(
            url="https://example.com",
            render=True,
            retry_timeout=10000
        )


def test_screenshot_block_resources_conflict():
    """
    Ensures screenshot parameters are rejected if block_resources is active.
    """
    screenshot_fields = [
        {"screenshot": True},
        {"full_screenshot": True},
        {"particular_screenshot": "#exmaple"}
    ]

    for field in screenshot_fields:
        with pytest.raises(
            ValidationError,
            match="automatically operate with 'blockResources=false'"
        ):
            RequestParameters(
                url="https://example.com",
                render=True,
                return_json=True,
                block_resources=True,
                **field
            )


def test_multiple_screenshot_parameters_conflict():
    """
    Ensures only one screenshot method can be used at a time.
    """
    screenshot_fields = [
        {"screenshot": True},
        {"full_screenshot": True},
        {"particular_screenshot": "#exmaple"}
        ]
    screenshot_combinations = [
        list(combo) for combo in combinations(screenshot_fields, 2)
        ]

    for combo in screenshot_combinations:
        kwargs = {v: k for d in combo for v, k in d.items()}

        with pytest.raises(
            ValidationError,
            match="Only one screenshot parameter can be used at a time"
        ):
            RequestParameters(
                url="https://example.com",
                render=True,
                return_json=True,
                **kwargs
            )


def test_particular_screenshot_and_browser_conflict():
    """
    Ensures particular_screenshot cannot be combined with play_with_browser.
    """
    with pytest.raises(
        ValidationError,
        match="cannot be used concurrently with the 'playWithBrowser'"
    ):
        RequestParameters(
            url="https://example.com",
            render=True,
            return_json=True,
            particular_screenshot="#hero",
            play_with_browser=[ClickAction(selector="#btn")]
        )


def test_headers_and_cookies_conflict():
    """
    Ensures custom header routing does not conflict with explicit cookie
    injection.
    """

    header_fields = [
        {"custom_headers": True},
        {"extra_headers": True},
        {"forward_headers": True}
    ]

    for field in header_fields:
        with pytest.raises(
            ValidationError,
            match="cannot be used concurrently with the set_cookies parameter"
        ):
            RequestParameters(
                url="https://example.com",
                set_cookies="session=123",
                **field
            )


def test_regional_geo_code_and_geo_code_conflict():
    """
    Ensures specific country targeting and broad regional targeting are
    mutually exclusive.
    """
    with pytest.raises(
        ValidationError,
        match="parameters cannot be used simultaneously"
    ):
        RequestParameters(
            url="https://example.com",
            super=True,
            geo_code="us",
            regional_geo_code="northamerica"
        )


def test_regional_geo_code_requires_super():
    """
    Ensures regional routing fails if super proxy is not activated.
    """
    with pytest.raises(
        ValidationError,
        match="'super=true' must be set to use the 'regionalGeoCode' parameter"
    ):
        RequestParameters(
            url="https://example.com",
            super=False,
            regional_geo_code="europe"
        )

# --- Geo Targeting Tests ---


def test_geo_code_super_proxy_logic():
    """
    Ensures datacenter proxies reject super-proxy-only country codes.
    """
    only_super_codes = {
        c for c in _SUPER_SUPPORTED_COUNTRIES if c not in
        _DATACENTER_SUPPORTED_COUNTRIES
        }
    for code in _DATACENTER_SUPPORTED_COUNTRIES:
        RequestParameters(
            url="https://example.com",
            super=False,
            geo_code=code
            )

    for code in only_super_codes:
        with pytest.raises(
            ValidationError,
            match="not a supported country code when 'super=false'"
        ):
            RequestParameters(
                url="https://example.com",
                super=False,
                geo_code=code
            )

    invalid_iso_codes = ["aa", "zz", "qm", "qn", "qo", "qp", "qq", "qr"]

    for invalid_code in invalid_iso_codes:
        with pytest.raises(
            ValidationError,
            match="not a supported country code"
        ):
            RequestParameters(
                url="https://example.com",
                super=False,
                geo_code=invalid_code
            )

        with pytest.raises(
            ValidationError,
            match="not a supported country code"
        ):
            RequestParameters(
                url="https://example.com",
                super=True,
                geo_code=invalid_code
            )


def test_zipcode_missing_dependencies():
    """
    Ensures zipcode requires both super=True and a geo_code.
    """
    with pytest.raises(
        ValidationError,
        match=("can only be used when both 'super=true' and a valid 'geoCode'"
               " are provided"
               )
    ):
        RequestParameters(
            url="https://example.com",
            postal_code="90210"
        )


@pytest.mark.parametrize("geo_code, valid_zips, invalid_zips", [
    ("us", ["90210", "10001"], ["9021", "90210-1234", "ABCDE"]),
    ("gb", ["SW1A1AA", "EC1A 1BB", "E14", "M1"], ["S", "TOOLONGZIPCODE"]),
    ("de", ["10115", "80331"], ["1011", "101156", "ABCDE"]),
    ("fr", ["75001", "31000"], ["7500", "750012", "ABCDE"]),
    ("ca", ["M5V3L9", "V6B 1A1", "m5v 3l9"], ["12345", "M5V 3L", "M5V-3L9"]),
    ("au", ["2000", "3000"], ["200", "20001", "ABCD"]),
    ("in", ["110001", "400001"], ["11000", "1100012", "ABCDEF"]),
    ("nl", ["1012AB", "1012ab", "1000AA"], ["1012", "1012A", "1012ABC"]),
    ("it", ["00100", "20100"], ["0010", "001001", "ABCDE"]),
    ("es", ["28001", "08001"], ["2800", "280012", "ABCDE"]),
    ("br", ["01001", "01001000"], ["0100", "0100100", "ABCDE"]),
    ("jp", ["100-0001", "1000001"], ["100-000", "10-0001", "ABCDEFG"])
])
def test_comprehensive_zipcode_regex_validation(
    geo_code,
    valid_zips,
    invalid_zips
):
    """
    Ensures every supported country correctly accepts its valid postal code
    formats and strictly rejects invalid formats.
    """
    for valid_zip in valid_zips:
        RequestParameters(
            url="https://example.com",
            super=True,
            geo_code=geo_code,
            postal_code=valid_zip
        )

    for invalid_zip in invalid_zips:
        with pytest.raises(
            ValidationError,
            match="does not match the required pattern"
        ):
            RequestParameters(
                url="https://example.com",
                super=True,
                geo_code=geo_code,
                postal_code=invalid_zip
            )


def test_unsupported_zipcode_country_rejection():
    """
    Ensures that supplying a zip code for a country that is not mapped in
    _ZIPCODE_FORMATS throws the correct unsupported error.
    """
    supported_zip_code_countries = list(_ZIPCODE_FORMATS.keys())

    unsupported_code = [
        c for c in _SUPER_SUPPORTED_COUNTRIES
        if c not in supported_zip_code_countries
    ][0]

    with pytest.raises(
        ValidationError,
        match="Zip code targeting is not supported for country"
    ):
        RequestParameters(
            url="https://example.com",
            super=True,
            geo_code=unsupported_code,
            postal_code="12345"
        )

# --- Boundary Tests ---


def test_integer_boundary_constraints():
    """
    Ensures native ge/le limits correctly reject out-of-bounds integers.
    """
    boundary_fields = [
        {"timeout": 120001},
        {"timeout": 4999},
        {"custom_wait": 35001},
        {"custom_wait": -1},
        {"session_id": 1000001},
        {"session_id": -1},
        {"retry_timeout": 55001},
        {"retry_timeout": 4999}
    ]
    for field in boundary_fields:
        if "retry_timeout" in field:
            with pytest.raises(ValidationError):
                RequestParameters(
                    url="https://example.com",
                    **field
                    )
        else:
            with pytest.raises(ValidationError):
                RequestParameters(
                        url="https://example.com",
                        render=True,
                        **field
                        )
