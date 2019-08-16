import pytest
import instrumentor


@pytest.fixture()
def counter(registry: instrumentor.CollectorRegistry):
    counter = instrumentor.Counter(
        name="http_total_requests", description="Test", allowed_labels=["code", "path"]
    )
    registry.register(counter)
    return counter


class TestCounter:
    def test_inc_by_1(self, counter: instrumentor.Counter):

        counter.inc()

        assert counter.counts["__"] == 1

    def test_inc_by(self, counter: instrumentor.Counter):
        counter.inc(3)

        assert counter.counts["__"] == 3

    def test_inc_with_labels(self, counter: instrumentor.Counter):
        counter.inc(3, labels={"code": "200", "path": "/api"})

        assert counter.counts['code="200",path="/api"'] == 3

    def test_inc_with_labels_in_different_order_increase_same_counter(
        self, counter: instrumentor.Counter
    ):

        counter.inc(3, labels={"code": "200", "path": "/api"})
        counter.inc(3, labels={"path": "/api", "code": "200"})

        assert counter.counts['code="200",path="/api"'] == 6

    def test_counter_type_value(self, counter: instrumentor.Counter):
        assert counter.TYPE_KEY == "c"

    def test_reset(self, counter: instrumentor.Counter):
        counter.inc()
        counter.inc(3, labels={"code": "200", "path": "/api"})
        counter.inc(3, labels={"path": "/api", "code": "200"})
        assert counter.counts != {"__": 0}
        counter.reset()
        assert counter.counts == {"__": 0}

    def test_inc_by_negative_raises_value_error(self, counter: instrumentor.Counter):
        with pytest.raises(ValueError):
            counter.inc(-1)
