import pytest
from django.core.cache import cache


@pytest.fixture(autouse=True)
def clear_cache():
    """Reset rate limits (stored in the cache) between tests, so one test's
    requests never count against the next test."""
    cache.clear()
    yield
    cache.clear()
