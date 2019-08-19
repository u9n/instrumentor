from itertools import groupby
import attr
import typing


@attr.s
class RedisKeyValuePair:
    key = attr.ib()
    value = attr.ib()


@attr.s
class MetricValue:
    type = attr.ib()
    labels = attr.ib()
    value = attr.ib()


@attr.s
class MetricSet:

    name: str = attr.ib()
    description: str = attr.ib(default=None)
    type: str = attr.ib(default=None)
    values: typing.List[MetricValue] = attr.ib(default=attr.Factory(list))

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
        elif extension == "b":
            self.values.append(
                MetricValue(type="bucket", labels=labels, value=kv_pair.value)
            )

        elif extension == "c":
            self.values.append(
                MetricValue(type="count", labels=labels, value=kv_pair.value)
            )

        elif extension == "s":
            self.values.append(
                MetricValue(type="sum", labels=labels, value=kv_pair.value)
            )

        else:
            self.values.append(
                MetricValue(type=None, labels=labels, value=kv_pair.value)
            )

    @staticmethod
    def _split_key(key):
        parts = key.split(":")
        name = parts[0]
        ext = parts[1]
        labels = parts[2]
        return ext, labels


class ExpositionClient:
    """
    Very simple implementation of client that will get all available metrics from a
    namespace and expose a string formatted accoring to Prometheus expositions format.
    """

    def __init__(self, redis_client, namespace: str):
        self.redis = redis_client
        self.namespace = namespace

    def _get_data(self) -> typing.List[MetricSet]:
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
            for value in metric.values:

                if value.type and value.labels:
                    out += (
                        f"{metric.name}_{value.type}{{{value.labels}}} {value.value}\n"
                    )
                elif value.type and not value.labels:
                    out += f"{metric.name}_{value.type} {value.value}\n"
                elif not value.type and value.labels:
                    out += f"{metric.name}{{{value.labels}}} {value.value}\n"
                else:
                    out += f"{metric.name} {value.value}\n"

            out += f"\n"

        return out
