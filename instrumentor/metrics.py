import functools
import contextlib
from typing import Dict, List
import time

import attr


NO_LABELS_KEY = "__"
HISTOGRAM_LABEL = "le"
SUMMARY_LABEL = "quantile"
INFINITY_FOR_HISTOGRAM = "+Inf"
TYPE_EXTENSION_LETTER = "t"
DESCRIPTION_EXTENSION_LETTER = "d"


@attr.s
class UpdateAction:
    """
    Simple dataclass to hold update data for Redis.

    :param key: Redis key
    :param value: Redis value
    :param set: Indicates if a SET command should be used to write to Redis.
    """

    key = attr.ib()
    value = attr.ib()
    set = attr.ib(default=False)


class Metric:
    """
    Base class for metrics


    :param name: Metric name
    :param description: Metric description
    :param allowed_labels: Labels that are allowed for the metric.
    """

    RESERVED_LABELS = [NO_LABELS_KEY, HISTOGRAM_LABEL, SUMMARY_LABEL]
    INTERNAL_LABELS = []
    TYPE_KEY = None

    def __init__(self, name, description, allowed_labels=None):

        self.name = name
        self.description = description
        self.allowed_labels = self._clean_allowed_labels(allowed_labels)
        self.registry = None
        self.registered_remotely = False

    def add_registry(self, registry) -> None:
        """
        Connect a registry to this metric.
        :param registry:
        :return: None
        """
        self.registry = registry

    def remove_registry(self) -> None:
        """
        Will unregister the metric in the registry so that we won't have orphaned
        objects in the registry and then remove the registry from the metric.
        :return:
        """
        self.registry = None

    def propagate(self, update_actions: List[UpdateAction]) -> None:
        """
        Will propagate counter updates up to the registry. 
        
        Metric type and description will only be propagated to redis once.
        :param update_actions: List of update actions
        :return:
        """

        if not self.registry:
            raise RuntimeError(
                f"Counter {self.name} is not yet registered in a CollectorRegistry"
            )

        to_propagate = list()

        for item in update_actions:
            # TODO: are we missing the :: after value? is that ok?
            if item.key == NO_LABELS_KEY:
                to_propagate.append(UpdateAction(key=self.name, value=item.value))

            else:
                to_propagate.append(item)

        if not self.registered_remotely:
            to_propagate.append(
                UpdateAction(key=self.metric_type_key, value=self.TYPE_KEY, set=True)
            )
            to_propagate.append(
                UpdateAction(
                    key=self.metric_description_key, value=self.description, set=True
                )
            )
            # Only propagate type and description once.
            self.registered_remotely = True

        self.registry.update_buffer(to_propagate)

    @property
    def metric_type_key(self) -> str:
        """
        Type Key should be structured as {metric_name}:{type_extension_letter}:
        :return: str
        """
        return self.make_redis_key(extension=TYPE_EXTENSION_LETTER)

    @property
    def metric_description_key(self) -> str:
        """
        Description key should be structured as {metric_name}:{description_extension_letter}
        :return: str
        """
        return self.make_redis_key(extension=DESCRIPTION_EXTENSION_LETTER)

    def _check_labels(self, labels=None) -> dict:
        """
        Raises error on not allowed labels and sorts the labels
        :param labels:
        :return: list
        """
        if not labels:
            return dict()

        for label in labels.keys():
            if label in self.RESERVED_LABELS and label not in self.INTERNAL_LABELS:
                raise ValueError(
                    f"Label name {label} is reserved for metric of class "
                    f"{self.__class__.__name__}"
                )

            if label not in self.allowed_labels and label not in self.INTERNAL_LABELS:
                raise ValueError(
                    f"Label name {label} is not an allowed label in metric {self.name}"
                )

        return labels

    def _clean_allowed_labels(self, labels=None) -> list:
        """
        Raises error on not allowed labels and sorts the labels

        :param labels: Metric labels
        :return: list
        """

        if not labels:
            return list()

        _labels = set()

        for label in labels:
            if label in self.RESERVED_LABELS:
                raise ValueError(
                    f"Label name {label} is reserved for metric of class "
                    f"{self.__class__.__name__}"
                )
            _labels.add(label)

        return list(_labels)

    def _encode_labels(self, labels=None) -> str:
        """
        Encodes all labels in the instrumento redis key format.
        Labels are always sorted to produce the same string independent of the order
        labels are typed.
        Format is {label_name}="{label_value}" which is also the Prometheus format.
        To handle the case with no lables the NO_LABELS_KEY is used.

        :param labels: Metric labels
        :return: str
        """
        if not labels:
            return NO_LABELS_KEY

        _labels = self._check_labels(labels)

        label_string = ""
        for label_name, label_value in sorted(_labels.items()):

            label_string += f'{label_name}="{label_value}",'

        return label_string[:-1]  # removes last comma

    def make_redis_key(self, name="", extension="", labels="") -> str:
        """
        Will structure the full key to be used in local and remote store.
        :param name: Metric name
        :param extension: Instrumentor metric extension
        :param labels: Metric labels
        :return:
        """
        _name = name or self.name
        if labels == NO_LABELS_KEY:
            labels = ""

        return f"{_name}:{extension}:{labels}"


class Counter(Metric):
    """
    A Counter is a monotonically increasing counter.
    """

    TYPE_KEY = "c"

    def __init__(self, name, description, allowed_labels=None):
        super().__init__(name, description, allowed_labels)

        self.counts = {NO_LABELS_KEY: 0}

    def inc(self, value: int = 1, labels: Dict[str, str] = None) -> None:
        """
        Will increase the counter for a given label combination. It does not allow
        negative values

        :param value:
        :param labels:
        :return:
        """

        if value < 0:
            raise ValueError(
                f"It is not possible to decrease a Counter. Counter was "
                f"provided negative value: {value}"
            )

        key = self._encode_labels(labels)
        current_value = self.counts.get(key, 0)
        new_value = current_value + value

        self.counts[key] = new_value

        self.propagate(
            [UpdateAction(key=self.make_redis_key(labels=key), value=new_value)]
        )

    def reset(self):
        """
        Clears all the counters and sets counter dict to initial state.
        :return:
        """
        self.counts = {NO_LABELS_KEY: 0}

    def count(self, _func=None, *, labels=None):
        """
        Decoration that will count the number of times the decorator has been used,
        ie. how many times the function is called.
        :return:
        """

        def count_decorator(func):
            @functools.wraps(func)
            def count_wrapper(*args, **kwargs):
                result = func(*args, **kwargs)
                self.inc(labels=labels)
                return result

            return count_wrapper

        if _func is None:
            return count_decorator
        else:
            return count_decorator(_func)


class Gauge(Metric):
    """
    A Gauge is a value that can increase and decrease.
    """

    TYPE_KEY = "g"

    def __init__(self, name, description, allowed_labels=None, initial_value=0):
        super().__init__(name, description, allowed_labels)

        self.counts = {NO_LABELS_KEY: initial_value}
        self.set_command_issued = set()

    def inc(self, value=1, labels: Dict[str, str] = None) -> None:
        """
        Increases the value.
        When starting up we might no know the current value of the remote metric
        store in Redis. By issuing incr commands on `inc` and `dec` we don't need to
        know the remote store state when increasing or decreasing.
        If `set` is called we have now know that the local state and remote state
        should be the same. After that we can issue changes by using the set command.

        :param value: Value to increase by
        :param labels: Metric labels
        :return:
        """

        if value < 0:
            raise ValueError(
                f"inc() only accepts positive values. If you want to decreace use dec()."
            )

        key = self._encode_labels(labels)
        current_value = self.counts.get(key, 0)
        new_value = current_value + value

        if self._check_set_command_issued(key):
            self.set(new_value, labels)

        else:
            # uses incrby and we dont need to know the current value.
            self.counts[key] = new_value
            self.propagate(
                [UpdateAction(key=self.make_redis_key(labels=key), value=new_value)]
            )

    def dec(self, value=1, labels: Dict[str, str] = None) -> None:
        """
        Decrease the value.
        When starting up we might no know the current value of the remote metric
        store in Redis. By issuing incr commands on `inc` and `dec` we don't need to
        know the remote store state when increasing or decreasing.
        If `set` is called we have now know that the local state and remote state
        should be the same. After that we can issue changes by using the set command.

        :param value: Value to decrease by
        :param labels: Metric labels
        :return:
        """
        if value < 0:
            raise ValueError(
                f"dec() only accepts positive values. If you want to increase use inc()."
            )

        key = self._encode_labels(labels)
        current_value = self.counts.get(key, 0)
        new_value = current_value - value

        if self._check_set_command_issued(key):
            self.set(new_value, labels)

        else:
            self.counts[key] = new_value
            self.propagate(
                [UpdateAction(key=self.make_redis_key(labels=key), value=new_value)]
            )

    def set(self, value, labels: Dict[str, str] = None) -> None:
        """
        Sets the value of a label combination.

        :param value: Value to set
        :param labels: Metric labels
        :return:
        """

        key = self._encode_labels(labels)

        self.counts[key] = value

        self.propagate(
            [UpdateAction(key=self.make_redis_key(labels=key), value=value, set=True)]
        )

        self.set_command_issued.add(key)

    def reset(self):
        """
        Since a gauge can go up and down we should not set the value to zero on reset
        :return:
        """
        pass

    def _check_set_command_issued(self, label_combination):
        """
        To keep track of when to use a set command or an incr commands we are tracking
        the issued set commands. Returns True if a set command been issued for the
        label combination

        :param label_combination:
        :return:
        """

        return label_combination in self.set_command_issued


class Histogram(Metric):

    """
    A histogram samples observations (usually things like request durations
    or response sizes) and counts them in configurable buckets. It also provides a
    sum of all observed values.

    A histogram with a base metric name of <basename> exposes multiple time series
    during a scrape:

    cumulative counters for the observation buckets, exposed
    as <basename>_bucket{le="<upper inclusive bound>"}

    the total sum of all observed values, exposed as <basename>_sum

    the count of events that have been observed, exposed as <basename>_count
    (identical to <basename>_bucket{le="+Inf"} above)

    """

    INTERNAL_LABELS = [HISTOGRAM_LABEL]
    TYPE_KEY = "h"

    def __init__(self, name, description, buckets=None, allowed_labels=None):
        super().__init__(name, description, allowed_labels)

        self.buckets = buckets
        self.counts = dict()
        self.sum = 0
        self.set_command_issued = set()

    def observe(self, value, labels=None):
        """
        Histograms are cumulative in prometheus so an observation should be added in
        each bucket that is equal or higher than the observation
        :param value:
        :param labels:
        :return:
        """

        for bucket in self.buckets:
            if bucket >= value:
                self._add_observed_value(bucket, labels)

        # TODO: should the sum and count be sensitive to labels?
        self._add_to_histogram_sum(value)
        self._increase_total_count()

    def _add_observed_value(self, bucket, labels=None):
        """
        Adds increases the count for a given label combination but also adds the
        bucket label to the label combination
        :param bucket: bucket to increase
        :param labels: metric labels
        :return:
        """
        bucket_label = {"le": bucket}
        if not labels:
            metric_labels = dict()
        else:
            metric_labels = labels
        all_labels = {**bucket_label, **metric_labels}
        count_key = self._encode_labels(all_labels)
        current_value = self.counts.get(count_key, 0)
        new_value = current_value + 1
        self.counts[count_key] = new_value

        self.propagate(
            [
                UpdateAction(
                    key=self.make_redis_key(labels=count_key, extension="b"),
                    value=new_value,
                )
            ]
        )

    def _add_to_histogram_sum(self, value):
        """
        Histogram has a sum that will have the sum of all observed values. When it is
        changed we also must issue a new update to the remote store.

        :param value:
        :return:
        """
        self.sum += value

        self.propagate(
            [UpdateAction(key=self.make_redis_key(extension="s"), value=self.sum)]
        )

    def _increase_total_count(self):
        """
        Histogram should keep a counter for the total number of observations. This
        counter should have the same value as the bucket counter for +Inf. And for
        every change we should propagate an update to the remote store.
        :return:
        """
        self._add_observed_value(bucket=INFINITY_FOR_HISTOGRAM)
        self.propagate(
            [
                UpdateAction(
                    key=self.make_redis_key(extension="c"),
                    value=self.counts.get('le="+Inf"'),
                )
            ]
        )

    def reset(self):
        """Resets the counters on the Histogram."""
        self.counts = dict()
        self.sum = 0

    def time(self, _func=None, *, labels=None, milliseconds=False):
        """
        Decoration that will time the functions it wraps and add the observation to the
        histogram.
        :return:
        """

        def count_decorator(func):
            @functools.wraps(func)
            def count_wrapper(*args, **kwargs):
                start = time.time()
                result = func(*args, **kwargs)
                duration = time.time() - start

                if milliseconds:
                    observed = duration * 1000
                else:
                    observed = duration

                self.observe(value=observed, labels=labels)
                return result

            return count_wrapper

        if _func is None:
            return count_decorator
        else:
            return count_decorator(_func)


def count(_func=None, *, metric, labels=None):
    """
        Decoration that will count the number of times the decorator has been used,
        ie. how many times the function is called.
        :return:
        """

    if isinstance(metric, (Counter, Gauge)):

        def count_decorator(func):
            @functools.wraps(func)
            def count_wrapper(*args, **kwargs):
                result = func(*args, **kwargs)
                metric.inc(labels=labels)
                return result

            return count_wrapper

        if _func is None:
            return count_decorator
        else:
            return count_decorator(_func)

    else:
        raise ValueError("Count decorator can only be used with Counters or Gauges.")


class timer(contextlib.ContextDecorator):
    """
    A decorator that also can be used as a context manager for timing some execution

    :param metric: Metric instance (Histogram or Summary)
    :param labels: Metric labels
    :param milliseconds: Indicates if result should be in milliseconds instead of
        seconds.
    """

    def __init__(self, *, metric, labels=None, milliseconds=False):
        self.metric = metric
        self.labels = labels
        self.milliseconds = milliseconds
        self.start_time = None

    def __enter__(self):
        self.start_time = time.time()

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        if self.milliseconds:
            observed = duration * 1000
        else:
            observed = duration

        self.metric.observe(value=observed, labels=self.labels)
