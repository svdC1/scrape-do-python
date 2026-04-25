"""Custom exception hierarchy for the SDK

These exceptions translate generic HTTP errors into domain-specific,
catchable Python exceptions, allowing developers to implement granular
retry logic and error handling.
"""

from typing import Optional


class ScrapeDoError(Exception):
    """The base exception for all errors raised by the SDK.

    Catching this exception will catch any error originating from the SDK.
    """
    pass


class APIConnectionError(ScrapeDoError):
    """Raised when the SDK fails to connect to the Scrape.do API entirely.

    This indicates a network-level issue (e.g., DNS resolution failure,
    local internet outage, or a hard timeout) rather than an HTTP error.
    """
    pass


class APIResponseError(ScrapeDoError):
    """The base exception for all non-2xx responses from the Scrape.do API.

    Attributes:
        status_code (int): The HTTP status code returned by the API.
        response_body (str): The raw text of the API response.
        message (str): The parsed human-readable error message.
    """
    def __init__(
        self,
        status_code: int,
        response_body: str,
        message: Optional[str] = None
    ):
        default_msg = (
            f"Scrape.do API returned an error. "
            f"Status: {status_code} | Body: {response_body}"
            )
        msg = message or default_msg
        super().__init__(msg)
        self.status_code = status_code
        self.response_body = response_body
        self.message = msg


class AuthenticationError(APIResponseError):
    """Raised when the API returns a 401 Unauthorized.

    Indicates that the provided API token is missing, invalid, or expired.

    Attributes:
        status_code (int): The HTTP status code returned by the API.
        response_body (str): The raw text of the API response.
        message (str): The parsed human-readable error message.
    """
    def __init__(self, status_code: int, response_body: str):
        msg = "Authentication failed. Please verify your Scrape.do API token."
        super().__init__(
            status_code=status_code,
            response_body=response_body,
            message=msg
        )


class BadRequestError(APIResponseError):
    """Raised when the API returns a 400 Bad Request.

    Indicates that while the SDK's local validation passed, the Scrape.do
    servers rejected the request configuration or the target URL structure.
    """
    pass


class RateLimitError(APIResponseError):
    """Raised when the API returns a 429 Too Many Requests.

    Indicates that the account has exceeded its concurrent request limit
    or overall bandwidth quota.

    Attributes:
        status_code (int): The HTTP status code returned by the API.
        response_body (str): The raw text of the API response.
        message (str): The parsed human-readable error message.
    """
    def __init__(self, status_code: int, response_body: str):
        super().__init__(
            status_code,
            response_body,
            "Rate limit exceeded for Scrape.do account."
        )


class ServerError(APIResponseError):
    """Raised when the API returns a 5xx status code.

    Indicates a server-side issue at Scrape.do (e.g., proxy pool outage).
    """
    pass


class TargetError(ScrapeDoError):
    """Raised when Scrape.do connects, but the target website fails.
    This is commonly used when `transparent_response=True` is set and the
    target website returns a 403 Forbidden (proxy blocked) or 404 Not Found.

    Attributes:
        target_status_code (int): The HTTP status code returned by the target
            website.
        message (str): The parsed human-readable error message.
    """
    def __init__(self, target_status_code: int, message: str):
        self.target_status_code = target_status_code
        super().__init__(
            f"Target website returned status {target_status_code}: {message}"
            )
