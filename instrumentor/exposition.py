# Just to test concept
from itertools import groupby
from instrumentor.metrics import KeyValuePair
import attr


@attr.s
class MetricSet:

    name = attr.ib()
    description = attr.ib()
    type = attr.ib()
    data = attr.ib()

    @classmethod
    def from_data(cls, name, data):
        pass


class InstrumentorClient:
    def __init__(self, redis_client, namespace):
        self.redis = redis_client
        self.namespace = namespace

    def get_data(self):
        results = self.redis.hgetall(self.namespace)

        lista = sorted([KeyValuePair(key, val) for key, val in results.items()])

        for k, g in groupby(lista, key=lambda x: x.key.split(b":")[0]):
            print(k)
            for item in g:
                print(item)
