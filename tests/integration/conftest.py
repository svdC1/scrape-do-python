"""
Fixtures for the integration tests.
"""

import pytest
import pytest_asyncio
import logging
import os
from pathlib import Path
from datetime import datetime
from scrape_do.client import ScrapeDoClient
from scrape_do.async_client import AsyncScrapeDoClient
from scrape_do.proxy_client import ScrapeDoProxyClient
from scrape_do.async_proxy_client import AsyncScrapeDoProxyClient
from scrape_do.constants import DEFAULT_PROXY_SSL_CONTEXT


@pytest.fixture(scope="session", autouse=True)
def setup_integration_logging():
    """
    Creates a timestamped log file for every integration run.
    """

    # Ensure a logs directory exists at the root of the project
    # file = root > tests > integration > conftest
    log_dir = Path(__file__).resolve().parent.parent.parent / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_filename = log_dir / f"integration_{timestamp}.log"

    # Target the logger
    logger = logging.getLogger("integration_tests")
    logger.setLevel(logging.INFO)

    # Prevent the logger from duplicating messages if it's called multiple
    # times
    logger.propagate = False

    # Create file handler
    file_handler = logging.FileHandler(log_filename, encoding="utf-8")
    file_handler.setLevel(logging.INFO)

    # Readable format for manual debugging
    formatter = logging.Formatter(
        fmt=(
            "\n\n|| Time: {asctime} ||\n|| Test File: {filename} ||\n"
            "|| Test Function: {funcName} ||\n|| Message : {message} ||"
            ),
        style="{",
        datefmt="%Y-%m-%d %H:%M:%S"
        )
    file_handler.setFormatter(formatter)

    # Attach handler
    if not logger.handlers:
        logger.addHandler(file_handler)

    logger.info(f"STARTING SCRAPE.DO INTEGRATION RUN: {timestamp}")

    yield

    logger.info("INTEGRATION RUN COMPLETE.")

    # Cleanup handlers
    file_handler.close()
    logger.removeHandler(file_handler)


@pytest.fixture(scope="session", autouse=True)
def _require_api_key():
    if not os.getenv("SCRAPE_DO_API_KEY"):
        pytest.skip("SCRAPE_DO_API_KEY not set", allow_module_level=True)


@pytest.fixture
def default_sync_client():
    """
    Provides a live ScrapeDoClient with default configurations
    """
    with ScrapeDoClient() as client:
        yield client


@pytest.fixture
def no_retry_sync_client():
    """
    Provides a live ScrapeDoClient with retries disabled
    """
    with ScrapeDoClient(max_retries=0) as client:
        yield client


@pytest_asyncio.fixture
async def default_async_client():
    """
    Provides a live AsyncScrapeDoClient with default configurations.
    """
    async with AsyncScrapeDoClient() as client:
        yield client


@pytest_asyncio.fixture
async def no_retry_async_client():
    """
    Provides a live AsyncScrapeDoClient with retries disabled.
    """
    async with AsyncScrapeDoClient(max_retries=0) as client:
        yield client


@pytest.fixture
def default_sync_proxy_client():
    """
    Provides a live ScrapeDoProxyClient configured with the bundled CA
    SSL context. Same as the SDK's default — explicit here so the cert
    use is visible in the test setup.
    """
    with ScrapeDoProxyClient(
        verify=DEFAULT_PROXY_SSL_CONTEXT
    ) as client:
        yield client


@pytest.fixture
def no_retry_sync_proxy_client():
    """
    Provides a live ScrapeDoProxyClient with retries disabled and the
    bundled CA SSL context.
    """
    with ScrapeDoProxyClient(
        max_retries=0,
        verify=DEFAULT_PROXY_SSL_CONTEXT
    ) as client:
        yield client


@pytest_asyncio.fixture
async def default_async_proxy_client():
    """
    Provides a live AsyncScrapeDoProxyClient configured with the bundled
    CA SSL context.
    """
    async with AsyncScrapeDoProxyClient(
        verify=DEFAULT_PROXY_SSL_CONTEXT
    ) as client:
        yield client


@pytest_asyncio.fixture
async def no_retry_async_proxy_client():
    """
    Provides a live AsyncScrapeDoProxyClient with retries disabled and
    the bundled CA SSL context.
    """
    async with AsyncScrapeDoProxyClient(
        max_retries=0,
        verify=DEFAULT_PROXY_SSL_CONTEXT
    ) as client:
        yield client
