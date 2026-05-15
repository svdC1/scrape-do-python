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
# Logging setup (lazy: file handler attached on first test start)
# ---------------------------------------------------------------------------
#
# `pytest_configure` prepares the log directory but does NOT create the
# file handler.
#
# The handler is attached on the FIRST `pytest_runtest_logstart` so that
# - The very first test's `---> START` boundary lands in the file
# - Runs that never execute an integration test don't create empty log files
#   containing only the START / COMPLETE entries.

_file_handler: Optional[logging.FileHandler] = None
_log_filename: Optional[Path] = None


def pytest_configure(config):
    """Prepares the log directory and target filename, but defers
    actually creating the file until the first test starts."""
    global _log_filename
    # file = root > tests > integration > conftest
    log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    _log_filename = log_dir / f"integration_{timestamp}.log"


def _ensure_log_handler() -> None:
    """Attaches the file handler on first call. Idempotent."""
    global _file_handler

    # All subsequent calls use existing the existing file handler
    if _file_handler is not None or _log_filename is None:
        return

    logger = logging.getLogger("integration_tests")
    logger.setLevel(logging.INFO)
    logger.propagate = False

    _file_handler = logging.FileHandler(_log_filename, encoding="utf-8")
    _file_handler.setLevel(logging.INFO)
    _file_handler.addFilter(_NodeIDFilter())
    _file_handler.setFormatter(
        logging.Formatter(
            fmt="{asctime} [{levelname}] [{test_id}] {message}",
            style="{",
            datefmt="%H:%M:%S",
            )
        )
    logger.addHandler(_file_handler)
    logger.info(
        f"STARTING SCRAPE.DO INTEGRATION RUN "
        f"@ {datetime.now().strftime('%Y-%m-%d_%H-%M-%S')}"
        )


def pytest_unconfigure(config):
    """Closes and removes the integration log file handler at session
    end. No-op if no test ever started (file was never created)."""
    global _file_handler
    if _file_handler is None:
        return
    logger = logging.getLogger("integration_tests")
    logger.info("INTEGRATION RUN COMPLETE.")
    _file_handler.close()
    logger.removeHandler(_file_handler)
    _file_handler = None


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
    """Emits a START boundary entry for every test. Attaches the file
    handler on the first call so the log file isn't created for empty
    runs (collect-only, no-match filter, etc.)."""
    _ensure_log_handler()
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


def _is_binary_content_type(content_type: str) -> bool:
    """Returns True for content types whose text decode is meaningless
    (images, archives, binary streams)."""
    if not content_type:
        return False
    content_type = content_type.lower().split(";", 1)[0].strip()
    if content_type.startswith(("image/", "video/", "audio/")):
        return True
    if content_type in {
        "application/octet-stream",
        "application/pdf",
        "application/zip",
        "application/x-tar",
        "application/gzip",
    }:
        return True
    return False


@pytest.fixture
def response_trace() -> Callable[..., None]:
    """Returns a callable that logs a structured trace of any
    `ScrapeDoResponse` (error or success) and optionally asserts
    `is_proxy_error`.

    By default the trace logs every public field on the response and
    every field on the parsed Scrape.do error envelope (when present).
    Sections can be suppressed via boolean kwargs when the noise gets
    in the way of a particular test.

    Sections (always-on identity + verdict, then toggleable groups):

    - **Always**: `target_url`, `status_code` (httpx alias),
      `request.method`, `request.api_params.url` (the URL the test
      originally asked for, distinct from the proxy-reported
      `target_url`), `initial_status_header`, `is_proxy_error`,
      `scrape_do_status_code`, `target_status_code`,
      `initial_status_code`.
    - **`include_body=True`**: `body_len` + a preview. When the
      response Content-Type looks binary AND `binary_detect=True`, the
      preview is a hex snippet of `raw.content` instead of the
      best-effort text decode. `body_preview_len` controls how many
      bytes / chars are shown.
    - **`include_telemetry=True`**: `request_cost`, `remaining_credits`,
      `request_id`, `rid`, `rate`, `auth`, `resolved_url`.
    - **`include_headers=True`**: header counts for both
      `target_headers` and `scrape_do_headers`. With
      `verbatim_headers=True`, dumps each header dict verbatim.
    - **`include_cookies=True`**: cookies count (or `None` when the
      cookies property returned `None` rather than an empty jar).
      With `verbatim_cookies=True`, dumps the full cookies dict.
    - **`include_artifacts=True`**: browser-render artifacts -
      `frames`, `network_requests`, `websocket_requests`,
      `action_results`, `screenshots`. Shows count plus a first-item
      peek. With `verbatim_artifacts=True`, dumps every item via
      `model_dump()` instead of a peek.
    - **`include_envelope=True`**: every field on the parsed
      `ScrapeDoJSONErrorMessage`. Logs `envelope=None` when no
      parseable error body is present.

    All field accesses are guarded so partial / unexpected response
    shapes never crash the trace.

    Args:
        response (ScrapeDoResponse): The response to trace.
        expected_is_proxy_error (Optional[bool]): If provided, asserts
            `response.is_proxy_error is expected_is_proxy_error`.
        include_body (bool): Show body length + preview (or hex
            preview for binary). Defaults to True.
        include_telemetry (bool): Show success-path telemetry.
            Defaults to True.
        include_headers (bool): Show header counts (or verbatim if
            `verbatim_headers=True`). Defaults to True.
        include_cookies (bool): Show cookies count (or verbatim if
            `verbatim_cookies=True`). Defaults to True.
        include_artifacts (bool): Show browser-render artifact counts
            and first-item peeks (or verbatim if
            `verbatim_artifacts=True`). Defaults to True.
        include_envelope (bool): Show the parsed Scrape.do error
            envelope. Defaults to True.
        body_preview_len (int): Max characters (or bytes for binary)
            of body preview. Defaults to 500.
        binary_detect (bool): Sniff Content-Type and render binary
            bodies as a hex preview. Defaults to True.
        verbatim_headers (bool): Dump full header dicts instead of
            counts. Defaults to False.
        verbatim_cookies (bool): Dump full cookies dict instead of
            count. Defaults to False.
        verbatim_artifacts (bool): Dump every artifact item via
            `model_dump()` instead of a first-item peek. Defaults to
            False.

    Returns:
        None. Side effect is logging.
    """
    logger = logging.getLogger("integration_tests")

    def _trace(
        response: ScrapeDoResponse,
        expected_is_proxy_error: Optional[bool] = None,
        *,
        include_body: bool = True,
        include_telemetry: bool = True,
        include_headers: bool = True,
        include_cookies: bool = True,
        include_artifacts: bool = True,
        include_envelope: bool = True,
        body_preview_len: int = 500,
        binary_detect: bool = True,
        verbatim_headers: bool = False,
        verbatim_cookies: bool = False,
        verbatim_artifacts: bool = False,
    ) -> None:
        raw = response.httpx_response

        # --- Always-on: identity + SDK verdict ---
        logger.info("[trace] Scrape.do raw response")
        logger.info(f"[trace] target_url={response.target_url}")
        logger.info(f"[trace] status_code={response.status_code}")
        logger.info(
            f"[trace] request.method={response.request.method}"
            )
        logger.info(
            f"[trace] request.api_params.url="
            f"{response.request.api_params.url}"
            )
        logger.info(
            f"[trace] initial_status_header="
            f"{raw.headers.get('scrape.do-initial-status-code', 'missing')}"
            )
        logger.info(
            f"[trace] sdk_verdict.is_proxy_error={response.is_proxy_error}"
            )
        logger.info(
            f"[trace] scrape_do_status_code={response.scrape_do_status_code}"
            )
        logger.info(
            f"[trace] target_status_code={response.target_status_code}"
            )
        logger.info(
            f"[trace] initial_status_code={response.initial_status_code}"
            )

        # --- Body (with binary detection) ---
        if include_body:
            content_type = raw.headers.get("content-type", "")
            is_binary = (
                binary_detect and _is_binary_content_type(content_type)
                )
            if is_binary:
                preview = raw.content[:body_preview_len].hex()
                logger.info(
                    f"[trace] body_len={len(raw.content)} (binary,"
                    f" content_type={content_type!r})"
                    )
                logger.info(
                    f"[trace] body[:{body_preview_len}]_hex={preview}"
                    )
            else:
                text = raw.text
                logger.info(f"[trace] body_len={len(text)}")
                logger.info(
                    f"[trace] body[:{body_preview_len}]="
                    f"{text[:body_preview_len]!r}"
                    )

        # --- Telemetry ---
        if include_telemetry:
            logger.info(f"[trace] request_cost={response.request_cost}")
            logger.info(
                f"[trace] remaining_credits={response.remaining_credits}"
                )
            logger.info(f"[trace] request_id={response.request_id}")
            logger.info(f"[trace] rid={response.rid}")
            logger.info(f"[trace] rate={response.rate}")
            logger.info(f"[trace] auth={response.auth}")
            logger.info(f"[trace] resolved_url={response.resolved_url}")

        # --- Headers (count or verbatim) ---
        if include_headers:
            try:
                target_hdrs = response.target_headers
                if verbatim_headers:
                    logger.info(
                        f"[trace] target_headers={dict(target_hdrs)!r}"
                        )
                else:
                    logger.info(
                        f"[trace] target_headers_count="
                        f"{_safe_len(target_hdrs)}"
                        )
            except Exception as exc:  # noqa: BLE001
                logger.info(f"[trace] target_headers_error={exc!r}")

            try:
                sd_hdrs = response.scrape_do_headers
                if verbatim_headers:
                    sd_dict = (
                        dict(sd_hdrs) if sd_hdrs is not None else None
                        )
                    logger.info(f"[trace] scrape_do_headers={sd_dict!r}")
                else:
                    logger.info(
                        f"[trace] scrape_do_headers_count="
                        f"{_safe_len(sd_hdrs)}"
                        )
            except Exception as exc:  # noqa: BLE001
                logger.info(f"[trace] scrape_do_headers_error={exc!r}")

        # --- Cookies (count or verbatim) ---
        if include_cookies:
            try:
                cookies = response.cookies
                if verbatim_cookies:
                    c_dict = (
                        dict(cookies) if cookies is not None else None
                        )
                    logger.info(f"[trace] cookies={c_dict!r}")
                else:
                    count = (
                        _safe_len(cookies)
                        if cookies is not None
                        else "None"
                        )
                    logger.info(f"[trace] cookies_count={count}")
            except Exception as exc:  # noqa: BLE001
                logger.info(f"[trace] cookies_error={exc!r}")

        # --- Browser-render artifacts ---
        if include_artifacts:
            for label, items, peek in (
                (
                    "frames",
                    response.frames,
                    lambda x: f"url={x.url!r}",
                ),
                (
                    "network_requests",
                    response.network_requests,
                    lambda x: (
                        f"{x.method} {x.url!r} -> {x.status}"
                    ),
                ),
                (
                    "websocket_requests",
                    response.websocket_requests,
                    lambda x: f"type={x.type!r}",
                ),
                (
                    "action_results",
                    response.action_results,
                    lambda x: (
                        f"action={x.action!r} success={x.success}"
                    ),
                ),
                (
                    "screenshots",
                    response.screenshots,
                    lambda x: (
                        f"screenshot_type={x.screenshot_type!r}"
                    ),
                ),
            ):
                logger.info(
                    f"[trace] {label}_count={_safe_len(items)}"
                    )
                if not items:
                    continue
                if verbatim_artifacts:
                    for i, item in enumerate(items):
                        logger.info(
                            f"[trace] {label}[{i}]={item.model_dump()!r}"
                            )
                else:
                    first = _safe_first(items)
                    if first is not None:
                        logger.info(
                            f"[trace] {label}[0]={peek(first)}"
                            )

        # --- Scrape.do error envelope (full field dump) ---
        if include_envelope:
            envelope = ScrapeDoJSONErrorMessage.try_from_response(raw)
            if envelope is not None:
                logger.info(
                    f"[trace] envelope.status_code={envelope.status_code}"
                    )
                logger.info(
                    f"[trace] envelope.error_code={envelope.error_code}"
                    )
                logger.info(
                    f"[trace] envelope.error_type={envelope.error_type!r}"
                    )
                logger.info(f"[trace] envelope.url={envelope.url!r}")
                logger.info(
                    f"[trace] envelope.contact={envelope.contact!r}"
                    )
                logger.info(
                    f"[trace] envelope.messages={envelope.messages!r}"
                    )
                logger.info(
                    f"[trace] envelope.possible_causes="
                    f"{envelope.possible_causes!r}"
                    )
            else:
                logger.info(
                    "[trace] envelope=None (no parseable error body)"
                    )

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
