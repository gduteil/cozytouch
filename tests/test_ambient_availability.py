"""Whether the ambient reading the climate entity shows means anything.

Capability 103150 is the device saying, at each poll, that its ambient sensor
is or is not reporting. Without it the entity keeps the last good number for
good, which reads exactly like a live one. The Cozytouch app asks the same
question before it shows a temperature ; see docs/decisions.md.
"""

import pytest

from custom_components.cozytouch.capability import get_capability_infos
from custom_components.cozytouch.climate import CozytouchClimate
from custom_components.cozytouch.model import get_model_infos

# A room air conditioner behind a hub, which is what reports 103150.
ROOM = 557


class FakeCoordinator:
    """Only what the availability check asks of a hub."""

    def __init__(self, values):
        self.values = values

    def get_capability_value(self, capabilityId):
        return self.values.get(capabilityId)


def availability(capability, values):
    entity = object.__new__(CozytouchClimate)
    entity._capability = capability
    entity.coordinator = FakeCoordinator(values)
    return entity._ambient_temperature_is_available()


def climate_infos(availableCapabilityIds):
    return get_capability_infos(
        get_model_infos(ROOM), 7, "0", availableCapabilityIds
    )


def test_the_id_is_wired_when_the_device_reports_it():
    infos = climate_infos({7, 117, 103150})

    assert infos["currentAvailableCapabilityId"] == 103150


def test_no_id_is_wired_when_the_device_stays_silent():
    infos = climate_infos({7, 117})

    assert "currentAvailableCapabilityId" not in infos


def test_a_device_that_does_not_say_is_believed():
    """Every device that predates the capability, which is most of them."""
    assert availability({}, {}) is True


@pytest.mark.parametrize("value", ["1", 1, "2"])
def test_anything_but_zero_reads_as_available(value):
    assert availability({"currentAvailableCapabilityId": 103150}, {103150: value})


def test_zero_reads_as_unavailable():
    capability = {"currentAvailableCapabilityId": 103150}

    assert availability(capability, {103150: "0"}) is False


def test_a_missing_value_is_not_an_unavailable_one():
    """A poll that did not carry the id says nothing, and nothing is not no."""
    capability = {"currentAvailableCapabilityId": 103150}

    assert availability(capability, {}) is True
