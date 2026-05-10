"""scrape-do-python — A Python SDK for the Scrape.do web-scraping proxy API.

The synchronous client (`ScrapeDoClient`) is the current public surface.
Async and proxy-mode clients, the Async-API queue, and domain plugins
are on the roadmap — see ROADMAP.md.

Full API reference: https://svdc1.github.io/scrape-do-python

Example:
    ```
    from scrape_do import (
        ScrapeDoClient,
        RequestParameters,
        ScrapeDoResponse
        )

    # API Token pulled from `SCRAPE_DO_API_KEY` env variable

    with ScrapeDoClient() as client:
        resp = client.get(
            "https://httpbin.co/anything",
            render=True,
            return_json=True,
            screenshot=True,
            block_resources=False
            )

        resp.raise_for_status()

        print(resp.remaining_credits)
        # 300000.0
        resp.screenshots[0].to_file("screenshot.png")
    ```
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
