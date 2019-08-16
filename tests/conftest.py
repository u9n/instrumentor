from redislite import StrictRedis
from instrumentor.registry import CollectorRegistry
import pytest


@pytest.fixture()
def redis():
    return StrictRedis(db=0)


@pytest.fixture()
def registry(redis) -> CollectorRegistry:
    namespace = "testing"
    registry = CollectorRegistry(redis_client=redis, namespace=namespace)
    return registry
