"""
Shared fixtures for the SDK's test suite
"""

import pytest
import httpx
from scrape_do.models import RequestParameters, PreparedScrapeDoRequest
from unittest.mock import MagicMock
from scrape_do.client import ScrapeDoClient


@pytest.fixture
def example_url() -> str:
    """
    Provides a valid fake url to be used for model testing

    Returns:
        A valid fake url
    """
    return "https://example.com/"


@pytest.fixture
def mock_json_payload() -> dict:
    """
    Provides a fake JSON dictionary including all keys that can be present
    in the JSON returned by Scrape.do when `returnJSON=true`.

    Returns:
        The fake JSON dictionary
    """
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


@pytest.fixture
def mock_headers() -> httpx.Headers:
    """
    Provides a fake httpx.Headers object including all headers returned by
    Scrape.do.

    Returns:
        The fake httpx.Headers object
    """
    headers = {
        "server": "cloudflare",
        "x-frame-options": "DENY",
        "transfer-encoding": "chunked",
        "scrape.do-auth": "0",
        "scrape.do-cookies": "cookie1=value1;cookie2=value2",
        "scrape.do-initial-status-code": "200",
        "scrape.do-rate": "0:0",
        "scrape.do-remaining-credits": "300000",
        "scrape.do-request-cost": "25",
        "scrape.do-request-id": "123e4567-e89b-12d3-a456-426614174000",
        "scrape.do-resolved-url": "https://example.com/final",
        "scrape.do-rid": "node-123",
        "scrape.do-target-url": "https://example.com"
    }

    return httpx.Headers(headers)


@pytest.fixture
def make_request():
    """
    Factory to generate valid PreparedScrapeDoRequest objects.
    """
    def _make(
        url="https://example.com",
        method="GET",
        **kwargs
    ):
        params = RequestParameters(url=url, **kwargs)
        return PreparedScrapeDoRequest(api_params=params, method=method)
    return _make


@pytest.fixture
def make_response():
    """
    Factory to generate strictly controlled httpx.Response mocks.
    """
    def _make(
        status_code: int,
        json_data: dict = None,
        text: str = None,
        proxy_status_header: str = None
    ):
        headers = {}
        if proxy_status_header is not None:
            headers["scrape.do-initial-status-code"] = str(proxy_status_header)

        if json_data is not None:
            return httpx.Response(status_code, headers=headers, json=json_data)
        return httpx.Response(status_code, headers=headers, text=text or "")
    return _make


@pytest.fixture
def mock_sync_client():
    """
    Yields a cleanly initialized ScrapeDoClient for testing.
    """
    with ScrapeDoClient(api_token='dummy_token') as client:
        yield client


@pytest.fixture
def mock_env_vars(monkeypatch: pytest.MonkeyPatch):
    """Clears the SCRAPE_DO_API_KEY from the environment for a test function

    Guarantees that tests do not accidentally inherit a real
    developer token from the local machine's environment variables
    """
    monkeypatch.delenv("SCRAPE_DO_API_KEY", raising=False)


@pytest.fixture
def mock_sleep(mocker) -> MagicMock:
    """
     Mocks `time.sleep` across an entire test function.
    """
    return mocker.patch("time.sleep", return_value=None)
