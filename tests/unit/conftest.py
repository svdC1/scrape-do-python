"""
Fixtures for the unit tests.

Organization:
1. Static helpers (URLs, payloads, headers).
2. Factory fixtures (`make_response`, `make_scrape_do_response`).
3. Autouse environment guard (clears `SCRAPE_DO_API_KEY`).
4. Time-mock fixtures (`mock_sleep`, `mock_async_sleep`).
5. Sync client fixtures.
6. Async client fixtures.
"""

import pytest
import pytest_asyncio
import httpx
from typing import Any, Dict, Iterable, Optional
from unittest.mock import MagicMock
from scrape_do.client import ScrapeDoClient
from scrape_do.async_client import AsyncScrapeDoClient
from scrape_do.proxy_client import ScrapeDoProxyClient
from scrape_do.async_proxy_client import AsyncScrapeDoProxyClient
from scrape_do.models import (
    PreparedScrapeDoRequest,
    RequestParameters,
    ScrapeDoResponse,
    )


# ---------------------------------------------------------------------------
# Static helpers
# ---------------------------------------------------------------------------

@pytest.fixture
def example_url() -> str:
    """Provides a valid fake url to be used for model testing."""
    return "https://example.com/"


@pytest.fixture
def mock_json_payload() -> dict:
    """Fake JSON dictionary including every key Scrape.do can return
    when `returnJSON=true`."""
    return {
        "statusCode": 200,
        "content": "<html>Target Data</html>",
        "networkRequests": [{
            "url": "https://example.com/api",
            "method": "POST",
            "status": 204,
            "request_headers": {},
            "request_body": "{\"req\": \"data\"}",
            "response_body": "",
            "response_headers": {}
        }],
        "websocketRequests": [{
            "type": "received",
            "event": {
                "requestId": "586051.322",
                "timestamp": 21815567.089025,
                "response": {
                    "opcode": 1,
                    "mask": False,
                    "payloadData": "{\"live_price\": 65000.00}"
                }
            }
        }],
        "actionResults": [
            {
                "action": "Click",
                "index": 0,
                "success": False,
                "error": "Element not found",
                "response": None
            },
            {
                "action": "Wait",
                "index": 1,
                "success": True
            }
        ],
        "screenShots": [{
            "type": "FullScreenShot",
            "image": "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HA",
            "error": None
        }],
        "frames": [{
            "url": "https://example.com/iframe",
            "content": "<html>Iframe Content</html>"
        }]
    }


# Full set of Scrape.do telemetry headers that the SDK extracts from
# real responses. Tests can use the dict directly, or build a subset
# via `telemetry_headers_subset`.
_FULL_SCRAPE_DO_TELEMETRY_HEADERS: Dict[str, str] = {
    "scrape.do-auth": "0",
    "scrape.do-cookies": "cookie1=value1; cookie2=value2",
    "scrape.do-initial-status-code": "200",
    "scrape.do-rate": "0:0",
    "scrape.do-remaining-credits": "300000",
    "scrape.do-request-cost": "25",
    "scrape.do-request-id": "123e4567-e89b-12d3-a456-426614174000",
    "scrape.do-resolved-url": "https://example.com/final",
    "scrape.do-rid": "node-123",
    "scrape.do-target-url": "https://example.com",
    }

# Common target-side response headers paired with the telemetry above.
_DEFAULT_TARGET_HEADERS: Dict[str, str] = {
    "server": "cloudflare",
    "x-frame-options": "DENY",
    "transfer-encoding": "chunked",
    }


@pytest.fixture
def full_scrape_do_telemetry_headers() -> httpx.Headers:
    """Every Scrape.do telemetry header the SDK extracts, paired with
    common target-side headers. Suitable as the default response
    header shape in tests."""
    return httpx.Headers({
        **_DEFAULT_TARGET_HEADERS,
        **_FULL_SCRAPE_DO_TELEMETRY_HEADERS,
        })


@pytest.fixture
def telemetry_headers_subset():
    """Factory that returns a subset of the canonical Scrape.do
    telemetry headers.

    Args:
        keys: Iterable of header names (without the `scrape.do-`
            prefix - the factory adds it). Pass keys like
            `("request-id", "rid")` to get just those two telemetry
            headers in the returned dict.
    """
    def _build(keys: Iterable[str]) -> Dict[str, str]:
        prefixed = {f"scrape.do-{k}" for k in keys}
        return {
            name: value
            for name, value in _FULL_SCRAPE_DO_TELEMETRY_HEADERS.items()
            if name in prefixed
            }
    return _build


# ---------------------------------------------------------------------------
# Factory fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def make_response():
    """Factory for strictly controlled `httpx.Response` mocks.

    Args:
        status_code (int): HTTP status code.
        json_data (Optional[dict]): Body content as a JSON-serializable
            dict. Mutually exclusive with `text`.
        text (Optional[str]): Body content as a string. Used when
            `json_data` is None.
        scrape_do_headers (Optional[Dict[str, str]]): Scrape.do
            telemetry headers (e.g. `{"scrape.do-request-id": "..."}`).
        target_headers (Optional[Dict[str, str]]): Target-side response
            headers (e.g. `{"content-type": "image/png"}`).
        proxy_status_header (Optional[str]): Shortcut for setting
            `scrape.do-initial-status-code`. Kept for back-compat with
            existing tests; new tests should use `scrape_do_headers`
            directly.
    """
    def _make(
        status_code: int,
        json_data: Optional[dict] = None,
        text: Optional[str] = None,
        scrape_do_headers: Optional[Dict[str, str]] = None,
        target_headers: Optional[Dict[str, str]] = None,
        proxy_status_header: Optional[str] = None,
    ) -> httpx.Response:
        headers: Dict[str, str] = {}
        if target_headers:
            headers.update(target_headers)
        if scrape_do_headers:
            headers.update(scrape_do_headers)
        if proxy_status_header is not None:
            headers["scrape.do-initial-status-code"] = str(
                proxy_status_header
                )

        if json_data is not None:
            return httpx.Response(
                status_code, headers=headers, json=json_data
                )
        return httpx.Response(
            status_code, headers=headers, text=text or ""
            )
    return _make


@pytest.fixture
def make_scrape_do_response(make_response, example_url):
    """Factory that produces a ready-to-assert `ScrapeDoResponse`
    wrapping a `PreparedScrapeDoRequest` + `httpx.Response`.

    Args:
        status_code (int): HTTP status code for the underlying httpx
            response.
        request_kwargs (Optional[Dict[str, Any]]): Kwargs forwarded
            to `RequestParameters(...)` for the wrapped request.
            Defaults to `{"url": example_url}`.
        **response_kwargs: Forwarded to `make_response`. Use
            `json_data`, `text`, `scrape_do_headers`, `target_headers`,
            or `proxy_status_header` to shape the body / headers.
    """
    def _build(
        status_code: int,
        request_kwargs: Optional[Dict[str, Any]] = None,
        **response_kwargs: Any,
    ) -> ScrapeDoResponse:
        params = RequestParameters(
            **{"url": example_url, **(request_kwargs or {})}
            )
        request = PreparedScrapeDoRequest(api_params=params, method="GET")
        response = make_response(status_code, **response_kwargs)
        return ScrapeDoResponse(request, response)
    return _build


# ---------------------------------------------------------------------------
# Autouse environment guard
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clear_api_token_env(monkeypatch: pytest.MonkeyPatch):
    """Autouse: clears `SCRAPE_DO_API_KEY` from the environment at the
    start of every unit test so the suite never accidentally picks up
    a real developer token. Tests that need a value set explicitly use
    `monkeypatch.setenv(...)` - that override survives this clear
    since both fixtures share the same `monkeypatch` instance."""
    monkeypatch.delenv("SCRAPE_DO_API_KEY", raising=False)


# ---------------------------------------------------------------------------
# Time-mock fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_sleep(mocker) -> MagicMock:
    """Mocks `time.sleep` across an entire test function so the sync
    retry loop doesn't introduce real delay."""
    return mocker.patch("time.sleep", return_value=None)


@pytest.fixture
def mock_async_sleep(mocker) -> MagicMock:
    """Mocks `asyncio.sleep` across an entire test function so the
    async retry loop doesn't introduce real delay.

    Note: patching `scrape_do.async_client.asyncio.sleep` reaches
    `asyncio.sleep` globally because `scrape_do.async_client.asyncio`
    is the same module object as `asyncio` everywhere else. The
    `scrape_do.async_proxy_client` module's `asyncio.sleep` calls are
    therefore also intercepted by this fixture.
    """
    return mocker.patch(
        "scrape_do.async_client.asyncio.sleep",
        new_callable=mocker.AsyncMock,
        return_value=None,
        )


# ---------------------------------------------------------------------------
# Sync client fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_sync_client():
    """Yields a cleanly initialized `ScrapeDoClient` for testing.

    No `verify` override needed - API-mode tests run through respx so
    no TLS chain is established.
    """
    with ScrapeDoClient(api_token='dummy_token') as client:
        yield client


@pytest.fixture
def mock_sync_proxy_client():
    """Yields a cleanly initialized `ScrapeDoProxyClient` for testing.

    `verify=False` disables TLS verification so respx-mocked transports
    don't need to surface Scrape.do's CA chain.
    """
    with ScrapeDoProxyClient(
        api_token='dummy_token',
        verify=False,
    ) as client:
        yield client


# ---------------------------------------------------------------------------
# Async client fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def mock_async_client():
    """Yields a cleanly initialized `AsyncScrapeDoClient` for async
    testing."""
    async with AsyncScrapeDoClient(api_token='dummy_token') as client:
        yield client


@pytest_asyncio.fixture
async def mock_async_proxy_client():
    """Yields a cleanly initialized `AsyncScrapeDoProxyClient` for
    async testing."""
    async with AsyncScrapeDoProxyClient(
        api_token='dummy_token',
        verify=False,
    ) as client:
        yield client
