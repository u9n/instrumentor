from instrumentor.metrics import Metric, UpdateAction
from typing import List
from itertools import groupby
from contextlib import contextmanager


class CollectorRegistry:
    """
    The CollectorRegistry manages metrics and syncs updates to remote Redis store.
    """

    def __init__(self, redis_client, namespace: str, eager: bool = False):
        self.redis = redis_client
        self.namespace = namespace
        self.eager = eager
        self.metrics = dict()
        self.buffer = dict()

    def register(self, metric: Metric) -> None:
        """
        Registers the metrics in the collector and also makes the metric register the
        registry
        :param metric:
        :return:
        """
        self.metrics[metric.name] = metric
        metric.add_registry(self)

    def unregister(self, metric: Metric) -> None:
        """
        Removes a metric from the registry and makes sure the metrics removes the
        registry.
        :param metric:
        :return:
        """
        del self.metrics[metric.name]
        metric.remove_registry()

    def update_buffer(self, to_update: List[UpdateAction]) -> None:
        """
        Updates registry buffer with updates from metrics. If registry is eager it will
        also transfer buffer to remote Redis.
        :param to_update:
        :return:
        """
        for item in to_update:
            self.buffer[item.key] = item

        if self.eager:
            self.transfer()

    def transfer(self):
        """
        Transfer buffer to remote redis. When items are transferred a reset
        will be called on the metric to reset all counters.

        """
        metric_names = set()
        incr_actions = list()
        set_actions = list()

        for action in self.buffer.values():
            metric_names.add(action.key.split(":")[0])
            if action.set:
                set_actions.append(action)
            else:
                incr_actions.append(action)

        hmset_map = {action.key: action.value for action in set_actions}

        with self.pipe() as pipe:
            if hmset_map:
                pipe.hmset(self.namespace, hmset_map)
            for action in incr_actions:
                if isinstance(action.value, int):
                    pipe.hincrby(self.namespace, action.key, action.value)
                if isinstance(action.value, float):
                    pipe.hincrbyfloat(self.namespace, action.key, action.value)

        for metric_name in metric_names:
            metric = self.metrics[metric_name]
            metric.reset()

        self.buffer = dict()

    @contextmanager
    def pipe(self):
        """
        Context manager that will give a pipeline object if registry is not eager.
        Otherwise normal redis object.
                """

        pipe = self.redis.pipeline()

        yield pipe

        pipe.execute()
