from typing import Dict, List

import attr


NO_LABELS_KEY = "__"
HISTOGRAM_LABEL = "le"
SUMMARY_LABEL = "quantile"
TYPE_EXTENSION_LETTER = "t"
DESCRIPTION_EXTENSION_LETTER = "d"


@attr.s
class KeyValuePair:

    key = attr.ib()
    value = attr.ib()


@attr.s
class UpdateAction:
    key = attr.ib()
    value = attr.ib()
    set = attr.ib(default=False)


class Metric:
    """Base class for metrics"""

    RESERVED_LABELS = [NO_LABELS_KEY, HISTOGRAM_LABEL, SUMMARY_LABEL]
    TYPE_KEY = None

    def __init__(self, name, description, allowed_labels=None):

        self.name = name
        self.description = description
        self.allowed_labels = self._clean_labels(allowed_labels)
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

    def propagate(self, kw_list: List[UpdateAction]):
        """
        Will propagate counter updates up to the registry. We will only propagate the
        metric type and description before they have been registered remotely.
        :param kw_list:
        :return:
        """

        if not self.registry:
            raise RuntimeError(
                f"Counter {self.name} is not yet registered in a CollectorRegistry"
            )

        to_propagate = list()

        for item in kw_list:
            if item.key == NO_LABELS_KEY:
                to_propagate.append(UpdateAction(key=self.name, value=item.value))

            else:
                to_propagate.append(item)

        if not self.registered_remotely:
            to_propagate.append(
                UpdateAction(key=self._type_key, value=self.TYPE_KEY, set=True)
            )
            to_propagate.append(
                UpdateAction(
                    key=self._description_key, value=self.description, set=True
                )
            )
            # Only propagate type and description once.
            self.registered_remotely = True

        self.registry.update_buffer(to_propagate)

    @property
    def _type_key(self) -> str:
        """
        Type Key should be structured as {metric_name}:{type_extension_letter}:
        :return: str
        """
        return self._structure_key_name(extension=TYPE_EXTENSION_LETTER)

    @property
    def _description_key(self) -> str:
        """
        Description key should be structured as {metric_name}:{description_extension_letter}
        :return: str
        """
        return self._structure_key_name(extension=DESCRIPTION_EXTENSION_LETTER)

    def _clean_labels(self, labels=None) -> list:
        """
        Raises error on not allowed labels and sorts the labels
        :param labels:
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

        return sorted(_labels)

    def _encode_labels(self, labels=None) -> str:
        """
        Encodes all lables in the format it should be save in redis in the key name.
        Format is {label_name}="{label_value}" which is also the Prometheus format.
        To handle the case with no lables the NO_LABELS_KEY is used.
        :param labels:
        :return: str
        """
        if not labels:
            return NO_LABELS_KEY

        label_string = ""
        for label_name, label_value in sorted(labels.items()):
            if label_name in self.RESERVED_LABELS:
                continue

            if label_name not in self.allowed_labels:
                raise ValueError(
                    f"Label name {label_name} is not an allowed label in metric {self.name}"
                )

            label_string += f'{label_name}="{label_value}",'

        return label_string[:-1]  # removes last comma

    def _structure_key_name(self, name="", extension="", labels="") -> str:
        """
        Will structure the full key to be used in local and remote store.
        :param name:
        :param extension:
        :param labels:
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
            [UpdateAction(key=self._structure_key_name(labels=key), value=new_value)]
        )

    def reset(self):
        """
        Clears all the counters and sets counter dict to initial state.
        :return:
        """
        self.counts = {NO_LABELS_KEY: 0}


class Gauge(Metric):
    """
    A Gauge is a value that can increase and decrease.
    """

    TYPE_KEY = "g"

    def __init__(self, name, description, allowed_labels=None, initial_value=0):
        super().__init__(name, description, allowed_labels)

        self.counts = {NO_LABELS_KEY: initial_value}
        self.set_command_issued = set()

    def _set_command_issued_for_label_combination(self, label_combination):

        return label_combination in self.set_command_issued

    def inc(self, value=1, labels: Dict[str, str] = None) -> None:
        """
        Increases the value.
        If a set command has been issued, we can keep in using the redis set command.
        If not we don't know the current remote state of the gauge, but we can still use
        redis incrby and have correct value. After a set has been made for a label
        combination we can keep on using redis set and get a bit more performance.

        :param value:
        :param labels:
        :return:
        """

        if value < 0:
            raise ValueError(
                f"inc() only accepts positive values. If you want to decreace use dec()."
            )

        key = self._encode_labels(labels)
        current_value = self.counts.get(key, 0)
        new_value = current_value + value

        if self._set_command_issued_for_label_combination(key):
            self.set(new_value, labels)

        else:
            # uses incrby and we dont need to know the current value.
            self.counts[key] = new_value
            self.propagate(
                [
                    UpdateAction(
                        key=self._structure_key_name(labels=key), value=new_value
                    )
                ]
            )

    def dec(self, value=1, labels: Dict[str, str] = None) -> None:
        """
        Increases the value.
        If a set command has been issued, we can keep in using the redis set command.
        If not we don't know the current remote state of the gauge, but we can still use
        redis incrby and have correct value. After a set has been made for a label
        combination we can keep on using redis set and get a bit more performance.

        :param value:
        :param labels:
        :return:
        """
        if value < 0:
            raise ValueError(
                f"dec() only accepts positive values. If you want to increase use inc()."
            )

        key = self._encode_labels(labels)
        current_value = self.counts.get(key, 0)
        new_value = current_value - value

        if self._set_command_issued_for_label_combination(key):
            self.set(new_value, labels)

        else:
            # uses incrby and we dont need to know the current value.
            self.counts[key] = new_value
            self.propagate(
                [
                    UpdateAction(
                        key=self._structure_key_name(labels=key), value=new_value
                    )
                ]
            )

    def set(self, value, labels: Dict[str, str] = None) -> None:
        """
        Sets the value of a label combination.

        :param value:
        :param labels:
        :return:
        """

        key = self._encode_labels(labels)

        self.counts[key] = value

        self.propagate(
            [
                UpdateAction(
                    key=self._structure_key_name(labels=key), value=value, set=True
                )
            ]
        )

        self.set_command_issued.add(key)

    def reset(self):
        """
        Since a gauge can go up and down we should not set the value to zero on reset
        :return:
        """
        pass
