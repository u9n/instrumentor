import pytest
import instrumentor
import time


class TestHistogram:
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


class TestTimerDecorator:
    def test_with_histogram(self, histogram: instrumentor.Histogram):
        @instrumentor.timer(metric=histogram)
        def time_it():
            time.sleep(0.0001)

        time_it()

        assert histogram.sum > 0
        assert histogram.counts['le="+Inf"'] == 1

    def test_with_histogram_context_manager(self, histogram: instrumentor.Histogram):

        with instrumentor.timer(metric=histogram):
            time.sleep(0.0001)

        assert histogram.sum > 0
        assert histogram.counts['le="+Inf"'] == 1
