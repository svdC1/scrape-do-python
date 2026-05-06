"""
Fixtures for the integration tests.
"""

import pytest
import logging
import os
from pathlib import Path
from datetime import datetime
from scrape_do.client import ScrapeDoClient


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
        "\n=======================================================\n"
        "%(asctime)s | %(levelname)s\n"
        "-------------------------------------------------------\n"
        "%(message)s",
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
