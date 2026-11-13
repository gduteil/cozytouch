"""Pagosa sensors, from the heater's and the energy meter's Overkiz states.

Carried from the pagosa-1.4 branch unchanged but for the hub it talks to.
"""

from __future__ import annotations

import json
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfEnergy, UnitOfTemperature, UnitOfVolume
from homeassistant.core import callback
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from ..const import DOMAIN
from .hub import PagosaHub as Hub

_LOGGER = logging.getLogger(__name__)


class OverkizPagosaSensor(CoordinatorEntity[Hub], SensorEntity):
    """Sensor based on an Overkiz state of a Sauter Pagosa."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        coordinator: Hub,
        config_entry: ConfigEntry,
        state_key: str,
        description: dict,
    ) -> None:
        """Initialize a Pagosa sensor."""
        super().__init__(coordinator)

        self._state_key = state_key
        self._config_entry = config_entry

        self._attr_name = description["name"]
        self._attr_icon = description.get("icon")
        self._attr_unique_id = (
            f"{DOMAIN}_{config_entry.entry_id}_overkiz_"
            f"{state_key.replace(':', '_')}"
        )

        self._attr_native_unit_of_measurement = description.get("unit")
        self._attr_device_class = description.get("device_class")
        self._attr_state_class = description.get("state_class")
        self._attr_entity_category = description.get("entity_category")

        device = coordinator.get_overkiz_device() or {}
        self._device_identifier = str(
            device.get("deviceURL", config_entry.entry_id)
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return Pagosa device information."""
        device = self.coordinator.get_overkiz_device() or {}

        return DeviceInfo(
            identifiers={(DOMAIN, self._device_identifier)},
            manufacturer="Sauter",
            name=device.get("label") or self._config_entry.title,
            model="Pagosa 270L",
        )

    @property
    def available(self) -> bool:
        """Return sensor availability."""
        return (
            self.coordinator.last_update_success
            and self._state_key in self.coordinator.get_overkiz_states()
        )

    @property
    def native_value(self):
        """Return the current state value."""
        value = self.coordinator.get_overkiz_state(self._state_key)

        if value is None:
            return None

        if isinstance(value, (dict, list)):
            return json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
            )

        if isinstance(value, (int, float, bool)):
            return value

        return str(value)

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update the sensor when the coordinator refreshes."""
        self.async_write_ha_state()


class OverkizPagosaEnergySensor(CoordinatorEntity[Hub], SensorEntity):
    """Energy sensor from the separate Pagosa Overkiz energy device."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_device_class = SensorDeviceClass.ENERGY
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfEnergy.KILO_WATT_HOUR
    _attr_suggested_display_precision = 2

    def __init__(
        self,
        coordinator: Hub,
        config_entry: ConfigEntry,
        state_key: str,
        description: dict,
    ) -> None:
        """Initialize energy sensor."""
        super().__init__(coordinator)

        self._state_key = state_key
        self._config_entry = config_entry
        self._attr_name = description["name"]
        self._attr_icon = description.get("icon")

        self._attr_unique_id = (
            f"{DOMAIN}_{config_entry.entry_id}_overkiz_energy_"
            f"{state_key.replace(':', '_')}"
        )

        # Keep the energy entities grouped with the main Pagosa device.
        device = coordinator.get_overkiz_device() or {}
        self._device_identifier = str(
            device.get("deviceURL", config_entry.entry_id)
        )

    @property
    def device_info(self) -> DeviceInfo:
        """Return the same physical appliance as the Pagosa sensors."""
        device = self.coordinator.get_overkiz_device() or {}

        return DeviceInfo(
            identifiers={(DOMAIN, self._device_identifier)},
            manufacturer="Sauter",
            name=device.get("label") or self._config_entry.title,
            model="Pagosa 270L",
        )

    @property
    def available(self) -> bool:
        """Return energy sensor availability."""
        return (
            self.coordinator.last_update_success
            and self._state_key
            in self.coordinator.get_overkiz_energy_states()
        )

    @property
    def native_value(self) -> float | None:
        """Convert the Overkiz Wh value to kWh."""
        value = self.coordinator.get_overkiz_energy_state(
            self._state_key
        )

        if value is None:
            return None

        try:
            return float(value) / 1000
        except (TypeError, ValueError):
            _LOGGER.warning(
                "Invalid energy value for %s: %s",
                self._state_key,
                value,
            )
            return None

    @callback
    def _handle_coordinator_update(self) -> None:
        """Update energy sensor."""
        self.async_write_ha_state()




async def async_setup_pagosa(
    hub: Hub,
    config_entry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Add this platform's Pagosa entities ; config_entry is a PagosaContext."""
    sensors = []
    states = hub.get_overkiz_states()

    if not isinstance(states, dict):
        states = {}

    pagosa_sensors = [
        {
            "state": "core:TemperatureState",
            "name": "Température de l'eau",
            "icon": "mdi:thermometer",
            "device_class": SensorDeviceClass.TEMPERATURE,
            "unit": UnitOfTemperature.CELSIUS,
            "state_class": SensorStateClass.MEASUREMENT,
        },
        {
            "state": "core:TargetTemperatureState",
            "name": "Température cible",
            "icon": "mdi:thermometer-check",
            "device_class": SensorDeviceClass.TEMPERATURE,
            "unit": UnitOfTemperature.CELSIUS,
            "state_class": SensorStateClass.MEASUREMENT,
        },
        {
            "state": "core:ComfortTargetTemperatureState",
            "name": "Température de confort",
            "icon": "mdi:thermometer-plus",
            "device_class": SensorDeviceClass.TEMPERATURE,
            "unit": UnitOfTemperature.CELSIUS,
            "state_class": SensorStateClass.MEASUREMENT,
        },
        {
            "state": "core:EcoTargetTemperatureState",
            "name": "Température éco",
            "icon": "mdi:thermometer-minus",
            "device_class": SensorDeviceClass.TEMPERATURE,
            "unit": UnitOfTemperature.CELSIUS,
            "state_class": SensorStateClass.MEASUREMENT,
        },
        {
            "state": "core:FrostProtectionTargetTemperatureState",
            "name": "Température hors gel",
            "icon": "mdi:snowflake-thermometer",
            "device_class": SensorDeviceClass.TEMPERATURE,
            "unit": UnitOfTemperature.CELSIUS,
            "state_class": SensorStateClass.MEASUREMENT,
        },
        {
            "state": "core:HaltedTargetTemperatureState",
            "name": "Température en arrêt",
            "icon": "mdi:thermometer-off",
            "device_class": SensorDeviceClass.TEMPERATURE,
            "unit": UnitOfTemperature.CELSIUS,
            "state_class": SensorStateClass.MEASUREMENT,
        },
        {
            "state": "io:DHWCapacityState",
            "name": "Capacité du ballon",
            "icon": "mdi:water",
            "device_class": SensorDeviceClass.VOLUME,
            "unit": UnitOfVolume.LITERS,
        },
        {
            "state": "core:WaterConsumptionState",
            "name": "Consommation d'eau",
            "icon": "mdi:water-outline",
        },
        {
            "state": "io:HeatPumpOperatingTimeState",
            "name": "Temps de fonctionnement pompe à chaleur",
            "icon": "mdi:clock-outline",
        },
        {
            "state": "io:ElectricBoosterOperatingTimeState",
            "name": "Temps de fonctionnement appoint électrique",
            "icon": "mdi:clock-time-four-outline",
        },
        {
            "state": "core:RSSILevelState",
            "name": "Puissance du signal radio",
            "icon": "mdi:wifi",
        },
        {
            "state": "core:DiscreteRSSILevelState",
            "name": "Qualité du signal radio",
            "icon": "mdi:wifi-strength-2",
        },
        {
            "state": "core:StatusState",
            "name": "État de connexion du chauffe-eau",
            "icon": "mdi:connection",
            "entity_category": EntityCategory.DIAGNOSTIC,
        },
        {
            "state": "core:ManufacturerNameState",
            "name": "Fabricant",
            "icon": "mdi:factory",
            "entity_category": EntityCategory.DIAGNOSTIC,
        },
        {
            "state": "core:NameState",
            "name": "Nom de l'appareil",
            "icon": "mdi:tag",
            "entity_category": EntityCategory.DIAGNOSTIC,
        },
        {
            "state": "core:VersionState",
            "name": "Version matérielle",
            "icon": "mdi:chip",
            "entity_category": EntityCategory.DIAGNOSTIC,
        },
        {
            "state": "core:OperatingModeState",
            "name": "État des modes de fonctionnement",
            "icon": "mdi:state-machine",
        },
        {
            "state": "core:CommandLockLevelsState",
            "name": "Verrouillages des commandes",
            "icon": "mdi:lock",
            "entity_category": EntityCategory.DIAGNOSTIC,
        },
        {
            "state": "core:PriorityLockTimerState",
            "name": "Durée du verrouillage prioritaire",
            "icon": "mdi:timer-lock",
            "entity_category": EntityCategory.DIAGNOSTIC,
        },
        {
            "state": "core:SecuredPositionTemperatureState",
            "name": "Température de sécurité",
            "icon": "mdi:shield-thermometer",
            "device_class": SensorDeviceClass.TEMPERATURE,
            "unit": UnitOfTemperature.CELSIUS,
        },
        {
            "state": "io:DHWModeState",
            "name": "Mode de fonctionnement ECS",
            "icon": "mdi:water-boiler",
        },
        {
            "state": "io:OperatingRangeState",
            "name": "Plage de fonctionnement",
            "icon": "mdi:tune",
        },
        {
            "state": "io:AntiLegionellosisState",
            "name": "Protection anti-légionellose",
            "icon": "mdi:shield-check",
        },
        {
            "state": "io:ElectricalExtraManagementState",
            "name": "Gestion appoint électrique",
            "icon": "mdi:flash",
        },
        {
            "state": "io:InstallationState",
            "name": "Type d'installation",
            "icon": "mdi:home-lightning-bolt",
            "entity_category": EntityCategory.DIAGNOSTIC,
        },
        {
            "state": "io:BoilerInstallationOptionState",
            "name": "Option d'installation",
            "icon": "mdi:cog",
            "entity_category": EntityCategory.DIAGNOSTIC,
        },
        {
            "state": "io:SmartGridOptionState",
            "name": "Option Smart Grid",
            "icon": "mdi:transmission-tower",
        },
        {
            "state": "io:ExtractionOptionState",
            "name": "Option d'extraction",
            "icon": "mdi:fan",
        },
        {
            "state": "io:RateManagementState",
            "name": "Gestion tarifaire",
            "icon": "mdi:currency-eur",
        },
        {
            "state": "io:AwayModeDurationState",
            "name": "Durée du mode absence",
            "icon": "mdi:calendar-clock",
        },
        {
            "state": "core:BoostModeDurationState",
            "name": "Durée du mode Boost",
            "icon": "mdi:rocket-launch",
        },
        {
            "state": "io:OperatingModeCapabilitiesState",
            "name": "Fonctions disponibles",
            "icon": "mdi:list-box",
            "entity_category": EntityCategory.DIAGNOSTIC,
        },
        {
            "state": "io:DHWErrorState",
            "name": "Erreur chauffe-eau",
            "icon": "mdi:alert-circle-outline",
            "entity_category": EntityCategory.DIAGNOSTIC,
        },
        {
            "state": "io:ProgrammingSlotsState",
            "name": "Programmation horaire",
            "icon": "mdi:calendar-clock",
        },
        {
            "state": "io:ElectricalExtraManagementState",
            "name": "Gestion appoint électrique",
            "icon": "mdi:lightning-bolt",
        },
        {
            "state": "io:SmartGridOptionState",
            "name": "Configuration Smart Grid",
            "icon": "mdi:transmission-tower",
        },
        {
            "state": "io:BoilerInstallationOptionState",
            "name": "Configuration chaudière",
            "icon": "mdi:water-boiler-auto",
        },
        {
            "state": "io:ExtractionOptionState",
            "name": "Configuration extraction",
            "icon": "mdi:fan",
        },
    ]

    seen_states = set()

    for description in pagosa_sensors:
        state_key = description["state"]

        if state_key in seen_states or state_key not in states:
            continue

        seen_states.add(state_key)

        sensors.append(
            OverkizPagosaSensor(
                coordinator=hub,
                config_entry=config_entry,
                state_key=state_key,
                description=description,
            )
        )

    # Energy meter is a separate Overkiz device (#2).
    energy_states = hub.get_overkiz_energy_states()

    if not isinstance(energy_states, dict):
        energy_states = {}

    energy_sensors = [
        {
            "state": "core:ElectricEnergyConsumptionState",
            "name": "Consommation électrique totale",
            "icon": "mdi:lightning-bolt",
        },
        {
            "state": "core:ElectricEnergyConsumptionInTariff1State",
            "name": "Consommation électrique tarif 1",
            "icon": "mdi:lightning-bolt-outline",
        },
        {
            "state": "core:ElectricEnergyConsumptionInTariff2State",
            "name": "Consommation électrique tarif 2",
            "icon": "mdi:lightning-bolt-outline",
        },
    ]

    for description in energy_sensors:
        state_key = description["state"]

        if state_key not in energy_states:
            continue

        sensors.append(
            OverkizPagosaEnergySensor(
                coordinator=hub,
                config_entry=config_entry,
                state_key=state_key,
                description=description,
            )
        )

    if sensors:
        _LOGGER.info(
            "%s: adding %d Pagosa Overkiz sensors",
            config_entry.title,
            len(sensors),
        )

        _LOGGER.info(
            "%s: found %d Pagosa energy states",
            config_entry.title,
            sum(
                1
                for item in energy_sensors
                if item["state"] in energy_states
            ),
        )

        async_add_entities(sensors, True)
    else:
        _LOGGER.warning(
            "%s: no Pagosa states available to create sensors",
            config_entry.title,
        )

    return
