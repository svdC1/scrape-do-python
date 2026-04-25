"""Data models and API contracts

This module utilizes Pydantic V2 to enforce Scrape.do's complex routing rules,
parameter dependencies, and geographical targeting constraints locally,
ensuring that invalid configurations are caught before a network request is
generated.
"""

from __future__ import annotations
import json
import warnings
from typing import (Annotated,
                    Literal,
                    Optional,
                    Union,
                    List,
                    Self,
                    Type,
                    Any,
                    TypeAlias,
                    Dict
                    )
from pydantic import (BaseModel,
                      Field,
                      HttpUrl,
                      model_validator,
                      field_validator,
                      ValidationInfo,
                      ConfigDict
                      )
from scrape_do.constants import (
    _SUPER_SUPPORTED_COUNTRIES,
    _DATACENTER_SUPPORTED_COUNTRIES,
    _ZIPCODE_FORMATS
    )

# -------------------------------------------------------------------
# Browser Action Models
# -------------------------------------------------------------------


class ClickAction(BaseModel):
    """Executes a click event on a specified CSS selector.

    Attributes:
        action (Literal["Click"]): The literal action identifier.
        selector (str): The CSS selector of the target element.
    """
    model_config = ConfigDict(
        populate_by_name=True
        )

    action: Literal["Click"] = Field(
        "Click",
        alias="Action"
        )
    selector: str = Field(
        ...,
        alias="Selector",
        min_length=1
        )


class WaitAction(BaseModel):
    """Pauses browser execution for a specific duration.

    Attributes:
        action (Literal["Wait"]): The literal action identifier.
        timeout (int): Number of milliseconds to wait.
    """
    model_config = ConfigDict(
        populate_by_name=True
        )

    action: Literal["Wait"] = Field(
        "Wait",
        alias="Action"
        )
    timeout: int = Field(
        ...,
        alias="Timeout",
        description="Number of miliseconds to wait",
        ge=0
        )


class WaitSelectorAction(BaseModel):
    """Pauses browser execution until a specific element appears in the DOM.

    Attributes:
        action (Literal["WaitSelector"]): The literal action identifier.
        wait_selector (str): The CSS selector to wait for.
        timeout (int, optional): Maximum time to wait in milliseconds.
            Defaults to None.
    """
    model_config = ConfigDict(
        populate_by_name=True
        )

    action: Literal["WaitSelector"] = Field(
        "WaitSelector",
        alias="Action"
        )
    wait_selector: str = Field(
        ...,
        alias="WaitSelector",
        min_length=1
        )
    timeout: Optional[int] = Field(
        None,
        alias="Timeout",
        description="Number of miliseconds to wait",
        ge=0
        )


class ScrollXAction(BaseModel):
    """Scrolls the viewport horizontally.

    Attributes:
        action (Literal["ScrollX"]): The literal action identifier.
        value (int): Number of pixels to scroll along the X-axis.
    """
    model_config = ConfigDict(
        populate_by_name=True
        )

    action: Literal["ScrollX"] = Field(
        "ScrollX",
        alias="Action"
        )
    value: int = Field(
        ...,
        alias="Value",
        description="Number of pixels to scroll"
        )


class ScrollYAction(BaseModel):
    """Scrolls the viewport vertically.

    Attributes:
        action (Literal["ScrollY"]): The literal action identifier.
        value (int): Number of pixels to scroll along the Y-axis.
    """
    model_config = ConfigDict(
        populate_by_name=True
        )

    action: Literal["ScrollY"] = Field(
        "ScrollY",
        alias="Action"
        )
    value: int = Field(
        ...,
        alias="Value",
        description="Number of pixels to scroll"
        )


class ScrollToAction(BaseModel):
    """Scrolls the viewport until a specific element is visible.

    Attributes:
        action (Literal["ScrollTo"]): The literal action identifier.
        selector (str): The CSS selector of the element to scroll to.
    """
    model_config = ConfigDict(
        populate_by_name=True
        )

    action: Literal["ScrollTo"] = Field(
        "ScrollTo",
        alias="Action"
        )
    selector: str = Field(
        ...,
        alias="Selector",
        min_length=1
        )


class FillAction(BaseModel):
    """Types a specified value into an input field.

    Attributes:
        action (Literal["Fill"]): The literal action identifier.
        selector (str): The CSS selector of the input element.
        value (str): The text string to type into the element.
    """
    model_config = ConfigDict(
        populate_by_name=True
        )

    action: Literal["Fill"] = Field(
        "Fill",
        alias="Action"
        )
    selector: str = Field(
        ...,
        alias="Selector",
        min_length=1
        )
    value: str = Field(
        ...,
        alias="Value"
        )


class ExecuteAction(BaseModel):
    """Executes arbitrary JavaScript within the browser context.

    Attributes:
        action (Literal["Execute"]): The literal action identifier.
        execute (str): The raw JavaScript code to evaluate.
    """
    model_config = ConfigDict(
        populate_by_name=True
        )

    action: Literal["Execute"] = Field(
        "Execute",
        alias="Action"
        )
    execute: str = Field(
        ...,
        alias="Execute",
        description="Custom JavaScript to run",
        min_length=1
        )


class ScreenShotAction(BaseModel):
    """Captures a screenshot during the execution of browser actions.

    Attributes:
        action (Literal["ScreenShot"]): The literal action identifier.
        full_screenshot (bool, optional): If True, captures the entire
            scrollable page.
        particular_screenshot (str, optional): CSS selector of a specific
            element to capture.
    """
    model_config = ConfigDict(
        populate_by_name=True
        )

    action: Literal["ScreenShot"] = Field(
        "ScreenShot",
        alias="Action"
        )
    full_screenshot: Optional[bool] = Field(
        None,
        alias="fullScreenShot",
        )
    particular_screenshot: Optional[str] = Field(
        None,
        alias="particularScreenShot",
        description="Selector of the element to take a screenshot of",
        min_length=1
        )

    @model_validator(mode="after")
    def validate_screenshot_logic(self) -> Self:
        """Ensures mutually exclusive screenshot targeting parameters are not
        combined.

        tip: Capturing Full Screenshot And Particular Screenshot
            A single screenshot action can either capture the entire scrollable
            page OR a specific DOM element, but not both simultaneously.
            To capture both, provide two separate `ScreenShotAction` objects in
            the `play_with_browser` list.

        Returns:
            The validated instance from which the method was called from

        Raises:
            ValueError: If both `full_screenshot` and `particular_screenshot`
                are active.
        """
        if self.full_screenshot and self.particular_screenshot:
            raise ValueError(
                "Cannot use 'full_screenshot' and 'particular_screenshot' "
                "simultaneously within a single ScreenShotAction."
            )
        return self


class WaitForRequestCompletionAction(BaseModel):
    """Pauses execution until network requests matching a specific pattern
    complete.

    Attributes:
        action (Literal["WaitForRequestCompletion"]): The literal action
            identifier.
        url_pattern (str): The regex or string pattern of the URL to wait for.
        timeout (int): Maximum time to wait in milliseconds before failing.
    """
    model_config = ConfigDict(
        populate_by_name=True
        )

    action: Literal["WaitForRequestCompletion"] = Field(
        "WaitForRequestCompletion",
        alias="Action"
        )

    url_pattern: str = Field(
        ...,
        alias="UrlPattern",
        description="Wait for requests matching this url pattern to complete",
        min_length=1
        )
    timeout: int = Field(
        ...,
        alias="Timeout",
        description="Number of miliseconds to wait",
        ge=0
    )

# -------------------------------------------------------------------
# Type Alias
# -------------------------------------------------------------------


BrowserAction = Annotated[
    Union[
        ClickAction,
        WaitAction,
        WaitSelectorAction,
        ScrollXAction,
        ScrollYAction,
        ScrollToAction,
        FillAction,
        ExecuteAction,
        ScreenShotAction,
        WaitForRequestCompletionAction
    ],
    Field(discriminator="action")
]
"""
Defines the valid types that can be passed to the
`play_with_browser` parameter in the `RequestParameters`
model
"""

RegionCodeType: TypeAlias = Literal[
    'europe',
    'asia'
    'africa'
    'oceania',
    'northamerica',
    'southamerica'
    ]
"""
Defines the valid strings that can be passed to the
`regional_geo_code` parameter in the `RequestParameters`
model
"""

WaitUntilType: TypeAlias = Literal[
    'domcontentloaded',
    'networkidle0',
    'networkidle2',
    'load'
    ]
"""
Defines the valid strings that can be passed to the
`wait_until` parameter in the `RequestParameters`
model
"""

DeviceType: TypeAlias = Literal[
    'desktop',
    'mobile',
    'tablet'
    ]
"""
Defines the valid strings that can be passed to the
`device` parameter in the `RequestParameters`
model
"""

OutputType: TypeAlias = Literal['raw', 'markdown']
"""
Defines the valid strings that can be passed to the
`output` parameter in the `RequestParameters`
model
"""

HttpMethod: TypeAlias = Literal[
    "GET",
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
    "HEAD",
    "OPTIONS"
    ]
"""
Defines the valid HTTP methods that can be passed to the
`method` parameter in the `PreparedScrapeDoRequest` model
"""

PayloadType: TypeAlias = Literal["json", "form", "raw"]
"""
Defines the valid types of payload that can be passed to the
`payload_type` parameter in the `PreparedScrapeDoRequest` model
"""

# -------------------------------------------------------------------
# Request Parameters Model
# -------------------------------------------------------------------


class RequestParameters(BaseModel):
    """The strict data contract for the request parameters accepted by
    Scrape.do's API.

    This model enforces all parameter dependencies, mutually exclusive rules,
    and geographical targeting constraints locally before a network request
    is generated.

    Attributes:
        url (HttpUrl): The absolute destination URL you wish to scrape.
        super (bool, optional): Activates Residential/Mobile IP proxies.
        render (bool, optional): Executes the request using a headless browser.
        device (DeviceType, optional): Specify the device type (desktop,
            mobile, tablet)
        session_id (int, optional): Use the same IP address continuously with
            a session
        geo_code (str, optional): ISO 3166-1 alpha-2 country code for IP
            targeting.
        regional_geo_code (RegionCodeType, optional): Targets a broader
            geographical region. Requires super=True.
        postal_code (str, optional): Targets a specific zip code. Requires
            super=True and a supported geo_code.
        wait_until (WaitUntilType, optional): Control when the browser
            considers the page loaded
        custom_wait (int, optional): Set the browser wait time on the target
            web page after content loaded
        wait_selector (str, optional): CSS selector to wait for in the target
            web page.
        width (int, optional): Custom viewport width.
        height (int, optional): Custom viewport height.
        return_json (bool, optional): Returns response body as base64-encoded
            JSON instead of raw HTML.
        block_resources (bool, optional): Block CSS, images, and fonts on your
            target web page
        screenshot (bool, optional): Captures the visible viewport.
        full_screenshot (bool, optional): Captures the entire scrollable page.
        particular_screenshot (str, optional): Captures a specific DOM element
            by selector.
        play_with_browser (List[BrowserAction], optional): A sequence of
            automated interactions to perform.
        show_frames (bool, optional): Returns all iframe content from the
            target webpage. Requires render=true and returnJSON=true
        show_websocket_requests (bool, optional): Captures WebSocket network
            traffic. Requires render=true and returnJSON=true.
        custom_headers (bool, optional): Replaces Scrape.do's default headers
            with your provided headers.
        extra_headers (bool, optional): Appends your provided headers to
            Scrape.do's default headers.
        forward_headers (bool, optional): Forwards all headers exactly as sent
            by your client.
        set_cookies (str, optional): Injects specific cookies into the request.
        disable_redirection (bool, optional): Prevents the proxy from
            following 3xx HTTP redirects.
        timeout (int, optional): Total API connection timeout in milliseconds.
        retry_timeout (int, optional): Internal proxy retry duration in
            milliseconds. Cannot be used with render=True.
        disable_retry (bool, optional): Fails immediately on target error
            without rotating IPs.
        output (OutputType, optional): Output format parser.
        transparent_response (bool, optional): Return pure response from
            target web page without Scrape.do processing
        pure_cookies (bool, optional): Returns the original Set-Cookie headers
            from the target website
    """
    model_config = ConfigDict(
        populate_by_name=True
        )

    # --- Required Parameters ---

    url: HttpUrl = Field(
        ...,
        alias="url"
        )

    # --- Core Routing Parameters ---

    super: Optional[bool] = Field(
        default=None,
        alias="super"
        )

    render: Optional[bool] = Field(
        None,
        alias="render"
        )

    device: Optional[DeviceType] = Field(
        None,
        alias="device"
        )

    session_id: Optional[int] = Field(
        None,
        alias="sessionId",
        ge=0,
        le=1000000
        )

    # --- Location Parameters ---

    geo_code: Optional[str] = Field(
        None,
        alias="geoCode",
        min_length=2,
        max_length=2
        )

    regional_geo_code: Optional[RegionCodeType] = Field(
        None,
        alias="regionalGeoCode"
        )

    postal_code: Optional[str] = Field(
        None,
        alias="postalcode"
    )

    # --- Browser Parameters ---

    wait_until: Optional[WaitUntilType] = Field(
        None,
        alias="waitUntil"
        )

    custom_wait: Optional[int] = Field(
        None,
        alias="customWait",
        ge=0,
        le=35000
        )

    wait_selector: Optional[str] = Field(
        None,
        alias="waitSelector"
        )

    width: Optional[int] = Field(
        None,
        alias="width"
        )

    height: Optional[int] = Field(
        None,
        alias="height"
        )

    return_json: Optional[bool] = Field(
        None,
        alias="returnJSON"
        )

    block_resources: Optional[bool] = Field(
        None,
        alias="blockResources"
        )

    screenshot: Optional[bool] = Field(
        None,
        alias="screenShot"
        )

    full_screenshot: Optional[bool] = Field(
        None,
        alias="fullScreenShot"
        )

    particular_screenshot: Optional[str] = Field(
        None,
        alias="particularScreenShot"
        )

    play_with_browser: Optional[List[BrowserAction]] = Field(
        None,
        alias="playWithBrowser"
        )

    # --- Browser Response Configuration Parameters ---

    show_frames: Optional[bool] = Field(
        None,
        alias="showFrames"
        )

    show_websocket_requests: Optional[bool] = Field(
        None,
        alias="showWebsocketRequests"
    )

    # --- Header + Cookie Control Parameters ---

    custom_headers: Optional[bool] = Field(
        None,
        alias="customHeaders"
        )

    extra_headers: Optional[bool] = Field(
        None,
        alias="extraHeaders"
        )

    forward_headers: Optional[bool] = Field(
        None,
        alias="forwardHeaders"
        )

    set_cookies: Optional[str] = Field(
        None,
        alias="setCookies"
        )

    # --- Network Parameters ---

    disable_redirection: Optional[bool] = Field(
        None,
        alias="disableRedirection"
        )

    timeout: Optional[int] = Field(
        None,
        alias="timeout",
        le=120000,
        ge=5000
        )

    retry_timeout: Optional[int] = Field(
        None,
        alias="retryTimeout",
        le=55000,
        ge=5000
        )

    disable_retry: Optional[bool] = Field(
        None,
        alias="disableRetry"
        )

    # --- General Response Configuration Parameters ---

    output: Optional[OutputType] = Field(
        None,
        alias="output"
        )

    transparent_response: Optional[bool] = Field(
        None,
        alias="transparentResponse"
        )

    pure_cookies: Optional[bool] = Field(
        None,
        alias="pureCookies"
        )

    @model_validator(mode="after")
    def validate_compatibility(self) -> Self:
        """Cross-validates parameter dependencies to prevent invalid API
        requests locally.

        info: Headless Browser Dependencies (`render=True`)
            - `wait_until`
            - `wait_selector`
            - `custom_wait`
            - `width`
            - `height`
            - `return_json`
            - `block_resources`
            - `screenshot`
            - `full_screenshot`
            - `particular_screenshot`
            - `play_with_browser`
            - `show_frames`
            - `show_websocket_requests`

        info: ReturnJSON Dependencies (`render=True` + `return_json=True`)
            - `screenshot`
            - `full_screenshot`
            - `particular_screenshot`
            - `show_frames`
            - `show_websocket_requests`

        info: Super Proxy Dependencies (`super=True`)
            - `regional_geo_code`

        info: Screenshot Parameters
             - Only one of the screenshot parameters can be set at a time.

             - In addition to `render=True` and `return_json=True`, all
                screenshot parameters require `blockResources` to be set to
                False.

        info: Header Parameters
            - Only one of the header parameters can be set at a time.

            - None of the header parameters can be set to True when using the
               `setCookies` parameter

        info: Mutually Exclusive Parameters
            - The `playWithBrowser` and `particular_screenshot` parameters
                cannot be used simultaneously

            - The `retryTimeout` and `render` parameters cannot be used
                simultaneously

            - The `regional_geo_code` and `geo_code` parameters cannot be used
                simultaneously

        Returns:
            The validated instance from which the method was called

        Raises:
            ValueError: If mutually exclusive parameters are combined or if
                dependent parameters are provided without their required
                prerequisites.
        """

        # --- Headless Browser Dependencies ---

        # Render Dependencies

        render_dependent_fields = {
            "wait_until": self.wait_until,
            "custom_wait": self.custom_wait,
            "wait_selector": self.wait_selector,
            "width": self.width,
            "height": self.height,
            "return_json": self.return_json,
            "block_resources": self.block_resources,
            "screenshot": self.screenshot,
            "full_screenshot": self.full_screenshot,
            "particular_screenshot": self.particular_screenshot,
            "play_with_browser": self.play_with_browser,
            "show_frames": self.show_frames,
            "show_websocket_requests": self.show_websocket_requests
            }

        used_render_fields = [
            field_name for field_name, value in render_dependent_fields.items()
            if value is not None
            ]

        if used_render_fields and not self.render:
            raise ValueError(
                f"The following parameters require 'render=true' to be set: "
                f"{', '.join(used_render_fields)}."
                )

        # ReturnJSON Additional Dependencies
        json_dependent_fields = {
            "screenshot": self.screenshot,
            "full_screenshot": self.full_screenshot,
            "particular_screenshot": self.particular_screenshot,
            "show_frames": self.show_frames,
            "show_websocket_requests": self.show_websocket_requests
        }

        used_json_fields = [
            field_name for field_name, value in json_dependent_fields.items()
            if value
            ]

        if used_json_fields and not self.return_json:
            raise ValueError((
                f"The following parameters require both 'render=true' AND"
                f" 'returnJSON=true' to be set: "
                f" {', '.join(used_json_fields)}."
                ))

        # Screenshot Additional Dependencies
        screenshot_fields = {
            "screenshot": self.screenshot,
            "full_screenshot": self.full_screenshot,
            "particular_screenshot": self.particular_screenshot
        }

        used_screenshot_fields = [
            field_name for field_name, value in screenshot_fields.items()
            if value
            ]

        if used_screenshot_fields and self.block_resources:
            raise ValueError((
                f"Screenshot parameters automatically operate with "
                f"'blockResources=false' to ensure contents are loaded "
                f"correctly. Screenshot Parameters used:"
                f" {', '.join(used_screenshot_fields)}"
                ))

        # --- Enforce Mutually Eclusive Parameters ---

        if self.render and self.retry_timeout is not None:
            raise ValueError(
                "The 'retry_timeout' parameter cannot be used concurrently"
                " with 'render=true'"
            )

        if len(used_screenshot_fields) > 1:
            raise ValueError(
                f"Only one screenshot parameter can be used at a time."
                f" Screenshot Parameters used:"
                f" {', '.join(used_screenshot_fields)}"
                )

        if (
            self.particular_screenshot is not None
            and self.play_with_browser is not None
        ):
            raise ValueError(
                "The 'particular_screenshot' parameter cannot be used"
                " concurrently with the 'playWithBrowser' parameter"
                )

        header_fields = {
            "custom_headers": self.custom_headers,
            "extra_headers": self.extra_headers,
            "forward_headers": self.forward_headers
        }

        used_header_fields = [
            field_name for field_name, value in header_fields.items()
            if value
            ]

        if len(used_header_fields) > 1:
            raise ValueError(
                f"Only one header parameter can be used at a time."
                f" Header Parameters used: {', '.join(used_header_fields)}"
                )

        if used_header_fields and self.set_cookies:
            raise ValueError(
                f"Header parameters cannot be used concurrently with"
                f" the set_cookies parameter. Header Parameters used:"
                f" {', '.join(used_header_fields)}"
                )

        if self.geo_code is not None and self.regional_geo_code is not None:
            raise ValueError(
                "'geoCode' and 'regionalGeoCode' parameters cannot be used"
                " simultaneously"
                )

        if not self.super and self.regional_geo_code is not None:
            raise ValueError(
                "'super=true' must be set to use the 'regionalGeoCode'"
                " parameter"
            )

        return self

    @field_validator("geo_code")
    @classmethod
    def validate_geo_code(
        cls: Type[Self],
        v: Optional[str],
        info: ValidationInfo
    ) -> Optional[str]:
        """Validates the country code against the allowed proxy pools.

        Args:
            cls (Type[RequestParameters]): The RequestParameters model class
            v (str, optional): The `geo_code` provided during initialization
            info (ValidationInfo): The data already validated for the model so
                far

        Returns:
            The validated `geo_code` parameter

        Raises:
            ValueError: If the country code is not supported by the selected
                proxy tier.
        """

        is_super = info.data.get("super", False)
        if v is not None:
            v = v.lower()
            if is_super:
                if v not in _SUPER_SUPPORTED_COUNTRIES:
                    raise ValueError(
                        f"'{v}' is not a supported country code"
                    )
            else:
                if v not in _DATACENTER_SUPPORTED_COUNTRIES:
                    if v in _SUPER_SUPPORTED_COUNTRIES:
                        raise ValueError(
                            f"'{v}' is not a supported country code when"
                            f" 'super=false'"
                            )
                    else:
                        raise ValueError(
                            f"'{v}' is not a supported country code"
                            )
            return v

        return v

    @field_validator("postal_code")
    @classmethod
    def validate_postal_code(
        cls: Type[Self],
        v: Optional[str],
        info: ValidationInfo
    ) -> Optional[str]:
        """Validates postal codes based on specific regional formats.

        Args:
            cls (Type[RequestParameters]): The RequestParameters model class
            v (str, optional): The `postal_code` provided during initialization
            info (ValidationInfo): The data already validated for the model so
                far

        Returns:
            The validated `postal_code` parameter

        Raises:
            ValueError: If dependencies are missing or the format does not
                match the regional regex.
        """
        if v is not None:
            v = v.strip()
            is_super = info.data.get("super", False)
            geo_code = info.data.get("geo_code")

            if not is_super or not geo_code:
                raise ValueError(
                    "The 'postalcode' parameter can only be used when both "
                    "'super=true' and a valid 'geoCode' are provided."
                    )

            if geo_code not in _ZIPCODE_FORMATS:
                raise ValueError(
                    f"Zip code targeting is not supported for country"
                    f" '{geo_code}'. "
                    f" Supported countries are:"
                    f" {', '.join(_ZIPCODE_FORMATS.keys())}."
                )

            regex = _ZIPCODE_FORMATS[geo_code]
            if not regex.match(v):
                raise ValueError(
                    f"Invalid zip code format for {geo_code}. "
                    f"Provided '{v}' does not match the required pattern."
                )

            return v
        return v

    def to_api_params(self) -> dict[str, Any]:
        """Serializes the model into a dictionary formatted for httpx
        query parameters.

        This method automatically drops unassigned fields, maps snake_case
        variables to their camelCase API equivalents, and stringifies nested
        JSON objects as required by Scrape.do.

        Returns:
            A sanitized dictionary ready to be passed to httpx.
        """

        params = self.model_dump(
            by_alias=True,
            exclude_none=True,
            mode="json"
            )

        if "playWithBrowser" in params:
            params["playWithBrowser"] = json.dumps(params["playWithBrowser"])

        for key, value in params.items():
            if isinstance(value, bool):
                params[key] = "true" if value else "false"

        return params


# -------------------------------------------------------------------
# PreparedScrapeDoRequest Model
# -------------------------------------------------------------------


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
        headers (Dict[str, str], optional): Custom HTTP headers to forward
        body (Union[Dict[str, Any], str, bytes], optional): Payload to send to
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
              true and `method=HEAD`

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

        if self.api_params.render and self.method == "HEAD":
            raise ValueError((
                "Combining method='HEAD' with 'render=True' is an "
                "architectural anti-pattern. A HEAD request returns no body, "
                "causing the headless browser to idle with an empty DOM until "
                "it times out. This wastes API credits and compute resources."
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

    def to_httpx_kwargs(self) -> Dict[str, Any]:
        """Packages the validated object into a dictionary ready for httpx
        unpacking.

        Returns:
            Keyword arguments strictly formatted for `httpx.request()`.
        """

        kwargs: Dict[str, Any] = {
            "method": self.method,
            "url": "https://api.scrape.do/",
            "params": self.api_params.to_api_params()
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
