"""Pydantic models for headless browser automation.

Defines the strongly-typed contracts for the `playWithBrowser`
feature of the Scrape.do API. It provides models for every supported
browser interaction, enabling users to chain automation workflows with
full type safety and IDE support.
"""

from __future__ import annotations
from typing import (
    Literal,
    Optional,
    Self,
    TypeAlias,
    Annotated,
    Union
    )
from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator
    )


# ---------------------
# Browser Action Models
# ---------------------

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

# -------------------------
# Browser Action Type Alias
# -------------------------


BrowserAction: TypeAlias = Annotated[
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
