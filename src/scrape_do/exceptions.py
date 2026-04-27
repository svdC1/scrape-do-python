"""Custom exception hierarchy and network error routing for the Scrape.do SDK.

Dynamically parses API failures, distinguishes proxy infrastructure errors
from target website blocks, and exposes programmatic flags for retry
strategies.
"""

import httpx


class ScrapeDoError(Exception):
    """The base exception for all errors raised by the SDK.

    Catching this exception guarantees that any error originating strictly
    from the SDK or the proxy network is handled.
    """
    pass


class APIConnectionError(ScrapeDoError):
    """Raised when the SDK fails to connect to the Scrape.do gateway entirely.

    This indicates a network-level failure such as DNS resolution issues,
    local internet outages, or hard socket timeouts.
    """
    pass


class TargetError(ScrapeDoError):
    """Raised when the Scrape.do proxy connects, but the target website fails.

    This exception is triggered when `transparent_response=True` is used,
    explicitly flagging that the destination URL returned a non-2xx status
    code.

    Args:
        target_status_code (int): The HTTP status code returned by the target
            website.
        message (str): The raw response body or error message from the target.
    """

    def __init__(self, target_status_code: int, message: str):
        self.target_status_code = target_status_code
        super().__init__(
            f"Target website returned status {target_status_code}: {message}"
            )

    @property
    def is_waf_block(self) -> bool:
        """
        Programmatic flag to identify if the target website blocked the proxy.

        Returns:
            `True` if status code is either `401` or `403`, `False` otherwise
        """
        return self.target_status_code in (401, 403)

    @property
    def is_throttled(self) -> bool:
        """
        Programmatic flag to identify target-level rate limiting.

        Returns:
            `True` if status code is `429`, `False` otherwise
        """
        return self.target_status_code == 429


class AuthenticationThrottleError(ScrapeDoError):
    """Raised when high-frequency invalid requests trigger an authentication
    ban.
    """
    pass


class APIResponseError(ScrapeDoError):
    """Dynamically parses and represents a Scrape.do API infrastructure error.

    This acts as the base exception for all non-2xx HTTP responses returned
    by the Scrape.do gateway. It parses the JSON payloads to extract
    human-readable error messages.

    Args:
        response (httpx.Response): The raw HTTP response object.
    """

    def __init__(self, response: httpx.Response):
        self.response = response
        self.status_code = response.status_code
        self.message = f"Unknown API Error. Body: {response.text}"

        # Attempt to parse known JSON keys
        try:
            data = response.json()
            for key in ("detail", "Error", "errorMessage", "message"):
                if key in data and isinstance(data[key], str):
                    self.message = data[key]
                    break

        except ValueError:
            pass

        super().__init__(
            f"API returned an error."
            f"Status: {self.status_code} | Message: {self.message}"
            )


# --- Specific API Response Subclasses ---

class AuthenticationError(APIResponseError):
    """Raised when the API returns an HTTP 401 (Unauthorized).

    Indicates that the provided API token is missing or invalid.
    """
    pass


class BadRequestError(APIResponseError):
    """Raised when the API returns an HTTP 400 (Bad Request).

    Indicates that the Scrape.do servers rejected the request configuration.
    """
    pass


class RateLimitError(APIResponseError):
    """Raised when the API returns an HTTP 429 (Too Many Requests).

    Indicates that the account has exceeded its concurrent request limit.
    """
    pass


class ServerError(APIResponseError):
    """Raised when the API returns an HTTP 500+ status code.

    Indicates a gateway failure or proxy pool outage.
    """
    pass
