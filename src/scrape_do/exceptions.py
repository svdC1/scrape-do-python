"""Custom exception hierarchy and network error routing for the Scrape.do SDK.

Dynamically parses API failures, distinguishes proxy infrastructure errors
from target website blocks, and exposes programmatic flags for retry
strategies.
"""

from __future__ import annotations
import httpx
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from scrape_do.models import PreparedScrapeDoRequest, ScrapeDoResponse


class ScrapeDoError(Exception):
    """The base exception for all errors raised by the SDK.

    Catching this exception guarantees that any error originating strictly
    from the SDK or the proxy network is handled.

    Args:
        message (str): Error message to be displayed
        request (Optional[PreparedScrapeDoRequest]): Object containing the
            request's information if it exists, otherwise `None`.
        response (Optional[ScrapeDoResponse]): Object containing the response's
            information if it exists, otherwise `None`
    """
    def __init__(
        self,
        message: str,
        request: Optional[PreparedScrapeDoRequest] = None,
        response: Optional[ScrapeDoResponse] = None
    ):
        super().__init__(message)
        self.message = message
        self.request = request
        self.response = response
        if response is not None:
            self.status_code = response.target_status_code


class APIConnectionError(ScrapeDoError):
    """Raised when the SDK fails to connect to the Scrape.do gateway entirely.

    This indicates a network-level failure such as DNS resolution issues,
    local internet outages, or hard socket timeouts.
    """


class TargetError(ScrapeDoError):
    """Raised when the Scrape.do proxy connects, but the target website fails.

    This exception is triggered when `transparent_response=True` is used,
    explicitly flagging that the destination URL returned a non-2xx status
    code.

    Args:
        message (str): The raw response body or error message from the target.
        target_status_code (int): The HTTP status code returned by the target
            website.
        raw_response (httpx.Response): The raw HTTP response object.
        request (Optional[PreparedScrapeDoRequest]): Object containing the
            request's information if it exists, otherwise `None`.
        response (Optional[ScrapeDoResponse]): Object containing the response's
            information if it exists, otherwise `None`
    """

    def __init__(
        self,
        message: str,
        target_status_code: int,
        raw_response: httpx.Response,
        request: Optional[PreparedScrapeDoRequest] = None,
        response: Optional[ScrapeDoResponse] = None
    ):
        self.target_status_code = target_status_code
        self.raw_response = raw_response
        super().__init__(
            f"Target website returned status {target_status_code}: {message}",
            request,
            response
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

    Args:
        raw_response (httpx.Response): The raw HTTP response object.
        request (Optional[PreparedScrapeDoRequest]): Object containing the
            request's information if it exists, otherwise `None`.
        response (Optional[ScrapeDoResponse]): Object containing the response's
            information if it exists, otherwise `None`
    """
    def __init__(
        self,
        raw_response: httpx.Response,
        request: Optional[PreparedScrapeDoRequest] = None,
        response: Optional[ScrapeDoResponse] = None
    ):
        msg = ("Your request has been temporarily throttled by the"
               "authentication server."
               )
        self.raw_response = raw_response

        super().__init__(msg, request, response)


class APIResponseError(ScrapeDoError):
    """Dynamically parses and represents a Scrape.do API infrastructure error.

    This acts as the base exception for all non-2xx HTTP responses returned
    by the Scrape.do gateway. It parses the JSON payloads to extract
    human-readable error messages.

    Args:
        raw_response (httpx.Response): The raw HTTP response object.
        request (Optional[PreparedScrapeDoRequest]): Object containing the
            request's information if it exists, otherwise `None`.
        response (Optional[ScrapeDoResponse]): Object containing the response's
            information if it exists, otherwise `None`
    """

    def __init__(
        self,
        raw_response: httpx.Response,
        request: Optional[PreparedScrapeDoRequest] = None,
        response: Optional[ScrapeDoResponse] = None
    ):
        self.raw_response = raw_response
        self.raw_status_code = raw_response.status_code
        self.message = f"Unknown API Error. Body: {raw_response.text}"

        # Attempt to parse known JSON keys
        try:
            data = raw_response.json()
            for key in ("detail",
                        "Error",
                        "errorMessage",
                        "message",
                        "Message"
                        ):
                if key in data and isinstance(data[key], str):
                    self.message = data[key]
                    break

        except ValueError:
            pass

        super().__init__(
            (
                f"API returned an error."
                f"Status: {self.raw_status_code} | Message: {self.message}"
                ),
            request,
            response
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


class RotatedSessionError(ScrapeDoError):
    """Raised when Scrape.do rotates the underlying proxy node for an active
    session.

    Args:
        raw_response (httpx.Response): The raw HTTPX response object
        request (PreparedScrapeDoRequest): The original request configuration.
        response (ScrapeDoResponse): The successful HTTP response containing
            the new RID state.
        last_known_rid (str): The RID found in the response of the last
            successful request made with the `request.api_params.session_id`
            parameter by the `ScrapeDoClient` instance before it raised the
            exception
    """
    def __init__(
        self,
        raw_response: httpx.Response,
        request: PreparedScrapeDoRequest,
        response: ScrapeDoResponse,
        last_known_rid: str,
        new_rid: str,
        session_id: int,
    ):
        self.new_rid = new_rid
        self.session_id = session_id
        self.last_known_rid = last_known_rid
        self.raw_response = raw_response
        msg = (f"The Scrape.do session for `sessionId={self.session_id}` has"
               f" expired | Last Known RID: {last_known_rid} | "
               f"Current RID: {self.new_rid}"
               )
        super().__init__(msg, request, response)
