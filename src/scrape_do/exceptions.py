"""Custom exception hierarchy and network error routing for the Scrape.do SDK.

Dynamically parses API failures, distinguishes proxy infrastructure errors
from target website blocks, and exposes programmatic flags for retry
strategies.
"""

from __future__ import annotations
import httpx
from typing import List, Optional, TYPE_CHECKING
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from .constants import _EXPECTED_ERROR_KEYS
if TYPE_CHECKING:
    from .models import PreparedScrapeDoRequest, ScrapeDoResponse


class ScrapeDoJSONErrorMessage(BaseModel):
    """Structured representation of a Scrape.do JSON error envelope.

    abstract: API Response Errors
        For `APIResponseErrors`, `Scrape.do` returns a JSON body containing
        information about what went wrong. This model unifies access to those
        responses and drives exception routing.

    warning: Not Official
        - The schema was reconstructed from manual testing against the
          `Scrape.do API`

        - New keys are silently ignored (`extra="ignore"`) so server-side
          additions don't break parsing

        - Missing keys fall back to their defaults.
    """
    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    status_code: Optional[int] = Field(default=None, alias="StatusCode")
    messages: List[str] = Field(default_factory=list, alias="Message")
    url: Optional[str] = Field(default=None, alias="URL")
    possible_causes: List[str] = Field(
        default_factory=list, alias="PossibleCauses"
        )
    error_type: Optional[str] = Field(default=None, alias="ErrorType")
    error_code: Optional[int] = Field(default=None, alias="ErrorCode")
    contact: Optional[str] = Field(default=None, alias="Contact")

    @classmethod
    def try_from_response(
        cls,
        raw_resp: httpx.Response,
    ) -> Optional[ScrapeDoJSONErrorMessage]:
        """Parse a Scrape.do error envelope, or return None if the
        response doesn't look like one.

        Args:
            raw_resp (httpx.Response): The raw `httpx.Response` object.

        Returns:
            A `ScrapeDoJSONErrorMessage` when the response body parses
                as a JSON dict containing at least one Scrape.do error key
                and pydantic validation succeeds. `None` otherwise. Never
                raises.
        """
        try:
            data = raw_resp.json()
        except ValueError:
            return None

        if not isinstance(data, dict):
            return None

        # StatusCode appears in success bodies too (e.g. returnJSON=true),
        # so it's not a reliable error signal. Require at least one of
        # the error-specific keys.
        keys = _EXPECTED_ERROR_KEYS - {"StatusCode"}
        if not any(k in data for k in keys):
            return None

        try:
            return cls.model_validate(data)
        except ValidationError:
            return None

    def __str__(self) -> str:
        """Generates a human-readable rendering for inclusion in
        exception messages.

        Returns:
            A multi-line string with all fields labeled.
        """
        status = f"Status Code : {self.status_code}"
        url = f"URL : {self.url or 'None'}"

        if self.possible_causes:
            causes = f"Possible Causes: {'|'.join(self.possible_causes)}"
        else:
            causes = "Possible Causes: None"

        if self.messages:
            msg = f"Messages : {'|'.join(self.messages)}"
        else:
            msg = "Messages : Unknown API Error"

        _type = f"Error Type : {self.error_type or 'None'}"
        code = f"Error Code : {self.error_code or 'None'}"
        contact = f"Contact : {self.contact or 'None'}"

        return (
            f"API Response Error\n{status}\n{msg}\n{url}\n{causes}\n{_type}"
            f"\n{code}\n{contact}"
            )

    @property
    def is_auth_throttle(self) -> bool:
        """Whether the envelope's messages match Scrape.do's
        authentication-throttle phrase.

        Returns:
            `True` if any of `messages` contains the throttle substring,
                `False` otherwise.
        """
        throttle_msg = "temporarily throttled by the authentication server"
        if not self.messages:
            return False
        return throttle_msg in ";".join(self.messages)


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

        error_info = ScrapeDoJSONErrorMessage.try_from_response(raw_response)
        if error_info is not None:
            self.message = str(error_info)
        else:
            self.message = (f"Unknown API Error\n"
                            f"Status: {raw_response.status_code}\n"
                            f"Body: {raw_response.text}"
                            )

        super().__init__(
            self.message,
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
    """
    Raised when a user-defined `session_validator` determines that the target
    website's state has been lost (e.g., logged out, CAPTCHA triggered),
    indicating that Scrape.do silently rotated the proxy exit node.

    Args:
        message (str): Error message to be displayed
        raw_response (httpx.Response): The raw HTTP response object.
        request (PreparedScrapeDoRequest): Object containing the
            request's information
        response (Optional[ScrapeDoResponse]): Object containing the response's
            information
    """
    def __init__(
        self,
        message: str,
        raw_response: httpx.Response,
        request: PreparedScrapeDoRequest,
        response: ScrapeDoResponse
    ):
        self.raw_response = raw_response
        super().__init__(message, request, response)
