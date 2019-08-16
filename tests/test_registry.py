import pytest
from redislite import StrictRedis
from instrumentor import CollectorRegistry
from instrumentor import Counter
from instrumentor.metrics import UpdateAction


class TestCollectorRegistry:
    def test_register_counter(self, registry: CollectorRegistry):

        counter = Counter(name="http_requests_total", description="Total HTTP Requests")
        registry.register(counter)

        assert registry.metrics[counter.name] == counter
        assert registry.metrics[counter.name].registry == registry

    def test_unregister_counter(self, registry: CollectorRegistry):
        counter = Counter(name="http_requests_total", description="Total HTTP Requests")
        registry.register(counter)

        assert registry.metrics[counter.name] == counter
        assert registry.metrics[counter.name].registry == registry

        registry.unregister(counter)

        with pytest.raises(KeyError):
            x = registry.metrics[counter.name]

        assert counter.registry is None

    def test_not_eager(self, registry: CollectorRegistry, redis: StrictRedis):
        counter = Counter(name="http_requests_total", description="Total HTTP Requests")
        registry.register(counter)

        assert not registry.eager

        counter.inc()

        assert redis.hgetall("testing") == {}

        registry.transfer()

        assert redis.hgetall("testing") != {}

    def test_eager(self, registry: CollectorRegistry, redis: StrictRedis):
        counter = Counter(name="http_requests_total", description="Total HTTP Requests")
        registry.eager = True
        registry.register(counter)

        assert registry.eager

        counter.inc()

        assert redis.hgetall("testing") != {}

    def test_update_buffer(self, registry: CollectorRegistry):
        test_key = "test"
        test_value = 1
        test_action = UpdateAction(key=test_key, value=test_value, set=False)
        to_update = [test_action]

        registry.update_buffer(to_update)

        assert registry.buffer[test_key] == test_action
