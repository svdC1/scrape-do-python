"""
Shared fixtures for integration and unit tests.
"""

import pytest
from scrape_do.models import RequestParameters, PreparedScrapeDoRequest


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
