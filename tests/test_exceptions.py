from scrape_do.exceptions import (
    ScrapeDoError,
    APIConnectionError,
    APIResponseError,
    AuthenticationError,
    BadRequestError,
    RateLimitError,
    ServerError,
    TargetError
)


def test_exception_inheritance_tree():
    """
    Ensures all network exceptions properly inherit from the base
    ScrapeDoError.
    """
    assert issubclass(APIConnectionError, ScrapeDoError)
    assert issubclass(APIResponseError, ScrapeDoError)
    assert issubclass(TargetError, ScrapeDoError)
    assert issubclass(AuthenticationError, APIResponseError)
    assert issubclass(BadRequestError, APIResponseError)
    assert issubclass(RateLimitError, APIResponseError)
    assert issubclass(ServerError, APIResponseError)


def test_api_response_error_instantiation():
    """
    Ensures standard API errors capture the response data correctly.
    """
    err = APIResponseError(
        status_code=400,
        response_body='{"Success": false}',
        message="Bad Target"
        )

    err2 = RateLimitError(
        status_code=429,
        response_body='{"Success": false}'
    )

    assert err.status_code == 400
    assert err.response_body == '{"Success": false}'
    assert err.message == "Bad Target"
    assert "Bad Target" in str(err)
    assert err2.status_code == 429
    assert err2.response_body == '{"Success": false}'


def test_authentication_error_default_message():
    """
    Ensures specific API errors apply their default human-readable messages.
    """
    err = AuthenticationError(
        status_code=401,
        response_body='Unauthorized'
        )
    assert err.status_code == 401
    assert "Authentication failed" in err.message


def test_target_error_instantiation():
    """
    Ensures TargetError uniquely tracks the target's status code,
    not Scrape.do's."
    """
    err = TargetError(
        target_status_code=403,
        message="Cloudflare Blocked"
        )
    assert err.target_status_code == 403
    assert "status 403" in str(err)
