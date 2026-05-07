"""Custom data models for the Scrape.do's API HTTP response

Encapsulates the httpx.Response object to provide a strongly-typed interface
for the respone data sent back by the Scrape.do API. It Parses nested JSON
payloads, extracts proxy telemetry, and attempts to determine whether non-2xx
responses are coming from the target website, or from Scrape.do's gateway
failures.
"""

from __future__ import annotations
from pathlib import Path
import os
import base64
import re
import httpx
from functools import cached_property
from typing import (
    Optional,
    Union,
    List,
    Self,
    Any,
    Dict
    )
from pydantic import (
    BaseModel,
    Field,
    HttpUrl,
    ConfigDict
    )
from .request import PreparedScrapeDoRequest
from ..exceptions import (
    APIResponseError,
    TargetError,
    BadRequestError,
    ServerError,
    AuthenticationError,
    AuthenticationThrottleError,
    RateLimitError
    )

# -------------------------
# JSON Response Info Models
# -------------------------


class ScrapeDoNetworkRequest(BaseModel):
    """Represents an intercepted HTTP network request made by the headless
    browser.

    When rendering JavaScript, the browser makes subsequent requests to fetch
    CSS, images, and background API data which Scrape.do returns in the
    `networkRequests` field when `returnJSON=true`

    Attributes:
        url (HttpUrl): The absolute URL of the requested resource.
        method (str): The HTTP method used (e.g., GET, POST).
        status (int): The HTTP status code returned by the resource server.
        request_headers (Dict[str, str]): The headers sent by the headless
            browser.
        request_body (Optional[str]): The payload sent with the request,
             if any.
        response_body (Optional[str]): The payload returned by the server,
             if captured.
        response_headers (Dict[str, str]): The headers returned by the
            resource server.
    """
    model_config = ConfigDict(populate_by_name=True)
    url: HttpUrl
    method: str
    status: int
    request_headers: Dict[str, str] = Field(default_factory=dict)
    request_body: Optional[str] = None
    response_body: Optional[str] = None
    response_headers: Dict[str, str] = Field(default_factory=dict)


class ScrapeDoWebSocketFrame(BaseModel):
    """Represents the underlying payload of an intercepted WebSocket message.

    Attributes:
        opcode (int): The WebSocket frame operation code
            (1 for text, 2 for binary).
        mask (bool): Indicates if the payload data is masked.
        payload_data (str): The actual message content transferred over the
            socket.
    """
    model_config = ConfigDict(populate_by_name=True)
    opcode: int
    mask: bool
    payload_data: str = Field(alias="payloadData")


class ScrapeDoWebSocketEvent(BaseModel):
    """Represents the Chrome DevTools Protocol (CDP) event metadata for a
    WebSocket.

    Attributes:
        request_id (str): The unique identifier for this specific
            WebSocket connection.
        timestamp (float): The exact epoch timestamp when the event occurred.
        response (ScrapeDoWebSocketFrame): The underlying frame containing the
            payload.
    """
    model_config = ConfigDict(populate_by_name=True)
    request_id: str = Field(alias="requestId")
    timestamp: float
    response: ScrapeDoWebSocketFrame


class ScrapeDoWebsocketRequest(BaseModel):
    """Represents a complete WebSocket message intercepted during rendering.

    Attributes:
        type (str): The direction of the traffic (e.g., "sent" or "received").
        event (ScrapeDoWebSocketEvent): The raw DevTools Protocol event data.
    """
    model_config = ConfigDict(populate_by_name=True)
    type: str
    event: ScrapeDoWebSocketEvent

    @property
    def is_text(self) -> bool:
        """Determines if the WebSocket payload is readable text.

        Returns:
            `True` if the underlying frame opcode is 1 (Text).
        """
        return self.event.response.opcode == 1


class ScrapeDoActionResult(BaseModel):
    """Represents the execution outcome of a specific programmatic browser
    action.

    Attributes:
        action (str): The name of the action executed (e.g., "Click", "Wait").
        index (int): The sequence index of this action in the original request
            array.
        success (bool): Indicates whether the action completed without
            throwing an error.
        error (Optional[str]): The error message if the action failed.
        response (Optional[Union[Dict[str, Any], str]]): Data returned by the
            action, typically populated when using the `ExecuteAction` to run
            custom JavaScript.
    """
    model_config = ConfigDict(populate_by_name=True)
    action: str
    index: int
    success: bool
    error: Optional[str] = None
    response: Optional[Union[Dict[str, Any], str]] = None


class ScrapeDoScreenshot(BaseModel):
    """Represents a captured screenshot generated during the scraping process.

    Attributes:
        screenshot_type (str): The configuration used (e.g., "FullScreenShot").
        b64_image (Optional[str]): The Base64 encoded string of the PNG image
            data.
        error (Optional[str]): The failure reason if the screenshot could not
            be captured.
    """
    model_config = ConfigDict(populate_by_name=True)
    screenshot_type: str = Field(alias="type")
    b64_image: Optional[str] = Field(alias="image", default=None)
    error: Optional[str] = None

    def to_bytes(self) -> bytes:
        """
        Convenience method to convert the `b64_image` string into a bytes
        object using the `base64` standard python library

        Raises:
            ValueError: If the instance's `b64_image` attribute is empty

        Returns:
            bytes object retuned by `base64.b64decode(b64_image)`
        """
        if not self.b64_image:
            raise ValueError(
                f"No image data was found in the screenshot response | "
                f"Screenshot Type: {self.screenshot_type} | "
                f"Error String: {self.error}"
                )

        return base64.b64decode(self.b64_image)

    def to_file(self, path: Union[str, os.PathLike]) -> Path:
        """
        Convenience method to save the base64-encoded screenshot

        warning: File Type
            Scrape.do returns base64-encoded `.png` image data, so `path`
            should end in `/file_name.png`

        Args:
            path (Union[str, os.PathLike]): Image file will be saved to this
                path

        Returns:
            resolved `pathlib.Path` object of the `path` parameter
        """
        r_path = Path(path).resolve()
        image_bytes = self.to_bytes()

        with open(r_path, "wb") as image:
            image.write(image_bytes)

        return r_path


class ScrapeDoFrame(BaseModel):
    """Represents an isolated, cross-origin iframe discovered on the target
    webpage.

    Attributes:
        url (HttpUrl): The absolute source URL of the iframe.
        content (Optional[str]): The rendered HTML content inside the iframe.
    """
    model_config = ConfigDict(populate_by_name=True)
    url: HttpUrl
    content: Optional[str] = None


# --------------------
# Main Response Model
# --------------------

class ScrapeDoResponse:
    """A unified data model for all HTTP responses returned by the Scrape.do
    API.

    This model encapsulates the underlying HTTPX network response to provide
    a flexible, strongly-typed interface.

    abstract: Different Response Types
        Because Scrape.do alters its response format based on the request
        parameters, this model attempts to route property access to the
        correct underlying data source.

    info: Additional Infomartion
        The following are some of the parameters that change the format of the
        HTTP response returned by Scrape.do.

        - `return_json=True` : Returns a JSON string containing information
          about the request instead of the target website's raw HTML

        - `transparent_response=True` : Causes the HTTP response returned by
          Scrape.do to mirror the exact status code of the HTTP response
          it got from the target website

        - `pure_cookies=True` : Tells Scrpe.do to return the original
          `Set-Cookie` headers it got from the target website instead of
          bundling them into its `scrape.do-cookies` response header

    Attributes:
        request (PreparedScrapeDoRequest): The original, validated request
            configuration.
        httpx_response (httpx.Response): The unmutated network response object.
        target_status_code (Optional[int]): The status code returned by the
            destination server.
        text (str): The primary payload of the target website
            (HTML or inner JSON string).
        target_headers (httpx.Headers): The target's headers, without
            proxy telemetry headers.
        cookies (Optional[httpx.Cookies]): Extracted cookies returned by the
            target.
        resolved_url (Optional[str]): The final destination URL after all
            redirects.
        target_url (Optional[str]): The original destination URL requested.
        scrape_do_status_code (Optional[int]): The status code of the
            Scrape.do gateway.
        request_cost (Optional[float]): API billing credits consumed by this
            specific execution.
        remaining_credits (Optional[float]): Total API billing credits
            remaining on your account.
        rid (Optional[str]): The specific proxy node Routing ID utilized
        rate (Optional[str]): Current rate limit metrics for the provided API
            token.
        request_id (Optional[str]): Unique UUID assigned to this request by
            the gateway.
        auth (Optional[int]): Authentication status against the
            Scrape.do gateway.
        initial_status_code (Optional[int]): Target's status extracted
            strictly from proxy headers.
        scrape_do_headers (httpx.Headers): Filtered headers containing only
             Scrape.do telemetry.
        frames (Optional[List[ScrapeDoFrame]]): Isolated cross-origin iframes
            discovered on the page.
        network_requests (Optional[List[ScrapeDoNetworkRequest]]): Background
            HTTP calls made by the browser.
        websocket_requests (Optional[List[ScrapeDoWebsocketRequest]]):
            Intercepted bidirectional WebSocket traffic.
        action_results (Optional[List[ScrapeDoActionResult]]): Execution
            outcomes of programmatic DOM actions.
        screenshots (Optional[List[ScrapeDoScreenshot]]): Captured Base64
            screenshots.
    """
    def __init__(
        self,
        request: PreparedScrapeDoRequest,
        response: httpx.Response
    ):
        # Raw Request and Response
        self._raw_request = request
        self._raw_response = response

        # Response Flags
        self._is_json = request.api_params.return_json
        self._is_transparent = request.api_params.transparent_response
        self._is_pure_cookies = request.api_params.pure_cookies

        # JSON Parsing
        self._parsed_json: Optional[Dict[str, Any]] = None
        if self._is_json:
            parsed = response.json()
            try:
                parsed = response.json()
                if isinstance(parsed, dict):
                    self._parsed_json = parsed
            except ValueError:
                # If Scrape.do crashed and returned HTML despite
                # returnJSON=True, we swallow the error here so the
                # `is_proxy_error` heuristic can properly route it as a
                # ServerError later.
                pass

    @cached_property
    def is_proxy_error(self) -> bool:
        """Heuristic to determine whether a non-2xx status code error
        is coming directly from the target website, or whether it's coming
        from the Scrape.do gateway

        info: Additional Information
            Scrape.do usually sends JSON error messages when there's an
            infrastructure error, so we try to parse the response's payload
            as JSON regardless of whether or not `return_json=True`.

            - IF `Payload Is Parsable JSON` :
                  - Check if the returned JSON contatins one of the standard
                    error keys (`message`, `Error`, `detail`, `Message`,
                    or `errorMessage`). If it does, then the error is coming
                    from Scrape.do, so return `True`

                  - Otherwise, check if the returned JSON contains the
                    `statusCode` key. If it does, and its value matches the
                    status code returned by the original httpx response, then
                    the error is probably coming from the `target website`, so
                    return `False`.

                  - If the value doesn't match or the `statusCode` key is
                    missing, fallback to `Payload Is Not Parsable JSON` logic.

            - IF `Payload Is Not Parsable JSON` :
                  - Scrape.do sends telemetry headers when a request is
                    successfuly completed, so if the response has the
                    `scrape.do-intial-status-code` header and its value is not
                    empty, the error is probably coming from the
                    `target website`, so return `False`. Otherwise, it's
                    probably a Scrape.do error, so return `True`

        info: `transparent_response=True`
            When `trasparent_response=True`, Scrape.do can still send its
            own error status codes when there's an infrastructure failure, so
            we can't rely on the `scrape_do_status_code` to determine where
            the error is coming from. With this in mind, this method aims
            to provide a solution by analysing the response's structure as a
            whole.

        Returns:
            `True` if it's a Scrape.do error, or `False` if it's a target
                website error
        """
        raw_status = self._raw_response.status_code
        has_intial_status_code = self.initial_status_code is not None
        parsed_json = None

        try:
            parsed_json = self._raw_response.json()
        except ValueError:
            pass

        if isinstance(parsed_json, dict):
            error_keys = [
                "message",
                "Error",
                "detail",
                "Message",
                "errorMessage"
                ]

            if any(k in parsed_json for k in error_keys):
                return True

            status_code_match = (
                "statusCode" in parsed_json
                and int(parsed_json["statusCode"]) == raw_status
                )

            if status_code_match:
                return False

        return not has_intial_status_code

    @property
    def httpx_response(self) -> httpx.Response:
        """Exposes the raw, underlying HTTPX response.

        info: Intended Usage
            Accessing this bypasses all SDK normalization. It's provided as an
            escape hatch for specific use cases where the original response
            object is needed.

        Returns:
            The raw httpx response object.
        """
        return self._raw_response

    @property
    def status_code(self) -> int:
        """Convenience accessor for the underlying HTTPX response status code.

        Equivalent to `response.httpx_response.status_code`. Distinct from
        `target_status_code` and `scrape_do_status_code`, which interpret the
        Scrape.do response envelope.

        Returns:
            The HTTP status code of the response received from `api.scrape.do`.
        """
        return self.httpx_response.status_code

    @property
    def request(self) -> PreparedScrapeDoRequest:
        """Exposes the original, validated request configuration.

        Returns:
            The `PreparedScrapeDoRequest` configuration that generated this
                response.
        """
        return self._raw_request

    @property
    def scrape_do_status_code(self) -> Optional[int]:
        """The HTTP status code returned by the Scrape.do gateway
        infrastructure.

        info: Transparent Response
            If `transparent_response=True` was used, the gateway hides its own
            status code, and this property will return `None`.

        Returns:
            The proxy gateway status code (e.g., 200, 429, 502).
        """
        if self._is_transparent:
            return None

        return self._raw_response.status_code

    @property
    def target_status_code(self) -> Optional[int]:
        """The HTTP status code returned by the destination website.

        info: Additional Information
            - If `self.is_proxy_error=True`, the target website was never
              reached, so return `None`

            - If `transparent_response=True`, the original status code from
              the httpx response is returned

            - If `return_json=True`, the `statusCode` field from the response's
              JSON is returned

            - If it's not a proxy error, and both parameters are set to false,
              the `ScrapeDoResponse.initial_status_code` property value is
              returned

        Returns:
            The target website's status code (e.g., 200, 403, 404).
        """
        if self.is_proxy_error:
            return None

        if self._is_transparent:
            return self._raw_response.status_code

        if self._parsed_json:
            return self._parsed_json.get("statusCode")

        return self.initial_status_code

    @property
    def text(self) -> str:
        """The primary textual payload of the target website.

        info: Additional Information
            Depending on the request parameters, this will return
            either the raw HTML byte stream or the extracted `content` string
            from within Scrape.do's JSON wrapper.

        Returns:
            The HTML or JSON string payload from the target.
        """
        if self._parsed_json:
            return self._parsed_json.get(
                "content",
                self._raw_response.text
                )

        return self._raw_response.text

    @property
    def target_headers(self) -> httpx.Headers:
        """The HTTP headers returned by the destination server.

        info: Additional Information
            This property automatically filters all internal `scrape.do-` proxy
            telemetry headers, providing a clean representation of
            the target's response.

        Returns:
            The filtered headers from the target website.
        """
        clean_headers = {
            k: v for k, v in self._raw_response.headers.items()
            if not k.lower().startswith("scrape.do-")
        }
        return httpx.Headers(clean_headers)

    # --- Scrape.do Headers ---

    @property
    def scrape_do_headers(self) -> Optional[httpx.Headers]:
        """Filters the response headers to isolate Scrape.do's specific
        infrastructure telemetry.

        Returns:
            Only headers prefixed with `scrape.do-`, or None if no
                `scrape.do-` headers are found
        """
        headers = {
            k: v for k, v in self._raw_response.headers.items()
            if k.lower().startswith("scrape.do-")
            }
        if not headers:
            return None
        return httpx.Headers(headers)

    @property
    def request_cost(self) -> Optional[float]:
        """The amount of API billing credits consumed by this specific
        execution.

        Returns:
            The value returned in the scapre_do_headers casted to a
                float, or `None` if the `scrape.do-request-cost`
                header is missing
        """
        cost = self._raw_response.headers.get("scrape.do-request-cost")
        return float(cost) if cost else None

    @property
    def initial_status_code(self) -> Optional[int]:
        """The target website's HTTP status code, extracted directly from the
        proxy headers.

        Returns:
            The status code casted to an int, or None if the
                `scrape.do-intial-status-code` header is missing.
        """
        initial_status_code = self._raw_response.headers.get(
            "scrape.do-initial-status-code"
            )

        return int(initial_status_code) if initial_status_code else None

    @property
    def request_id(self) -> Optional[str]:
        """The unique UUID assigned to this request by the Scrape.do gateway.

        Returns:
            The internal tracking ID, or None if the `scrape.do-request-id`
                header is missing
        """
        return self._raw_response.headers.get("scrape.do-request-id")

    @property
    def resolved_url(self) -> Optional[str]:
        """The final destination URL after all server-side and client-side
        redirects.

        Returns:
            The absolute URL where the browser ultimately landed, or None if
                the `scrape.do-resolved-url` header is missing
        """
        return self._raw_response.headers.get("scrape.do-resolved-url")

    @property
    def target_url(self) -> Optional[str]:
        """The original destination URL requested by the SDK.

        Returns:
            The initial target URL, or None if the `scrape.do-target-url`
                header is missing
        """
        return self._raw_response.headers.get("scrape.do-target-url")

    @property
    def auth(self) -> Optional[int]:
        """Indicates the authentication status against the Scrape.do gateway.

        Returns:
            The authentication flag value casted to an int, or None if the
                `scrape.do-auth` header is missing
        """
        auth = self._raw_response.headers.get("scrape.do-auth")
        return int(auth) if auth else None

    @property
    def rate(self) -> Optional[str]:
        """The current rate limit metrics for the provided API token.

        Returns:
            A string representing current concurrency thresholds, or None if
                the `scrape.do-rate` header is missing
        """
        return self._raw_response.headers.get("scrape.do-rate")

    @property
    def remaining_credits(self) -> Optional[float]:
        """The total number of API billing credits remaining on your account.

        Returns:
            The remaining account balance casted to a float, or None if the
                `scrape.do-remaining-credits` header is missing
        """
        remaining_credits = self._raw_response.headers.get(
            "scrape.do-remaining-credits"
            )

        return float(remaining_credits) if remaining_credits else None

    @property
    def rid(self) -> Optional[str]:
        """The specific proxy node Routing ID utilized for this connection.

        info: Session ID
            If `session_id` was provided in the parameters,
            this Routing ID is used by the `ScrapeDoClient` to verify that
            sticky sessions are maintaining the same node.

        Returns:
            The internal routing identifier, or None if the `scrape.do-rid`
                header is missing
        """
        return self._raw_response.headers.get("scrape.do-rid")

    @property
    def cookies(self) -> Optional[httpx.Cookies]:
        """Extracts and parses cookies returned by the target server.

        info: Additional Information
            If `pure_cookies=True` is active, it returns the httpx response's
            `cookies` attribute. Otherwise, it decodes the custom
            `scrape.do-cookies` string into a `httpx.Cookies` object

        Returns:
            A `httpx.Cookies` object containing all cookies.
        """
        if self._is_pure_cookies:
            return self._raw_response.cookies

        cookies = self._raw_response.headers.get("scrape.do-cookies")
        if cookies:
            # Parse Cookies (c1=v1;c2=v2;...)
            pattern = re.compile(r"([^=;]+)=([^;]*)")
            matches = re.findall(pattern, cookies)
            if not matches:
                return None
            cookie_dict = {n: v for n, v in matches}
            return httpx.Cookies(cookie_dict)

        return None

    # --- Scrape.do JSON ---

    @property
    def frames(self) -> Optional[List[ScrapeDoFrame]]:
        """Extracts isolated cross-origin iframes discovered during page
        rendering.

        info: Prerequisites
            Requires `render=True`, `return_json=True`, and `show_frames=True`

        Returns:
            A list of typed Pydantic models representing frames.
        """
        if self._parsed_json and "frames" in self._parsed_json:
            return [
                ScrapeDoFrame(**f) for f in self._parsed_json["frames"]
                ]
        return None

    @property
    def network_requests(self) -> Optional[List[ScrapeDoNetworkRequest]]:
        """Intercepts background network traffic triggered by the headless
        browser.

        info: Prerequisites
            Requires `render=True` and `return_json=True`.

        Returns:
            A list of typed models detailing HTTP calls.
        """
        if self._parsed_json and "networkRequests" in self._parsed_json:
            return [
                ScrapeDoNetworkRequest(**nr) for nr
                in self._parsed_json["networkRequests"]
                ]
        return None

    @property
    def websocket_requests(self) -> Optional[List[ScrapeDoWebsocketRequest]]:
        """Intercepts bidirectional WebSocket traffic initiated by the target
        website.

        info: Prerequisites
            Requires `render=True`, `return_json=True`, and
            `show_websocket_requests=True`

        Returns:
            A list of typed models detailing socket events.
        """
        if self._parsed_json and "websocketRequests" in self._parsed_json:
            return [
                ScrapeDoWebsocketRequest(**ws) for ws
                in self._parsed_json["websocketRequests"]
                ]
        return None

    @property
    def action_results(self) -> Optional[List[ScrapeDoActionResult]]:
        """Details the success or failure of programmatic DOM interactions.

        Returns:
            A list of typed models mapping sequentially to the actions defined
                in the `play_with_browser` array.
        """
        if self._parsed_json and "actionResults" in self._parsed_json:
            return [
                ScrapeDoActionResult(**ar) for ar
                in self._parsed_json["actionResults"]
                ]
        return None

    @property
    def screenshots(self) -> Optional[List[ScrapeDoScreenshot]]:
        """Extracts generated Base64 screenshots from the JSON payload.

        info: Prerequisites
            Requires `render=True`, `return_json=True`, and a valid screenshot
            parameter (e.g., `full_screenshot=True`).

        Returns:
            A list of typed models containing the image data.
        """
        if self._parsed_json and "screenShots" in self._parsed_json:
            return [
                ScrapeDoScreenshot(**s) for s in
                self._parsed_json["screenShots"]
                ]
        return None

    def raise_for_status(self) -> Self:
        """Evaluates the response and raises a mapped exception if the request
        failed.

        info: Additional Information
            Utilizes the `is_proxy_error` heuristic to determine if
            the failure originated from the Scrape.do proxy infrastructure or
            from the target website.

        Returns:
            The current `ScrapeDoResponse` instance,
                allowing for method chaining.

        Raises:
            TargetError: If the proxy succeeded, but the target website
                returned an error code (e.g., a 403 Cloudflare block or a 404
                Not Found).
            BadRequestError: If the request was malformed
                (HTTP 400 from Scrape.do).
            AuthenticationError: If your Scrape.do API token is invalid
                (HTTP 401).
            AuthenticationThrottleError: If your specific token has been
                temporarily locked by the Scrape.do authentication server to
                prevent abuse. (HTTP 401)
            RateLimitError: If you exceed your account's concurrent request
                limit (HTTP 429).
            ServerError: If the Scrape.do gateway experiences an issue
                (HTTP 502/510).
            APIResponseError: A generic fallback for unmapped Scrape.do proxy
                errors.
        """

        if self.target_status_code and self.target_status_code < 400:
            return self

        # Checks if it's an Authentication Throttle Error
        error_msg = None
        if self._parsed_json:
            error_keys = [
                "message",
                "Error",
                "detail",
                "Message",
                "errorMessage"
                ]

            for k in error_keys:
                if k in self._parsed_json:
                    error_msg = self._parsed_json[k]
                    break

        elif self.text:
            error_msg = self.text

        is_throttled = None
        throttled_msg = "temporarily throttled by the authentication server"
        if error_msg and throttled_msg in error_msg:
            is_throttled = True

        raw_status = self._raw_response.status_code

        # Route to Proxy Infrastructure Errors
        if self.is_proxy_error:

            if raw_status == 400:
                raise BadRequestError(
                    self._raw_response,
                    self._raw_request,
                    self
                    )

            elif raw_status == 401:
                if is_throttled:
                    raise AuthenticationThrottleError(
                        self._raw_response,
                        self._raw_request,
                        self
                        )

                raise AuthenticationError(
                    self._raw_response,
                    self._raw_request,
                    self
                    )

            elif raw_status == 429:
                raise RateLimitError(
                    self._raw_response,
                    self._raw_request,
                    self
                    )
            elif raw_status in (502, 510):
                raise ServerError(
                    self._raw_response,
                    self._raw_request,
                    self
                    )

            raise APIResponseError(
                self._raw_response,
                self._raw_request,
                self
                )

        # If is_proxy_error is False, then it's a TargetError

        status_code = self.target_status_code or self._raw_response.status_code
        raise TargetError(
            (f"Target rejected request with status: "
             f"{status_code}"
             ),
            status_code,
            self._raw_response,
            self._raw_request,
            self
            )
