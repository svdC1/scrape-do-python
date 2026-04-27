import pytest
import httpx
from scrape_do.exceptions import (
    APIResponseError,
    TargetError
    )


@pytest.mark.parametrize(
    "status_code, expected_waf, expected_throttle",
    [(200, False, False),
     (401, True, False),
     (403, True, False),
     (429, False, True),
     (500, False, False)
     ]
    )
def test_target_error_programmatic_flags(
    status_code,
    expected_waf,
    expected_throttle
):
    """
    Ensures TargetError correctly identifies WAF blocks and rate limits.
    """
    err = TargetError(
        target_status_code=status_code,
        message="Test Body"
        )

    assert err.target_status_code == status_code
    assert err.is_waf_block is expected_waf
    assert err.is_throttled is expected_throttle
    assert "status " + str(status_code) in str(err)


@pytest.mark.parametrize(
    "payload, expected_message",
    [({"detail": "Missing token."}, "Missing token."),
     ({"Error": "Invalid geoCode."}, "Invalid geoCode."),
     ({"errorMessage": "Timeout reached."}, "Timeout reached."),
     ({"UnknownKey": "Data"},
      'Unknown API Error. Body: {"UnknownKey":"Data"}'
      )
     ]
    )
def test_api_response_error_json_parsing(payload, expected_message):
    """
    Ensures the base APIResponseError dynamically extracts the
    human-readable message.
    """

    mock_response = httpx.Response(status_code=400, json=payload)

    err = APIResponseError(mock_response)

    assert err.status_code == 400
    assert err.message == expected_message


def test_api_response_error_non_json_fallback():
    """
    Ensures raw HTML/Text errors do not crash the JSON parser.
    """
    mock_response = httpx.Response(status_code=502,
                                   text="<html>Bad Gateway</html>"
                                   )

    err = APIResponseError(mock_response)

    assert err.status_code == 502
    assert "Unknown API Error. Body: <html>Bad Gateway</html>" in err.message
