from redislite import StrictRedis
import instrumentor
import pytest


@pytest.fixture()
def redis():
    return StrictRedis(db=0)


@pytest.fixture()
def registry(redis) -> instrumentor.CollectorRegistry:
    namespace = "testing"
    registry = instrumentor.CollectorRegistry(redis_client=redis, namespace=namespace)
    return registry


@pytest.fixture()
def counter(registry: instrumentor.CollectorRegistry):
    counter = instrumentor.Counter(
        name="http_total_requests", description="Test", allowed_labels=["code", "path"]
    )
    registry.register(counter)
    return counter


@pytest.fixture()
def gauge(registry: instrumentor.CollectorRegistry):
    gauge = instrumentor.Gauge(
        name="temperature_celsius",
        description="Temperature Celsius",
        allowed_labels=["location", "id"],
    )
    registry.register(gauge)
    return gauge


@pytest.fixture()
def histogram(registry: instrumentor.CollectorRegistry):
    histogram = instrumentor.Histogram(
        name="http_response_time_seconds",
        description="HTTP Response Time in seconds.",
        buckets=[0.1, 0.2, 0.4, 0.8, 1.6],
        allowed_labels=["code"],
    )

    registry.register(histogram)
    return histogram
