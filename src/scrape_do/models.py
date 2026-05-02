"""Data models and API contracts

This module utilizes Pydantic V2 to enforce Scrape.do's complex routing rules,
parameter dependencies, and geographical targeting constraints locally,
ensuring that invalid configurations are caught before a network request is
generated.
"""

from __future__ import annotations
import json
import warnings
import httpx
import re
import base64
from pathlib import Path
import os
import urllib.parse
from functools import cached_property
from typing import (
    Annotated,
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
from pydantic import (
    BaseModel,
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

from scrape_do.exceptions import (
    AuthenticationError,
    BadRequestError,
    AuthenticationThrottleError,
    APIResponseError,
    RateLimitError,
    ServerError,
    TargetError
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
        timeout (Optional[int]): Maximum time to wait in milliseconds.
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
        full_screenshot (Optional[bool]): If True, captures the entire
            scrollable page.
        particular_screenshot (Optional[str]): CSS selector of a specific
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
        super (Optional[bool]): Activates Residential/Mobile IP proxies.
        render (Optional[bool]): Executes the request using a headless browser.
        device (Optional[DeviceType]): Specify the device type (desktop,
            mobile, tablet)
        session_id (Optional[int]): Use the same IP address continuously with
            a session
        geo_code (Optional[str]): ISO 3166-1 alpha-2 country code for IP
            targeting.
        regional_geo_code (Optional[RegionCodeType]): Targets a broader
            geographical region. Requires super=True.
        postal_code (Optional[str]): Targets a specific zip code. Requires
            super=True and a supported geo_code.
        wait_until (Optional[WaitUntilType]): Control when the browser
            considers the page loaded
        custom_wait (Optional[int]): Set the browser wait time on the target
            web page after content loaded
        wait_selector (Optional[str]): CSS selector to wait for in the target
            web page.
        width (Optional[int]): Custom viewport width.
        height (Optional[int]): Custom viewport height.
        return_json (Optional[bool]): Returns response body as base64-encoded
            JSON instead of raw HTML.
        block_resources (Optional[bool]): Block CSS, images, and fonts on your
            target web page
        screenshot (Optional[bool]): Captures the visible viewport.
        full_screenshot (Optional[bool]): Captures the entire scrollable page.
        particular_screenshot (Optional[str]): Captures a specific DOM element
            by selector.
        play_with_browser (Optional[List[BrowserAction]]): A sequence of
            automated interactions to perform.
        show_frames (Optional[bool]): Returns all iframe content from the
            target webpage. Requires render=true and returnJSON=true
        show_websocket_requests (Optional[bool]): Captures WebSocket network
            traffic. Requires render=true and returnJSON=true.
        custom_headers (Optional[bool]): Replaces Scrape.do's default headers
            with your provided headers.
        extra_headers (Optional[bool]): Appends your provided headers to
            Scrape.do's default headers.
        forward_headers (Optional[bool]): Forwards all headers exactly as sent
            by your client.
        set_cookies (Optional[str]): Injects specific cookies into the request.
        disable_redirection (Optional[bool]): Prevents the proxy from
            following 3xx HTTP redirects.
        timeout (Optional[int]): Total API connection timeout in milliseconds.
        retry_timeout (Optional[int]): Internal proxy retry duration in
            milliseconds. Cannot be used with render=True.
        disable_retry (Optional[bool]): Fails immediately on target error
            without rotating IPs.
        output (Optional[OutputType]): Output format parser.
        transparent_response (Optional[bool]): Return pure response from
            target web page without Scrape.do processing
        pure_cookies (Optional[bool]): Returns the original Set-Cookie headers
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
            v (Optional[str]): The `geo_code` provided during initialization
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
            v (Optional[str]): The `postal_code` provided during initialization
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

    def to_api_params(self) -> Dict[str, Any]:
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

        for key, value in params.items():

            # Serialize playWithBrowserActions
            if key == "playWithBrowser" and self.play_with_browser:
                actions = []
                for action in self.play_with_browser:
                    a_dict = action.model_dump(
                        by_alias=True,
                        exclude_none=True,
                        mode="json"
                        )

                    # Scrape.do's backend expects string booleans
                    for k, v in a_dict.items():
                        if isinstance(v, bool):
                            a_dict[k] = "true" if v else "false"

                    actions.append(a_dict)

                params[key] = json.dumps(actions)

            if isinstance(value, bool):
                params[key] = "true" if value else "false"

        return params

    @classmethod
    def from_url(cls, api_url: str) -> RequestParameters:
        """Instantiates a `RequestParameters` instance by parsing a raw
        Scrape.do API URL string.

        tip: Accepted URLs
            This method accepts both raw and encoded URLs by using
            the `urllib.parse.parse_qs` and `urllib.parse.unquote_plus`
            functions to normalize encoded URLs.

        warning: Browser Actions (`playWithBrowser`)
            When providing a URL containing the `playWithBrowser` parameter,
            make sure to use the `json.dumps` function to stringify the list
            of dictionaries containing the entries. Both the raw and ecoded
            URLs can be passed to this method afterwards.

        warning: API Token
            This method ignores the `&token=` parameter containing the
            Scrape.do API key, since its insertion is meant to be handled by
            the `ScrapeDoClient` using either an initialization parameter, or
            the `SCRAPE_DO_API_KEY` environment variable.

        Args:
            api_url (str): The full Scrape.do endpoint
                (`https://api.scrape.do/?url=...&render=true...`)

        Raises:
            ValueError: If the value found in the `&playWithBrowser=` parameter
                is not a parsable JSON string.

        Returns:
            The `RequestParameters` instance mapping the URL parameters
                (`&render=true&...`) to validated attributes
        """

        parsed = urllib.parse.urlparse(api_url)
        query_params = urllib.parse.parse_qs(parsed.query)
        # Type parsed params as Dict[str, Any] and let Pydantic raise a
        # ValidationError if it can't coerce a specific value
        flat_params: Dict[str, Any] = {
            k: v[0] for k, v in query_params.items()
            }

        # Reconstruct the nested JSON actions if they exist
        if "playWithBrowser" in flat_params:
            try:
                # Manually convert '+' to ' ' specifically for this JSON string
                decoded = urllib.parse.unquote_plus(
                    flat_params["playWithBrowser"]
                    )

                flat_params["playWithBrowser"] = json.loads(decoded)

            except json.JSONDecodeError as e:
                raise ValueError(
                    f"Failed to decode `playWithBrowser` parameter from URL | "
                    f"Parameter Value : {flat_params['playWithBrowser']}"
                    ) from e

        # Strip Token
        flat_params.pop("token", None)

        return cls(**flat_params)


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


# -------------------------------------------------------------------
# Response Models
# -------------------------------------------------------------------

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
                prevent abuse.
            RateLimitError: If you exceed your account's concurrent request
                limit (HTTP 429).
            ServerError: If the Scrape.do gateway experiences an issue
                (HTTP 500+).
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
            elif raw_status >= 500:
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
