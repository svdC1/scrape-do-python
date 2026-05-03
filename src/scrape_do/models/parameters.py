"""Core validation engine and configuration contracts.

Validates request data before the network layer to ensure that invalid
configurations are caught locally without wasting network requests by using
Pydantic V2 models to enforce Scrape.do's parameter dependencies and
interactions
"""

from __future__ import annotations
import json
import urllib.parse
from typing import (
    Optional,
    List,
    Self,
    Type,
    Any,
    Dict,
    TypedDict
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
from .browser_actions import BrowserAction
from .enums import (
    OutputType,
    DeviceType,
    WaitUntilType,
    RegionCodeType
    )
from ..constants import (
    _SUPER_SUPPORTED_COUNTRIES,
    _DATACENTER_SUPPORTED_COUNTRIES,
    _ZIPCODE_FORMATS
    )


# ----------------------------------
# RequestParameters Kwargs TypedDict
# ----------------------------------

class RequestParametersDict(TypedDict, total=False):
    """
    Provides strict IDE autocomplete and static type checking for `**kwargs`
    dictionaries meant for the
    [RequestParameters][scrape_do.models.RequestParameters] model.
    """
    super: Optional[bool]
    """
    Activates Residential/Mobile IP proxies.
    """
    render: Optional[bool]
    """
    Executes the request using a headless browser.
    """
    device: Optional[DeviceType]
    """
    Specify the device type (desktop, mobile, tablet)
    """
    session_id: Optional[int]
    """
    Use the same IP address continuously with a session
    """
    geo_code: Optional[str]
    """
    ISO 3166-1 alpha-2 country code for IP targeting.
    """
    regional_geo_code: Optional[RegionCodeType]
    """
    Targets a broader geographical region. Requires super=True.
    """
    postal_code: Optional[str]
    """
    Targets a specific zip code. Requires super=True and a supported geo_code.
    """
    wait_until: Optional[WaitUntilType]
    """
    Control when the browser considers the page loaded
    """
    custom_wait: Optional[int]
    """
    Set the browser wait time on the target web page after content loaded
    """
    wait_selector: Optional[str]
    """
    CSS selector to wait for in the target web page.
    """
    width: Optional[int]
    """
    Custom viewport width.
    """
    height: Optional[int]
    """
    Custom viewport height.
    """
    return_json: Optional[bool]
    """
    Returns response body as base64-encoded JSON instead of raw HTML.
    """
    block_resources: Optional[bool]
    """
    Block CSS, images, and fonts on your target web page
    """
    screenshot: Optional[bool]
    """
    Captures the visible viewport.
    """
    full_screenshot: Optional[bool]
    """
    Captures the entire scrollable page.
    """
    particular_screenshot: Optional[str]
    """
    Captures a specific DOM element by selector.
    """
    play_with_browser: Optional[List[BrowserAction]]
    """
    A sequence of automated interactions to perform.
    """
    show_frames: Optional[bool]
    """
    Returns all iframe content from the target webpage. Requires render=true
    and returnJSON=true
    """
    show_websocket_requests: Optional[bool]
    """
    Captures WebSocket network traffic. Requires render=true and
    returnJSON=true.
    """
    custom_headers: Optional[bool]
    """
    Replaces Scrape.do's default headers with your provided headers.
    """
    extra_headers: Optional[bool]
    """
    Appends your provided headers to Scrape.do's default headers.
    """
    forward_headers: Optional[bool]
    """
    Forwards all headers exactly as sent by your client.
    """
    set_cookies: Optional[str]
    """
    Injects specific cookies into the request.
    """
    disable_redirection: Optional[bool]
    """
    Prevents the proxy from following 3xx HTTP redirects.
    """
    timeout: Optional[int]
    """
    Total API connection timeout in milliseconds.
    """
    retry_timeout: Optional[int]
    """
    Internal proxy retry duration in milliseconds. Cannot be used with
    render=True.
    """
    disable_retry: Optional[bool]
    """
    Fails immediately on target error without rotating IPs.
    """
    output: Optional[OutputType]
    """
    Output format parser.
    """
    transparent_response: Optional[bool]
    """
    Return pure response from target web page without Scrape.do processing
    """
    pure_cookies: Optional[bool]
    """
    Returns the original Set-Cookie headers from the target website
    """


# --------------------
# Request Parameters
# --------------------

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
        max_length=2,
        validate_default=True
        )

    regional_geo_code: Optional[RegionCodeType] = Field(
        None,
        alias="regionalGeoCode"
        )

    postal_code: Optional[str] = Field(
        None,
        alias="postalcode",
        validate_default=True
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
    def from_url(cls: type[Self], api_url: str) -> RequestParameters:
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
