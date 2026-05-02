import pytest
from scrape_do.models import ScrapeDoResponse
from scrape_do.exceptions import (
    APIResponseError,
    TargetError,
    AuthenticationError,
    AuthenticationThrottleError,
    RateLimitError,
    ServerError,
    BadRequestError
)

# --- Testing Exception Parsing & Properties ---


@pytest.mark.parametrize(
    "json_data, text_data, expected_message",
    [
        ({"errorMessage": "Node failed"}, None, "Node failed"),
        ({"detail": "Missing param"}, None, "Missing param"),
        ({"Message": "Capitalized"}, None, "Capitalized"),
        (
            None,
            "<html>Nginx 502 Bad Gateway</html>",
            "Unknown API Error. Body: <html>Nginx 502 Bad Gateway</html>"
            )
        ]
    )
def test_api_response_error_parsing(
    make_request,
    make_response,
    json_data, text_data,
    expected_message
):
    """
    Ensures the exception dynamically extracts Scrape.do's varying error keys,
    or falls back to text.
    """
    req = make_request()
    resp = make_response(500, json_data=json_data, text=text_data)
    scrape_resp = ScrapeDoResponse(req, resp)

    err = APIResponseError(
        raw_response=resp,
        request=req,
        response=scrape_resp
        )
    assert expected_message in err.message


@pytest.mark.parametrize(
    "status_code, expected_waf, expected_throttle",
    [(403, True, False),
     (401, True, False),
     (429, False, True),
     (404, False, False),
     ])
def test_target_error_flags(
    make_request,
    make_response,
    status_code,
    expected_waf,
    expected_throttle
):
    """
    Validates the programmatic helper flags on the TargetError class.
    """
    req = make_request()
    resp = make_response(200, proxy_status_header=str(status_code))

    err = TargetError(
        "Block",
        target_status_code=status_code,
        raw_response=resp,
        request=req
        )
    assert err.is_waf_block is expected_waf
    assert err.is_throttled is expected_throttle


# --- Testing the Routing Logic ---

@pytest.mark.parametrize(
    "raw_status, json_data, proxy_status_header, expected_exception",
    [
        # Target Errors
        (200, None, "403", TargetError),
        (200, None, "404", TargetError),
        # Proxy Gateway Errors
        (400, None, None, BadRequestError),
        (401, None, None, AuthenticationError),
        (429, None, None, RateLimitError),
        (502, None, None, ServerError),
        ]
    )
def test_raise_for_status_routing(
    make_request,
    make_response,
    raw_status,
    json_data,
    proxy_status_header,
    expected_exception
):
    """Ensures raise_for_status throws the correct exception based on the
    is_proxy_error heuristic.
    """
    req = make_request()
    resp = make_response(
        raw_status,
        json_data=json_data,
        proxy_status_header=proxy_status_header
        )
    scrape_resp = ScrapeDoResponse(req, resp)

    with pytest.raises(expected_exception):
        scrape_resp.raise_for_status()


def test_raise_for_status_auth_throttle_trap(make_request, make_response):
    """
    Ensures the specific text match for token throttling raises the correct
    subclass.
    """
    req = make_request()
    # Missing headers + 401 + specific text = Throttle Error
    resp = make_response(
        401,
        json_data={
            "message": ("You are temporarily throttled by the authentication"
                        " server."
                        )
            }
        )
    scrape_resp = ScrapeDoResponse(req, resp)

    with pytest.raises(AuthenticationThrottleError):
        scrape_resp.raise_for_status()
