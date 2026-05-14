"""
Fixtures and pytest hooks for the integration tests.

Logging design
--------------
- A `ContextVar` (`_current_test_id`) tracks the pytest nodeid for the
  currently-running test. A logger filter reads it on every record and
  attaches `record.test_id`.
- An autouse function-scoped fixture pushes the nodeid into the contextvar
  on enter and resets it on exit.
- Pytest hooks (`pytest_runtest_logstart`, `pytest_runtest_logreport`) emit
  explicit START / PASS / FAIL / SKIP boundary entries so a long log file
  is easy to scan.
- Format is single-line: `{asctime} [{levelname}] [{test_id}] {message}`.

Shared helpers
--------------
- `_redact_token`: strips the `token=...` query parameter from a URL string
  before logging. Used by `response_trace` and available to test modules.
- `response_trace` fixture: returns a callable that logs a structured trace
  of a `ScrapeDoResponse` (raw status, headers, body preview, parsed
  Scrape.do error envelope, SDK verdict) and optionally asserts
  `is_proxy_error`.
"""

import pytest
import pytest_asyncio
import logging
import os
import re
import contextvars
from pathlib import Path
from datetime import datetime
from typing import Callable, Optional
from scrape_do.client import ScrapeDoClient
from scrape_do.async_client import AsyncScrapeDoClient
from scrape_do.proxy_client import ScrapeDoProxyClient
from scrape_do.async_proxy_client import AsyncScrapeDoProxyClient
from scrape_do.constants import DEFAULT_PROXY_SSL_CONTEXT
from scrape_do.exceptions import ScrapeDoJSONErrorMessage
from scrape_do.models import ScrapeDoResponse


# ---------------------------------------------------------------------------
# Test ID context for log records
# ---------------------------------------------------------------------------

_current_test_id: contextvars.ContextVar[str] = contextvars.ContextVar(
    "current_test_id", default="<setup>"
    )


class _NodeIDFilter(logging.Filter):
    """Attaches the current pytest nodeid to every log record as
    `record.test_id`."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.test_id = _current_test_id.get()
        return True


# ---------------------------------------------------------------------------
# Token redaction utility
# ---------------------------------------------------------------------------

_TOKEN_RE = re.compile(r"(?i)([?&]token=)[^&]+")


def _redact_token(url) -> str:
    """Strip the `token=...` query parameter from a URL string."""
    return _TOKEN_RE.sub(r"\1REDACTED", str(url))


# ---------------------------------------------------------------------------
# Logging setup (session-scoped)
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def setup_integration_logging():
    """Creates a timestamped log file for every integration run.

    Single-line format with the current test's nodeid as a prefix so each
    entry can be scanned independently. START / PASS / FAIL / SKIP
    boundaries are emitted by `pytest_runtest_logstart` and
    `pytest_runtest_logreport`.
    """
    # file = root > tests > integration > conftest
    log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_filename = log_dir / f"integration_{timestamp}.log"

    logger = logging.getLogger("integration_tests")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    file_handler = logging.FileHandler(log_filename, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.addFilter(_NodeIDFilter())

    formatter = logging.Formatter(
        fmt="{asctime} [{levelname}] [{test_id}] {message}",
        style="{",
        datefmt="%H:%M:%S",
        )
    file_handler.setFormatter(formatter)

    if not logger.handlers:
        logger.addHandler(file_handler)

    logger.info(f"STARTING SCRAPE.DO INTEGRATION RUN @ {timestamp}")

    yield

    logger.info("INTEGRATION RUN COMPLETE.")
    file_handler.close()
    logger.removeHandler(file_handler)


# ---------------------------------------------------------------------------
# Autouse fixture: push nodeid into the contextvar
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _log_test_nodeid(request: pytest.FixtureRequest):
    """Sets the current test's nodeid in a contextvar so the logger filter
    can prefix every record with it. Resets on exit."""
    token = _current_test_id.set(request.node.nodeid)
    try:
        yield
    finally:
        _current_test_id.reset(token)


# ---------------------------------------------------------------------------
# Pytest hooks for START / PASS / FAIL / SKIP boundaries
# ---------------------------------------------------------------------------

def pytest_runtest_logstart(nodeid: str, location):
    """Emits a START boundary entry for every test."""
    logger = logging.getLogger("integration_tests")
    token = _current_test_id.set(nodeid)
    try:
        logger.info(f"---> START {nodeid}")
    finally:
        _current_test_id.reset(token)


def pytest_runtest_logreport(report):
    """Emits a PASS / FAIL / SKIP boundary entry after the call phase."""
    if report.when != "call":
        return
    logger = logging.getLogger("integration_tests")
    token = _current_test_id.set(report.nodeid)
    try:
        outcome = report.outcome.upper()
        logger.info(
            f"<--- {outcome} {report.nodeid} ({report.duration:.2f}s)"
            )
    finally:
        _current_test_id.reset(token)


# ---------------------------------------------------------------------------
# Response trace helper
# ---------------------------------------------------------------------------

def _safe_first(items) -> object:
    """Return the first item of a sequence, or None if empty / None.
    Used in `response_trace` to defensively probe optional list fields
    (e.g. envelope.messages, response.frames) without IndexError."""
    try:
        return items[0] if items else None
    except (TypeError, IndexError):
        return None


def _safe_len(items) -> object:
    """Return `len(items)` or `0` for None / non-sized objects."""
    try:
        return len(items) if items is not None else 0
    except TypeError:
        return 0


@pytest.fixture
def response_trace() -> Callable[..., None]:
    """Returns a callable that logs a structured trace of any
    `ScrapeDoResponse` (error or success) and optionally asserts
    `is_proxy_error`.

    The trace covers the full response surface so it's useful regardless
    of what the test is checking:

    - Raw httpx state (status, initial-status header, body preview).
    - SDK verdict (`is_proxy_error`, `scrape_do_status_code`,
      `target_status_code`).
    - Telemetry (`request_cost`, `remaining_credits`, `request_id`,
      `rid`, `rate`, `auth`, `resolved_url`).
    - Header counts (`target_headers`, `scrape_do_headers`).
    - Cookies (count or None).
    - Browser-render artifacts (`frames`, `network_requests`,
      `websocket_requests`, `action_results`, `screenshots`) as counts
      so tests touching render paths can see population at a glance.
    - Scrape.do error envelope (`error_code`, `error_type`, first
      message, first possible cause) when present.

    All field accesses are guarded so a partial / unexpected response
    shape never crashes the trace.

    Args:
        response (ScrapeDoResponse): The response to trace.
        expected_is_proxy_error (Optional[bool]): If provided, asserts
            `response.is_proxy_error is expected_is_proxy_error`.

    Returns:
        None. Side effect is logging.
    """
    logger = logging.getLogger("integration_tests")

    def _trace(
        response: ScrapeDoResponse,
        expected_is_proxy_error: Optional[bool] = None,
    ) -> None:
        raw = response.httpx_response

        # --- Raw transport state ---
        logger.info("[trace] Scrape.do raw response")
        logger.info(f"[trace] target_url={response.target_url}")
        logger.info(f"[trace] httpx_status={raw.status_code}")
        logger.info(
            f"[trace] initial_status_header="
            f"{raw.headers.get('scrape.do-initial-status-code', 'missing')}"
            )
        logger.info(f"[trace] body_len={len(raw.text)}")
        logger.info(f"[trace] body[:200]={raw.text[:200]!r}")

        # --- SDK verdict ---
        logger.info(
            f"[trace] sdk_verdict.is_proxy_error={response.is_proxy_error}"
            )
        logger.info(
            f"[trace] scrape_do_status={response.scrape_do_status_code}"
            )
        logger.info(
            f"[trace] target_status={response.target_status_code}"
            )

        # --- Telemetry (success-path fields) ---
        logger.info(f"[trace] request_cost={response.request_cost}")
        logger.info(
            f"[trace] remaining_credits={response.remaining_credits}"
            )
        logger.info(f"[trace] request_id={response.request_id}")
        logger.info(f"[trace] rid={response.rid}")
        logger.info(f"[trace] rate={response.rate}")
        logger.info(f"[trace] auth={response.auth}")
        logger.info(f"[trace] resolved_url={response.resolved_url}")

        # --- Header / cookie counts (cheap structural info) ---
        try:
            target_hdrs = response.target_headers
            logger.info(
                f"[trace] target_headers_count={_safe_len(target_hdrs)}"
                )
        except Exception as exc:  # noqa: BLE001
            logger.info(f"[trace] target_headers_error={exc!r}")

        try:
            sd_hdrs = response.scrape_do_headers
            logger.info(
                f"[trace] scrape_do_headers_count={_safe_len(sd_hdrs)}"
                )
        except Exception as exc:  # noqa: BLE001
            logger.info(f"[trace] scrape_do_headers_error={exc!r}")

        try:
            cookies = response.cookies
            logger.info(
                f"[trace] cookies_count="
                f"{_safe_len(cookies) if cookies is not None else 'None'}"
                )
        except Exception as exc:  # noqa: BLE001
            logger.info(f"[trace] cookies_error={exc!r}")

        # --- Browser-render artifacts (counts only - cheap and useful) ---
        logger.info(
            f"[trace] frames_count={_safe_len(response.frames)}"
            )
        logger.info(
            f"[trace] network_requests_count="
            f"{_safe_len(response.network_requests)}"
            )
        logger.info(
            f"[trace] websocket_requests_count="
            f"{_safe_len(response.websocket_requests)}"
            )
        logger.info(
            f"[trace] action_results_count="
            f"{_safe_len(response.action_results)}"
            )
        logger.info(
            f"[trace] screenshots_count={_safe_len(response.screenshots)}"
            )

        # --- Scrape.do error envelope (when present) ---
        # Lean on the SDK's own parser so the trace stays in sync with
        # the canonical schema.
        envelope = ScrapeDoJSONErrorMessage.try_from_response(raw)
        if envelope is not None:
            logger.info(
                f"[trace] envelope.error_code={envelope.error_code}"
                )
            logger.info(
                f"[trace] envelope.error_type={envelope.error_type}"
                )
            logger.info(
                f"[trace] envelope.messages[0]="
                f"{_safe_first(envelope.messages)!r}"
                )
            logger.info(
                f"[trace] envelope.possible_causes[0]="
                f"{_safe_first(envelope.possible_causes)!r}"
                )
        else:
            logger.info("[trace] envelope=None (no parseable error body)")

        if expected_is_proxy_error is not None:
            assert response.is_proxy_error is expected_is_proxy_error

    return _trace


# ---------------------------------------------------------------------------
# Environment guard
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def _require_api_key():
    if not os.getenv("SCRAPE_DO_API_KEY"):
        pytest.skip("SCRAPE_DO_API_KEY not set", allow_module_level=True)


# ---------------------------------------------------------------------------
# Client fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def default_sync_client():
    """Provides a live ScrapeDoClient with default configurations."""
    with ScrapeDoClient() as client:
        yield client


@pytest.fixture
def no_retry_sync_client():
    """Provides a live ScrapeDoClient with retries disabled."""
    with ScrapeDoClient(max_retries=0) as client:
        yield client


@pytest_asyncio.fixture
async def default_async_client():
    """Provides a live AsyncScrapeDoClient with default configurations."""
    async with AsyncScrapeDoClient() as client:
        yield client


@pytest_asyncio.fixture
async def no_retry_async_client():
    """Provides a live AsyncScrapeDoClient with retries disabled."""
    async with AsyncScrapeDoClient(max_retries=0) as client:
        yield client


@pytest.fixture
def default_sync_proxy_client():
    """Provides a live ScrapeDoProxyClient configured with the bundled CA
    SSL context. Same as the SDK's default - explicit here so the cert
    use is visible in the test setup.
    """
    with ScrapeDoProxyClient(
        verify=DEFAULT_PROXY_SSL_CONTEXT
    ) as client:
        yield client


@pytest.fixture
def no_retry_sync_proxy_client():
    """Provides a live ScrapeDoProxyClient with retries disabled and the
    bundled CA SSL context."""
    with ScrapeDoProxyClient(
        max_retries=0,
        verify=DEFAULT_PROXY_SSL_CONTEXT
    ) as client:
        yield client


@pytest_asyncio.fixture
async def default_async_proxy_client():
    """Provides a live AsyncScrapeDoProxyClient configured with the bundled
    CA SSL context."""
    async with AsyncScrapeDoProxyClient(
        verify=DEFAULT_PROXY_SSL_CONTEXT
    ) as client:
        yield client


@pytest_asyncio.fixture
async def no_retry_async_proxy_client():
    """Provides a live AsyncScrapeDoProxyClient with retries disabled and
    the bundled CA SSL context."""
    async with AsyncScrapeDoProxyClient(
        max_retries=0,
        verify=DEFAULT_PROXY_SSL_CONTEXT
    ) as client:
        yield client
