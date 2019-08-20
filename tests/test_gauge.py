import pytest
import instrumentor


@pytest.fixture()
def gauge(registry: instrumentor.CollectorRegistry):
    gauge = instrumentor.Gauge(
        name="temperature_celsius",
        description="Temperature",
        allowed_labels=["location", "sensor_id"],
    )
    registry.register(gauge)
    return gauge


class TestGauge:
    def test_inc_by_1(self, gauge: instrumentor.Gauge):
        gauge.inc()
        assert gauge.counts["__"] == 1

    def test_inc_by(self, gauge: instrumentor.Gauge):
        gauge.inc(3)
        assert gauge.counts["__"] == 3

    def test_inc_by_negative_raises_value_error(self, gauge: instrumentor.Gauge):
        with pytest.raises(ValueError):
            gauge.inc(-3)

    def test_dec_by_1(self, gauge: instrumentor.Gauge):
        gauge.dec()
        assert gauge.counts["__"] == -1

    def test_dec_by(self, gauge: instrumentor.Gauge):
        gauge.dec(3)
        assert gauge.counts["__"] == -3

    def test_dec_by_negative_raises_value_error(self, gauge: instrumentor.Gauge):
        with pytest.raises(ValueError):
            gauge.dec(-3)

    def test_set(self, gauge: instrumentor.Gauge):
        gauge.set(100)
        assert gauge.counts["__"] == 100

    def test_inc_with_labels(self, gauge: instrumentor.Gauge):
        gauge.inc(3, labels={"location": "office", "sensor_id": "3"})
        assert gauge.counts['location="office",sensor_id="3"'] == 3

    def test_inc_with_labels_in_other_order_updates_same_counter(
        self, gauge: instrumentor.Gauge
    ):
        gauge.inc(3, labels={"location": "office", "sensor_id": "3"})
        gauge.inc(3, labels={"sensor_id": "3", "location": "office"})
        assert gauge.counts['location="office",sensor_id="3"'] == 6

    def test_inc_before_set_gives_redis_incrby(
        self, registry: instrumentor.CollectorRegistry, gauge: instrumentor.Gauge
    ):
        registry.register(gauge)

        gauge.inc()

        assert not list(registry.buffer.values())[0].set

    def test_inc_after_set_gives_redis_set(
        self, registry: instrumentor.CollectorRegistry, gauge: instrumentor.Gauge
    ):
        registry.register(gauge)
        gauge.set(100)
        gauge.inc()

        assert list(registry.buffer.values())[0].set

    def test_dec_before_set_gives_redis_incrby(
        self, registry: instrumentor.CollectorRegistry, gauge: instrumentor.Gauge
    ):
        registry.register(gauge)

        gauge.dec()

        assert not list(registry.buffer.values())[0].set

    def test_dec_after_set_gives_redis_set(
        self, registry: instrumentor.CollectorRegistry, gauge: instrumentor.Gauge
    ):
        registry.register(gauge)
        gauge.set(100)
        gauge.dec()

        assert list(registry.buffer.values())[0].set
