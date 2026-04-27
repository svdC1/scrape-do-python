import pytest


@pytest.fixture
def example_url():
    """
    Provides a valid fake url to be used for model testing

    Returns:
        str: A valid fake url
    """
    return "https://example.com/"
