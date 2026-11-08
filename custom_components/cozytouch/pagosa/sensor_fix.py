"""Pagosa tank capacity sensor: give it back a state class.

Home Assistant kept long-term statistics for this sensor, but the sensor
no longer declared a state class, which raised the repair "the entity no
longer has a state class". The tank capacity is a measured quantity that
does not change, so it is declared as a stored volume with the
``measurement`` state class (a plain measurement on older versions).
"""

from __future__ import annotations

import logging

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass

_LOGGER = logging.getLogger(__name__)

CAPACITY_STATE = "io:DHWCapacityState"


def _patch_sensor() -> None:
    from .sensor import OverkizPagosaSensor

    original_init = OverkizPagosaSensor.__init__

    def __init__(self, coordinator, config_entry, state_key, description) -> None:
        original_init(self, coordinator, config_entry, state_key, description)
        if state_key == CAPACITY_STATE:
            self._attr_device_class = getattr(
                SensorDeviceClass, "VOLUME_STORAGE", None
            )
            self._attr_state_class = SensorStateClass.MEASUREMENT

    OverkizPagosaSensor.__init__ = __init__


try:
    _patch_sensor()
except Exception:  # pragma: no cover - never break the integration
    _LOGGER.exception("Unable to patch the Pagosa capacity sensor")
