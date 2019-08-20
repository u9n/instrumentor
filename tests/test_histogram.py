import pytest
import instrumentor
import time


class TestHistogram:
    def test_observe_1(self, histogram: instrumentor.Histogram):
        histogram.observe(0.22)

        assert histogram.sum == 0.22

        assert histogram.counts['le="0.4"'] == 1
        assert histogram.counts['le="0.8"'] == 1
        assert histogram.counts['le="1.6"'] == 1
        assert histogram.counts['le="+Inf"'] == 1
        assert histogram.total_count == 1

    def test_observe_2(self, histogram: instrumentor.Histogram):
        histogram.observe(0.22)
        histogram.observe(0.78)

        assert histogram.sum == 1
        assert histogram.counts['le="0.4"'] == 1
        assert histogram.counts['le="0.8"'] == 2
        assert histogram.counts['le="1.6"'] == 2
        assert histogram.counts['le="+Inf"'] == 2
        assert histogram.total_count == 2

    def test_observe_1_with_labels(self, histogram: instrumentor.Histogram):
        histogram.observe(0.22, labels={"code": "200"})

        assert histogram.sum == 0.22

        assert histogram.counts['code="200",le="0.4"'] == 1
        assert histogram.counts['code="200",le="0.8"'] == 1
        assert histogram.counts['code="200",le="1.6"'] == 1
        assert histogram.counts['le="+Inf"'] == 1
        assert histogram.total_count == 1

    def test_observe_2(self, histogram: instrumentor.Histogram):
        histogram.observe(0.22, labels={"code": "200"})
        histogram.observe(0.78, labels={"code": "200"})

        assert histogram.sum == 1
        assert histogram.counts['code="200",le="0.4"'] == 1
        assert histogram.counts['code="200",le="0.8"'] == 2
        assert histogram.counts['code="200",le="1.6"'] == 2
        assert histogram.counts['le="+Inf"'] == 2
        assert histogram.total_count == 2

    def test_time_decorator(self, histogram: instrumentor.Histogram):
        @histogram.time
        def time_it():
            time.sleep(0.0001)

        time_it()

        assert histogram.sum > 0
        assert histogram.counts['le="+Inf"'] == 1

    def test_time_decorator_with_label(self, histogram: instrumentor.Histogram):
        @histogram.time(labels={"code": "200"})
        def time_it():
            time.sleep(0.0001)

        time_it()
        assert histogram.sum > 0
        assert histogram.counts['code="200",le="1.6"'] == 1

    def test_reset(self, histogram: instrumentor.Histogram):
        histogram.reset()

        assert histogram.counts == dict()
        assert histogram.sum == 0

    # TODO: test all counting works.


class TestTimerDecorator:
    def test_with_histogram(self, histogram: instrumentor.Histogram):
        @instrumentor.timer(metric=histogram)
        def time_it():
            time.sleep(0.0001)

        time_it()

        assert histogram.sum > 0
        assert histogram.counts['le="+Inf"'] == 1

    def test_with_histogram_and_milliseconds(self, histogram: instrumentor.Histogram):
        @instrumentor.timer(metric=histogram, milliseconds=True)
        def time_it():
            time.sleep(0.1)

        time_it()

        assert histogram.sum > 10
        assert histogram.counts['le="+Inf"'] == 1

    def test_with_histogram_context_manager(self, histogram: instrumentor.Histogram):

        with instrumentor.timer(metric=histogram):
            time.sleep(0.0001)

        assert histogram.sum > 0
        assert histogram.counts['le="+Inf"'] == 1
