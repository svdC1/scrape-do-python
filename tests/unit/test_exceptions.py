import pytest
from scrape_do.models import ScrapeDoResponse
from scrape_do.exceptions import (
    APIResponseError,
    TargetError,
    AuthenticationError,
    AuthenticationThrottleError,
    RateLimitError,
    ServerError,
    BadRequestError,
    RotatedSessionError,
    ScrapeDoJSONErrorMessage
)

pytestmark = pytest.mark.unit

# --- Testing Exception Parsing & Properties ---


@pytest.mark.parametrize(
    "json_data, text_data, expected_substrings",
    [
        # Full Scrape.do error envelope: each labeled field surfaces.
        (
            {
                "StatusCode": 500,
                "Message": ["Node failed"],
                "URL": "https://example.com",
                "PossibleCauses": ["Network glitch"],
                "ErrorType": "ProxyFailure",
                "ErrorCode": 42,
                "Contact": "support@scrape.do",
                },
            None,
            ["Node failed", "ProxyFailure", "42", "support@scrape.do"]
            ),
        # Partial envelope: only Message + ErrorCode set, others default.
        (
            {"Message": ["Missing param"], "ErrorCode": 7},
            None,
            ["Missing param", "Error Code : 7"]
            ),
        # Non-error JSON body: falls back to "Unknown API Error" multi-line.
        (
            None,
            "<html>Nginx 502 Bad Gateway</html>",
            [
                "Unknown API Error",
                "Status: 500",
                "<html>Nginx 502 Bad Gateway</html>",
                ]
            ),
        ]
    )
def test_api_response_error_parsing(
    make_request,
    make_response,
    json_data, text_data,
    expected_substrings
):
    """
    Ensures the exception extracts the Scrape.do error envelope when the
    body matches the canonical schema, and falls back to a multi-line
    "Unknown API Error" message otherwise.
    """
    req = make_request()
    resp = make_response(500, json_data=json_data, text=text_data)
    scrape_resp = ScrapeDoResponse(req, resp)

    err = APIResponseError(
        raw_response=resp,
        request=req,
        response=scrape_resp
        )
    for substring in expected_substrings:
        assert substring in err.message


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
        (503, None, None, APIResponseError)
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
    """
    Ensures raise_for_status throws the correct exception based on the
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
    # Missing headers + 401 + canonical Scrape.do envelope with the
    # throttle phrase in `Message` -> Throttle Error
    resp = make_response(
        401,
        json_data={
            "Message": [
                "You are temporarily throttled by the authentication"
                " server."
                ]
            }
        )
    scrape_resp = ScrapeDoResponse(req, resp)

    with pytest.raises(AuthenticationThrottleError):
        scrape_resp.raise_for_status()


def test_rotated_session_error_init(make_request, make_response):
    """
    Ensures RotatedSessionError is properly initialized with the
    user-defined session_validator signature.
    """

    req = make_request()
    resp = make_response(200)
    scrape_do_resp = ScrapeDoResponse(req, resp)
    err = RotatedSessionError(
        "Session Expired",
        resp,
        req,
        scrape_do_resp
        )

    assert err.message == "Session Expired"
    assert err.raw_response is resp
    assert err.request is req
    assert err.response is scrape_do_resp


# --- Testing ScrapeDoJSONErrorMessage ---


class TestScrapeDoJSONErrorMessage:

    def test_try_from_response_full_envelope(self, make_response):
        """Full Scrape.do error envelope parses every field through
        camelCase aliases into snake_case attributes."""
        resp = make_response(
            500,
            json_data={
                "StatusCode": 502,
                "Message": ["Upstream failed", "Retry later"],
                "URL": "https://example.com",
                "PossibleCauses": ["Network glitch"],
                "ErrorType": "ProxyFailure",
                "ErrorCode": 42,
                "Contact": "support@scrape.do",
                }
            )

        err = ScrapeDoJSONErrorMessage.try_from_response(resp)

        assert err is not None
        assert err.status_code == 502
        assert err.messages == ["Upstream failed", "Retry later"]
        assert err.url == "https://example.com"
        assert err.possible_causes == ["Network glitch"]
        assert err.error_type == "ProxyFailure"
        assert err.error_code == 42
        assert err.contact == "support@scrape.do"

    def test_try_from_response_partial_envelope(self, make_response):
        """Only Message + ErrorCode set; defaults fill the rest."""
        resp = make_response(
            500, json_data={"Message": ["solo"], "ErrorCode": 7}
            )

        err = ScrapeDoJSONErrorMessage.try_from_response(resp)

        assert err is not None
        assert err.messages == ["solo"]
        assert err.error_code == 7
        assert err.status_code is None
        assert err.url is None
        assert err.possible_causes == []
        assert err.error_type is None
        assert err.contact is None

    def test_try_from_response_ignores_extra_fields(self, make_response):
        """`extra="ignore"` lets new Scrape.do fields pass through
        without raising ValidationError."""
        resp = make_response(
            500,
            json_data={
                "Message": ["text"],
                "BrandNewServerField": "ignored",
                }
            )

        err = ScrapeDoJSONErrorMessage.try_from_response(resp)
        assert err is not None
        assert err.messages == ["text"]

    def test_try_from_response_returns_none_on_non_json(self, make_response):
        """Non-JSON body -> None (never raises)."""
        resp = make_response(500, text="<html>plain HTML</html>")
        assert ScrapeDoJSONErrorMessage.try_from_response(resp) is None

    def test_try_from_response_returns_none_on_non_dict(self, make_response):
        """JSON list body -> None."""
        resp = make_response(500, json_data=["a", "b"])
        assert ScrapeDoJSONErrorMessage.try_from_response(resp) is None

    def test_try_from_response_returns_none_on_only_statuscode(
        self, make_response
    ):
        """`StatusCode` alone isn't a reliable error signal - returnJSON
        success bodies have it too. Require at least one error-specific
        key."""
        resp = make_response(200, json_data={"StatusCode": 200})
        assert ScrapeDoJSONErrorMessage.try_from_response(resp) is None

    def test_try_from_response_returns_none_on_validation_error(
        self, make_response
    ):
        """Schema mismatch (Message must be list, got int) -> None
        rather than ValidationError bubbling out."""
        resp = make_response(500, json_data={"Message": 42})
        assert ScrapeDoJSONErrorMessage.try_from_response(resp) is None

    def test_str_includes_all_labels(self, make_response):
        """str() includes every field label and value."""
        resp = make_response(
            500,
            json_data={
                "StatusCode": 502,
                "Message": ["err"],
                "URL": "https://example.com",
                "PossibleCauses": ["bad"],
                "ErrorType": "T1",
                "ErrorCode": 99,
                "Contact": "support@scrape.do",
                }
            )
        err = ScrapeDoJSONErrorMessage.try_from_response(resp)
        rendered = str(err)

        assert "Status Code : 502" in rendered
        assert "Messages : err" in rendered
        assert "URL : https://example.com" in rendered
        assert "Possible Causes: bad" in rendered
        assert "Error Type : T1" in rendered
        assert "Error Code : 99" in rendered
        assert "Contact : support@scrape.do" in rendered

    def test_str_with_empty_messages_renders_unknown(self):
        """When `messages` is empty (envelope had no `Message` key,
        or it was an empty list), `__str__` falls back to the
        "Unknown API Error" placeholder rather than rendering an empty
        joined string."""
        err = ScrapeDoJSONErrorMessage(error_code=1)
        rendered = str(err)
        assert "Messages : Unknown API Error" in rendered

    def test_is_auth_throttle_positive(self, make_response):
        """Throttle phrase in messages -> True."""
        resp = make_response(
            401,
            json_data={
                "Message": [
                    "Hey, you are temporarily throttled by the "
                    "authentication server, slow down."
                    ]
                }
            )
        err = ScrapeDoJSONErrorMessage.try_from_response(resp)
        assert err is not None
        assert err.is_auth_throttle is True

    def test_is_auth_throttle_negative(self, make_response):
        """Different message -> False."""
        resp = make_response(401, json_data={"Message": ["Bad token"]})
        err = ScrapeDoJSONErrorMessage.try_from_response(resp)
        assert err is not None
        assert err.is_auth_throttle is False

    def test_is_auth_throttle_empty_messages(self, make_response):
        """No messages -> False (no crash on empty list)."""
        resp = make_response(401, json_data={"ErrorCode": 1})
        err = ScrapeDoJSONErrorMessage.try_from_response(resp)
        assert err is not None
        assert err.messages == []
        assert err.is_auth_throttle is False
