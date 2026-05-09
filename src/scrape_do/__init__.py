"""scrape-do-python — A Python SDK for the Scrape.do web-scraping proxy API.

The synchronous client (`ScrapeDoClient`) is the current public surface.
Async and proxy-mode clients, the Async-API queue, and domain plugins
are on the roadmap — see ROADMAP.md.

Common imports:
    >>> from scrape_do import ScrapeDoClient, RequestParameters, ScrapeDoResponse
    >>> from scrape_do import ScrapeDoError, RotatedSessionError

Full API reference: https://svdc1.github.io/scrape-do-python
"""

from scrape_do.client import (
    ScrapeDoClient,
    SyncClientEventHooks,
    SyncSessionValidator,
)
from scrape_do.exceptions import (
    APIConnectionError,
    AuthenticationError,
    AuthenticationThrottleError,
    BadRequestError,
    RateLimitError,
    RotatedSessionError,
    ScrapeDoError,
    ServerError,
    TargetError,
)
from scrape_do.models import (
    RequestParameters,
    ScrapeDoResponse,
)

__all__ = [
    "APIConnectionError",
    "AuthenticationError",
    "AuthenticationThrottleError",
    "BadRequestError",
    "RateLimitError",
    "RequestParameters",
    "RotatedSessionError",
    "ScrapeDoClient",
    "ScrapeDoError",
    "ScrapeDoResponse",
    "ServerError",
    "SyncClientEventHooks",
    "SyncSessionValidator",
    "TargetError",
]
