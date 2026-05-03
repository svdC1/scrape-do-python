"""Serialization layer and HTTP transport preparation.

Bridges the gap between the strictly validated Pydantic models and the
underlying HTTP client. It wraps the API parameters, handles URL
encoding, manages payload typing, and injects authentication token
before network execution.
"""

from __future__ import annotations
import warnings
from typing import (
    Optional,
    Self,
    Any,
    Dict,
    Union
    )
from pydantic import (
    BaseModel,
    Field,
    model_validator,
    )
from .parameters import RequestParameters
from .enums import (
    PayloadType,
    HttpMethod
    )

# ------------------------
# PreparedScrapeDoRequest
# ------------------------


class PreparedScrapeDoRequest(BaseModel):
    """Represents a fully validated, ready-to-execute API call.

    info: Payload Type
        - If `payload_type='json'`, the `body` will be sent to
          `httpx.request()` through the `json` parameter

        - If `payload_type='raw'`, the `body` will be sent to
          `httpx.request()` through the `content` parameter

        - If `payload_type='form'` the `body` will be sent to
          `httpx.request()` through the `data` parameter

    Attributes:
        api_params (RequestParameters): Validated parameters to pass to the
            API
        method (HttpMethod): HTTP method to forward to the target website
        headers (Optional[Dict[str, str]]): Custom HTTP headers to forward
        body (Optional[Union[Dict[str, Any], str, bytes]]): Payload to send to
            the target website (JSON dict, string, or bytes)
        payload_type (PayloadType): Dictates how httpx should encode
            the body. Defaults to 'json'.
    """

    api_params: RequestParameters = Field(
        ...,
        description="The validated parameters to pass to the API. "
    )
    method: HttpMethod = Field(
        default="GET",
        description="The HTTP method to forward to the target website."
    )
    headers: Optional[Dict[str, str]] = Field(
        default=None,
        description="The HTTP headers to forward."
    )
    body: Optional[Union[Dict[str, Any], str, bytes]] = Field(
        default=None,
        description="The payload to send (JSON dict, string, or bytes)."
    )

    payload_type: PayloadType = Field(
        default="json",
        description="Dictates how httpx should encode the body."
    )

    @model_validator(mode="after")
    def cross_validate_http_components(self) -> Self:
        """Cross-references standard HTTP request components (Method, Headers,
        Body) against the Scrape.do specific parameters to ensure the
        configuration will be respected by the proxy network.

        info: Headers
            - Raises a ValueError if none of the header flags is set to
              true in `RequestParameters` and custom headers are provided

            - Raises a ValueError if one of the header flags are set to
              true in `RequestParameters` and no custom headers are
              provided

            - Raises a ValueError if `RequestParameters.extra_headers` is
              set to true and any of the provided headers don't start with
              the required `sd-` prefix.

        info: Method
            - Raises a ValueError if `RequestParameters.render` is set to
              true and `method != "GET"`

        info: Body
            - Emits a UserWarning if a `body` is provided and `method=GET`
              or `method=HEAD`

        Returns:
            The validated instance from which the method was called

        Raises:
            ValueError: If any of the validation steps fails
        """
        # --- Header Validation ---

        has_header_flag = (
                self.api_params.custom_headers or
                self.api_params.extra_headers or
                self.api_params.forward_headers
                )

        if self.headers:
            if not has_header_flag:
                raise ValueError((
                    "You provided 'headers' for the HTTP request, but no "
                    "header routing flag (custom_headers, extra_headers, or "
                    "forward_headers) was enabled in your RequestParameters. "
                    "Scrape.do will ignore these headers."
                    ))

            # Extra Headers Prefix Check
            if self.api_params.extra_headers:
                invalid_keys = [
                    k for k in self.headers.keys()
                    if not k.lower().startswith("sd-")
                ]
                if invalid_keys:
                    raise ValueError((
                        f"When 'extra_headers=True' is used, Scrape.do "
                        f"requires all injected headers to be prefixed with "
                        f"'sd-'. Invalid headers found: {invalid_keys}. "
                        ))
        else:
            if has_header_flag:
                raise ValueError((
                    "One of the header routing flags (custom_headers, "
                    "extra_headers, or forward_headers) is enabled in your "
                    "RequestParameters, but no 'headers' were provided"
                    ))

        # --- Headless Browser Method Constraint ---

        if self.api_params.render and self.method != "GET":
            raise ValueError((
                "The JavaScript render feature (render=true) works only with"
                " the 'GET' method."
                ))

        # --- Payload Type Validation ---
        if self.body is not None:
            if (
                self.payload_type in ("json", "form")
                and not isinstance(self.body, dict)
            ):
                raise ValueError(
                    f"When payload_type is '{self.payload_type}', "
                    f"the body must be a Python dictionary. "
                    f" Received: {type(self.body).__name__}."
                )
            if (
                self.payload_type == "raw"
                and not isinstance(self.body, (str, bytes))
            ):
                raise ValueError(
                    f"When payload_type is 'raw', "
                    f"the body must be a string or bytes. "
                    f"Received: {type(self.body).__name__}."
                )

        # --- Warnings ---

        # Body with GET/HEAD Warning
        if self.body is not None and self.method in ("GET", "HEAD"):
            warnings.warn((
                f"Providing a body payload with a {self.method} request "
                f"violates standard HTTP specifications and may be ignored by "
                f"the target website."
                ),
                UserWarning
                )

        return self

    def to_httpx_kwargs(self, token: Optional[str] = None) -> Dict[str, Any]:
        """Packages the validated object into a dictionary ready for httpx
        unpacking.

        info: Token
            The optional `token` parameter is the user's Scrape.do API key and
            is only added here only for convenience. It can also be manuall
            inserted into the resulting `httpx_kwargs` dictionary as the value
            to the `token` key if it isn't provided

        Args:
            token (Optional[str]): The Scrape.do API key to include in the
                dictionary

        Returns:
            Keyword arguments strictly formatted for `httpx.request()`.
        """

        params = self.api_params.to_api_params()

        if token is not None:
            params["token"] = token

        kwargs: Dict[str, Any] = {
            "method": self.method,
            "url": "https://api.scrape.do/",
            "params": params
        }

        if self.headers:
            kwargs["headers"] = self.headers

        if self.body is not None:
            if self.payload_type == "json":
                kwargs["json"] = self.body
            elif self.payload_type == "form":
                kwargs['data'] = self.body
            else:
                kwargs["content"] = self.body

        return kwargs
