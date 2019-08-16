from itertools import groupby
import attr
import typing


@attr.s
class RedisKeyValuePair:
    key = attr.ib()
    value = attr.ib()


@attr.s
class MetricSet:

    name: str = attr.ib()
    description: str = attr.ib(default=None)
    type: str = attr.ib(default=None)
    counts: typing.Dict = attr.ib(default=attr.Factory(dict))

    def add_item(self, kv_pair: RedisKeyValuePair):
        extension, labels = self._split_key(kv_pair.key)

        if labels is None:
            labels = ""

        if extension == "d":
            self.description = kv_pair.value

        elif extension == "t":

            if kv_pair.value == "c":
                self.type = "counter"
            elif kv_pair.value == "g":
                self.type = "gauge"
            elif kv_pair.value == "h":
                self.type = "histogram"
            elif kv_pair.value == "s":
                self.type = "summary"

        else:
            self.counts[labels] = kv_pair.value

    @staticmethod
    def _split_key(key):
        parts = key.split(":")
        name = parts[0]
        ext = parts[1]
        labels = parts[2]
        return ext, labels


class InstrumentorClient:
    """
    Very simple implementation of client that will get all available metrics from a
    namespace and expose a string formatted accoring to Prometheus expositions format.
    """

    def __init__(self, redis_client, namespace: str):
        self.redis = redis_client
        self.namespace = namespace

    def _get_data(self):
        """
        Get and parse data from Redis.
        :return:
        """

        results = self.redis.hgetall(self.namespace)

        sorted_results = sorted(
            [
                RedisKeyValuePair(key.decode(), val.decode())
                for key, val in results.items()
            ]
        )

        metrics = list()

        for metric_name, metric_items in groupby(
            sorted_results, key=lambda x: x.key.split(":")[0]
        ):
            metric = MetricSet(name=metric_name)
            for item in list(metric_items):
                metric.add_item(item)

            metrics.append(metric)
        return metrics

    def expose(self):
        """
        Returns Prometheus formatted data.
        :return:
        """
        metrics = self._get_data()
        out = ""
        for metric in metrics:
            out += f"# HELP {metric.name} {metric.description}\n"
            out += f"# TYPE {metric.name} {metric.type}\n"
            for key, val in metric.counts.items():
                if key == "":
                    out += f"{metric.name} {val}\n"
                else:
                    out += f"{metric.name}{{{key}}} {val}\n"

            out += f"\n"

        return out
