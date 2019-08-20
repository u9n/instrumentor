import pytest
import instrumentor


class TestCounter:
    def test_inc_by_1(self, counter: instrumentor.Counter):

        counter.inc()

        assert counter.counts["__"] == 1

    def test_inc_by(self, counter: instrumentor.Counter):
        counter.inc(3)

        assert counter.counts["__"] == 3

    def test_inc_by_float(self, counter: instrumentor.Counter):
        counter.inc(3.5)

        assert counter.counts["__"] == 3.5

    def test_inc_with_labels(self, counter: instrumentor.Counter):
        counter.inc(3, labels={"code": "200", "path": "/api"})

        assert counter.counts['code="200",path="/api"'] == 3

    def test_inc_with_labels_in_different_order_increase_same_counter(
        self, counter: instrumentor.Counter
    ):

        counter.inc(3, labels={"code": "200", "path": "/api"})
        counter.inc(3, labels={"path": "/api", "code": "200"})

        assert counter.counts['code="200",path="/api"'] == 6

    def test_inc_counter_without_registering_raises_runtime_error(self):
        counter = instrumentor.Counter(
            name="http_total_requests",
            description="Test",
            allowed_labels=["code", "path"],
        )

        with pytest.raises(RuntimeError):
            counter.inc()

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

    def test_count_decorator(self, counter: instrumentor.Counter):
        @counter.count
        def try_count():
            print("Counting")

        try_count()
        try_count()
        try_count()

        assert counter.counts["__"] == 3

    def test_count_decorator_with_labels(self, counter: instrumentor.Counter):
        @counter.count(labels={"code": "200"})
        def try_count():
            print("Counting")

        try_count()
        try_count()
        try_count()

        assert counter.counts['code="200"'] == 3

    def test_using_reserved_labels_raises_value_error(
        self, counter: instrumentor.Counter
    ):

        with pytest.raises(ValueError):
            counter.inc(3, labels={"le": "200"})

    def test_creating_counter_with_reserved_label_raises_value_error(self):
        with pytest.raises(ValueError):
            counter = instrumentor.Counter(
                name="test", description="test", allowed_labels=["le"]
            )


class TestCountDecorator:
    def test_with_counter(self, counter: instrumentor.Counter):
        @instrumentor.count(metric=counter)
        def try_count():
            print("Counting")

        try_count()
        try_count()
        try_count()

        assert counter.counts["__"] == 3

    def test_with_counter_and_labels(self, counter: instrumentor.Counter):
        @instrumentor.count(metric=counter, labels={"code": "200"})
        def try_count():
            print("Counting")

        try_count()
        try_count()
        try_count()

        assert counter.counts['code="200"'] == 3

    def test_with_gauge(self, gauge: instrumentor.Gauge):
        @instrumentor.count(metric=gauge)
        def try_count():
            print("Counting")

        try_count()
        try_count()
        try_count()

        assert gauge.counts["__"] == 3

    def test_with_gauge_and_labels(self, gauge: instrumentor.Gauge):
        @instrumentor.count(metric=gauge, labels={"location": "main-office"})
        def try_count():
            print("Counting")

        try_count()
        try_count()
        try_count()

        assert gauge.counts['location="main-office"'] == 3

    def test_count_with_histogram_raises_value_error(
        self, histogram: instrumentor.Histogram
    ):
        with pytest.raises(ValueError):

            @instrumentor.count(metric=histogram)
            def try_count():
                print("Counting")
