"""Public API for the data models and Scrape.do API contracts

Aggregates domain models into a unified namespace to expose all necessary type
hints, browser actions, and configuration contracts required to interact with
the API.
"""

from __future__ import annotations

from .browser_actions import (
    ClickAction,
    WaitAction,
    WaitSelectorAction,
    ScrollXAction,
    ScrollYAction,
    ScrollToAction,
    FillAction,
    ExecuteAction,
    ScreenShotAction,
    WaitForRequestCompletionAction,
    BrowserAction
    )
from .enums import (
    RegionCodeType,
    WaitUntilType,
    DeviceType,
    OutputType,
    HttpMethod,
    PayloadType
    )
from .request import (
    PreparedScrapeDoRequest
)
from .parameters import (
    RequestParameters,
    RequestParametersDict
)
from .response import (
    ScrapeDoNetworkRequest,
    ScrapeDoWebSocketFrame,
    ScrapeDoWebSocketEvent,
    ScrapeDoWebsocketRequest,
    ScrapeDoActionResult,
    ScrapeDoScreenshot,
    ScrapeDoFrame,
    ScrapeDoResponse
    )


__all__ = [
    "ClickAction",
    "WaitAction",
    "WaitSelectorAction",
    "ScrollXAction",
    "ScrollYAction",
    "ScrollToAction",
    "FillAction",
    "ExecuteAction",
    "ScreenShotAction",
    "WaitForRequestCompletionAction",
    "BrowserAction",
    "RegionCodeType",
    "WaitUntilType",
    "DeviceType",
    "OutputType",
    "HttpMethod",
    "PayloadType",
    "RequestParametersDict",
    "RequestParameters",
    "PreparedScrapeDoRequest",
    "ScrapeDoNetworkRequest",
    "ScrapeDoWebSocketFrame",
    "ScrapeDoWebSocketEvent",
    "ScrapeDoWebsocketRequest",
    "ScrapeDoActionResult",
    "ScrapeDoScreenshot",
    "ScrapeDoFrame",
    "ScrapeDoResponse"
    ]
