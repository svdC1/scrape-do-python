"""
Live render-envelope integration tests.

Each test exercises ONE render artifact field on `ScrapeDoResponse`
with the minimum setup needed to populate it. The unit suite covers
the parsing logic against synthetic payloads; this file confirms the
live Scrape.do envelope shape matches what the pydantic models accept.

Render tests are credit-expensive on Scrape.do, so they're grouped
here for easy `--ignore=tests/integration/test_render.py` on
incremental runs.

Coverage by client variant:

- Sync API mode (`ScrapeDoClient`) - one test per artifact
  (frames, screenshots, action_results, network_requests,
  websocket_requests).
- Async API mode (`AsyncScrapeDoClient`) - one composite test that
  hits every artifact in a single render, confirming the async
  parsing code path produces the same shape.
- Sync + async proxy mode - one composite test each, mirroring async
  API mode. Proxy Mode emits a `UserWarning` when `render=True` is
  used (Scrape.do recommends against it for users running their own
  browser automation) - we suppress that specific warning per test
  since we're intentionally exercising the rendered envelope path
  through proxy clients.
"""

import os
import pytest
from scrape_do.client import ScrapeDoClient
from scrape_do.async_client import AsyncScrapeDoClient
from scrape_do.proxy_client import ScrapeDoProxyClient
from scrape_do.async_proxy_client import AsyncScrapeDoProxyClient
from scrape_do.models import (
    ExecuteAction,
    WaitAction,
    WaitForRequestCompletionAction,
    ScreenShotAction,
    )

HTTPBIN_BASE = os.getenv("HTTPBIN_BASE", "https://httpbin.co")


# ---------------------------------------------------------------------------
# Sync API mode - one test per artifact
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestLiveRenderEnvelopeSync:
    """One test per render artifact field. Each uses the minimum setup
    needed to populate the field under test."""

    def test_frames_populates(
        self,
        default_sync_client: ScrapeDoClient,
        response_trace,
    ):
        """`show_frames=True` populates `frames` with the root frame
        even on pages without iframes. Exercises `ScrapeDoFrame`
        construction against a live Scrape.do envelope."""
        response = default_sync_client.get(
            f"{HTTPBIN_BASE}/anything",
            render=True,
            super=True,
            return_json=True,
            show_frames=True,
            disable_retry=True,
            )
        response_trace(response)

        assert response.is_proxy_error is False
        assert response.target_status_code == 200
        assert response.frames is not None
        assert len(response.frames) >= 1
        root_frame = response.frames[0]
        assert root_frame.url is not None
        assert root_frame.content is not None

    def test_screenshots_populates(
        self,
        default_sync_client: ScrapeDoClient,
        response_trace,
    ):
        """`ScreenShotAction(full_screenshot=True)` populates
        `screenshots` with a non-empty base64 PNG."""
        response = default_sync_client.get(
            f"{HTTPBIN_BASE}/anything",
            render=True,
            super=True,
            return_json=True,
            play_with_browser=[
                ScreenShotAction(full_screenshot=True),
                ],
            disable_retry=True,
            )
        response_trace(response)

        assert response.is_proxy_error is False
        assert response.target_status_code == 200
        assert response.screenshots is not None
        assert len(response.screenshots) >= 1
        shot = response.screenshots[0]
        assert shot.b64_image is not None
        assert len(shot.b64_image) > 0
        assert shot.screenshot_type == "FullScreenShot"

    def test_action_results_populates(
        self,
        default_sync_client: ScrapeDoClient,
        response_trace,
    ):
        """Non-screenshot browser actions populate `action_results`.
        `ScreenShotAction` results go to `screenshots` instead, so a
        test focused on `action_results` uses a simple `WaitAction`."""
        response = default_sync_client.get(
            f"{HTTPBIN_BASE}/anything",
            render=True,
            super=True,
            return_json=True,
            play_with_browser=[WaitAction(timeout=200)],
            disable_retry=True,
            )
        response_trace(response)

        assert response.is_proxy_error is False
        assert response.target_status_code == 200
        assert response.action_results is not None
        assert len(response.action_results) == 1
        result = response.action_results[0]
        assert result.action == "Wait"
        assert result.success is True
        assert result.index == 0

    def test_network_requests_populates(
        self,
        default_sync_client: ScrapeDoClient,
        response_trace,
    ):
        """An `ExecuteAction` issuing a `fetch()` followed by a
        `WaitForRequestCompletionAction` ensures the browser's
        network instrumentation captures at least one in-flight
        request before the render completes. httpbin.co/anything
        on its own doesn't trigger subresource fetches, so we have
        to force one."""
        fetch_target = f"{HTTPBIN_BASE}/uuid"
        response = default_sync_client.get(
            f"{HTTPBIN_BASE}/anything",
            render=True,
            super=True,
            return_json=True,
            play_with_browser=[
                ExecuteAction(execute=f"fetch('{fetch_target}');"),
                WaitForRequestCompletionAction(
                    url_pattern=".*/uuid.*",
                    timeout=5000,
                    ),
                ],
            disable_retry=True,
            )
        response_trace(response)

        assert response.is_proxy_error is False
        assert response.target_status_code == 200
        assert response.network_requests is not None
        assert len(response.network_requests) >= 1
        # At least one entry should be the /uuid fetch we forced.
        assert any(
            "/uuid" in (nr.url or "")
            for nr in response.network_requests
            )

    def test_websocket_requests_populates(
        self,
        default_sync_client: ScrapeDoClient,
        response_trace,
    ):
        """`show_websocket_requests=True` plus an `ExecuteAction` that
        opens a WebSocket to httpbin's `/websocket/echo` endpoint
        to populate `websocket_requests`. A trailing `WaitAction` gives
        the WS roundtrip time to settle before render completion.

        This test is specific to httpbin's WS echo endpoint (provided
        by go-httpbin); it's not a generic WebSocket capture test.
        """
        open_ws_js = (
            "const ws = new WebSocket("
            "'wss://httpbin.co/websocket/echo"
            "?max_fragment_size=2048&max_message_size=10240'); "
            "ws.onopen = () => ws.send('hello scrape.do');"
            )
        response = default_sync_client.get(
            f"{HTTPBIN_BASE}/anything",
            render=True,
            super=True,
            return_json=True,
            show_websocket_requests=True,
            play_with_browser=[
                ExecuteAction(execute=open_ws_js),
                WaitAction(timeout=5000),
                ],
            disable_retry=True,
            )
        response_trace(response)

        assert response.is_proxy_error is False
        assert response.target_status_code == 200
        assert response.websocket_requests is not None
        assert len(response.websocket_requests) >= 1
        first = response.websocket_requests[0]
        assert first.type is not None
        assert first.event is not None
        assert first.event.request_id is not None


# ---------------------------------------------------------------------------
# Async API mode - one composite test
# ---------------------------------------------------------------------------

@pytest.mark.integration
@pytest.mark.asyncio
class TestLiveRenderEnvelopeAsync:
    """One composite test that hits every covered render artifact in
    a single render. The sync suite covers the artifact-by-artifact
    parsing; this confirms the async code path produces the same shape
    against a live response."""

    async def test_full_render_envelope_populates(
        self,
        default_async_client: AsyncScrapeDoClient,
        response_trace,
    ):
        fetch_target = f"{HTTPBIN_BASE}/uuid"
        open_ws_js = (
            "const ws = new WebSocket("
            "'wss://httpbin.co/websocket/echo"
            "?max_fragment_size=2048&max_message_size=10240'); "
            "ws.onopen = () => ws.send('hello scrape.do');"
            )
        response = await default_async_client.get(
            f"{HTTPBIN_BASE}/anything",
            render=True,
            super=True,
            return_json=True,
            show_frames=True,
            show_websocket_requests=True,
            play_with_browser=[
                ExecuteAction(execute=open_ws_js),
                ExecuteAction(execute=f"fetch('{fetch_target}');"),
                WaitForRequestCompletionAction(
                    url_pattern=".*/uuid.*",
                    timeout=5000,
                    ),
                WaitAction(timeout=2000),
                ScreenShotAction(full_screenshot=True),
                ],
            disable_retry=True,
            )
        response_trace(response)

        assert response.is_proxy_error is False
        assert response.target_status_code == 200
        assert response.frames is not None and len(response.frames) >= 1
        assert (
            response.network_requests is not None
            and len(response.network_requests) >= 1
            )
        assert (
            response.action_results is not None
            and len(response.action_results) >= 1
            )
        assert (
            response.screenshots is not None
            and len(response.screenshots) >= 1
            )
        assert (
            response.websocket_requests is not None
            and len(response.websocket_requests) >= 1
            )


# ---------------------------------------------------------------------------
# Proxy mode - one composite test each
# ---------------------------------------------------------------------------

_RENDER_PROXY_WARNING = (
    "ignore:If you are using your own browser automation:UserWarning"
    )


@pytest.mark.integration
@pytest.mark.filterwarnings(_RENDER_PROXY_WARNING)
class TestLiveRenderEnvelopeSyncProxy:
    """`ScrapeDoProxyClient` end-to-end render envelope parse."""

    def test_full_render_envelope_populates(
        self,
        default_sync_proxy_client: ScrapeDoProxyClient,
        response_trace,
    ):
        fetch_target = f"{HTTPBIN_BASE}/uuid"
        open_ws_js = (
            "const ws = new WebSocket("
            "'wss://httpbin.co/websocket/echo"
            "?max_fragment_size=2048&max_message_size=10240'); "
            "ws.onopen = () => ws.send('hello scrape.do');"
            )
        response = default_sync_proxy_client.get(
            f"{HTTPBIN_BASE}/anything",
            render=True,
            super=True,
            return_json=True,
            show_frames=True,
            show_websocket_requests=True,
            play_with_browser=[
                ExecuteAction(execute=open_ws_js),
                ExecuteAction(execute=f"fetch('{fetch_target}');"),
                WaitForRequestCompletionAction(
                    url_pattern=".*/uuid.*",
                    timeout=5000,
                    ),
                WaitAction(timeout=2000),
                ScreenShotAction(full_screenshot=True),
                ],
            disable_retry=True,
            )
        response_trace(response)

        assert response.is_proxy_error is False
        assert response.target_status_code == 200
        assert response.frames is not None and len(response.frames) >= 1
        assert (
            response.network_requests is not None
            and len(response.network_requests) >= 1
            )
        assert (
            response.action_results is not None
            and len(response.action_results) >= 1
            )
        assert (
            response.screenshots is not None
            and len(response.screenshots) >= 1
            )
        assert (
            response.websocket_requests is not None
            and len(response.websocket_requests) >= 1
            )


@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.filterwarnings(_RENDER_PROXY_WARNING)
class TestLiveRenderEnvelopeAsyncProxy:
    """`AsyncScrapeDoProxyClient` end-to-end render envelope parse."""

    async def test_full_render_envelope_populates(
        self,
        default_async_proxy_client: AsyncScrapeDoProxyClient,
        response_trace,
    ):
        fetch_target = f"{HTTPBIN_BASE}/uuid"
        open_ws_js = (
            "const ws = new WebSocket("
            "'wss://httpbin.co/websocket/echo"
            "?max_fragment_size=2048&max_message_size=10240'); "
            "ws.onopen = () => ws.send('hello scrape.do');"
            )
        response = await default_async_proxy_client.get(
            f"{HTTPBIN_BASE}/anything",
            render=True,
            super=True,
            return_json=True,
            show_frames=True,
            show_websocket_requests=True,
            play_with_browser=[
                ExecuteAction(execute=open_ws_js),
                ExecuteAction(execute=f"fetch('{fetch_target}');"),
                WaitForRequestCompletionAction(
                    url_pattern=".*/uuid.*",
                    timeout=5000,
                    ),
                WaitAction(timeout=2000),
                ScreenShotAction(full_screenshot=True),
                ],
            disable_retry=True,
            )
        response_trace(response)

        assert response.is_proxy_error is False
        assert response.target_status_code == 200
        assert response.frames is not None and len(response.frames) >= 1
        assert (
            response.network_requests is not None
            and len(response.network_requests) >= 1
            )
        assert (
            response.action_results is not None
            and len(response.action_results) >= 1
            )
        assert (
            response.screenshots is not None
            and len(response.screenshots) >= 1
            )
        assert (
            response.websocket_requests is not None
            and len(response.websocket_requests) >= 1
            )
