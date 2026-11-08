"""The Pagosa's entities keep the unique ids 1.4-pagosa gave them.

migrate_1_4.py moves a 1.4 entry under an account and rewrites each unique id
by putting the new subentry id where the 1.4 entry id was ; once Home
Assistant has started, it removes every entity nothing claimed. So a Pagosa
entity whose unique id moves by a character is deleted, with its entity id,
its history and whatever automation reads it.

The table is the 53 unique ids a Sauter Pagosa 270L carried on 1.4-pagosa
(2026-11-08), with ``{sub}`` where the entry id was. The entities are built
from ``scripts/test_ha/pagosa.json``, the same heater's Overkiz setup.
"""

import asyncio
import copy
import json
import pathlib

from custom_components.cozytouch import pagosa
from custom_components.cozytouch.pagosa.hub import PagosaHub, is_overkiz_device_id

CAPTURE = pathlib.Path(__file__).parent.parent / "scripts" / "test_ha" / "pagosa.json"
SUBENTRY = "01SUBENTRY0000000000000000"

UNIQUE_IDS_14 = {
    "binary_sensor": [
        "cozytouch_{sub}_cloud_connectivity",
    ],
    "button": [
        "cozytouch_{sub}_pagosa_identify",
        "cozytouch_{sub}_pagosa_refresh_away",
        "cozytouch_{sub}_pagosa_refresh_boost",
        "cozytouch_{sub}_pagosa_refresh_consumption",
        "cozytouch_{sub}_pagosa_refresh_error",
        "cozytouch_{sub}_pagosa_refresh_mode",
        "cozytouch_{sub}_pagosa_refresh_programming",
        "cozytouch_{sub}_pagosa_refresh_temperature",
    ],
    "calendar": [
        "cozytouch_{sub}_pagosa_absence_calendar",
    ],
    "datetime": [
        "{sub}_pagosa_absence_end",
        "{sub}_pagosa_datetime",
    ],
    "number": [
        "cozytouch_{sub}_pagosa_away_duration",
        "cozytouch_{sub}_pagosa_boost_duration",
        "cozytouch_{sub}_pagosa_target_temperature",
    ],
    "select": [
        "{sub}_dhw_mode",
        "{sub}_operating_range",
    ],
    "sensor": [
        "cozytouch_{sub}_overkiz_core_BoostModeDurationState",
        "cozytouch_{sub}_overkiz_core_CommandLockLevelsState",
        "cozytouch_{sub}_overkiz_core_DiscreteRSSILevelState",
        "cozytouch_{sub}_overkiz_core_ManufacturerNameState",
        "cozytouch_{sub}_overkiz_core_NameState",
        "cozytouch_{sub}_overkiz_core_OperatingModeState",
        "cozytouch_{sub}_overkiz_core_PriorityLockTimerState",
        "cozytouch_{sub}_overkiz_core_RSSILevelState",
        "cozytouch_{sub}_overkiz_core_StatusState",
        "cozytouch_{sub}_overkiz_core_TargetTemperatureState",
        "cozytouch_{sub}_overkiz_core_TemperatureState",
        "cozytouch_{sub}_overkiz_core_VersionState",
        "cozytouch_{sub}_overkiz_energy_core_ElectricEnergyConsumptionState",
        "cozytouch_{sub}_overkiz_io_AntiLegionellosisState",
        "cozytouch_{sub}_overkiz_io_AwayModeDurationState",
        "cozytouch_{sub}_overkiz_io_BoilerInstallationOptionState",
        "cozytouch_{sub}_overkiz_io_DHWCapacityState",
        "cozytouch_{sub}_overkiz_io_DHWErrorState",
        "cozytouch_{sub}_overkiz_io_DHWModeState",
        "cozytouch_{sub}_overkiz_io_ElectricBoosterOperatingTimeState",
        "cozytouch_{sub}_overkiz_io_ElectricalExtraManagementState",
        "cozytouch_{sub}_overkiz_io_ExtractionOptionState",
        "cozytouch_{sub}_overkiz_io_HeatPumpOperatingTimeState",
        "cozytouch_{sub}_overkiz_io_InstallationState",
        "cozytouch_{sub}_overkiz_io_OperatingModeCapabilitiesState",
        "cozytouch_{sub}_overkiz_io_OperatingRangeState",
        "cozytouch_{sub}_overkiz_io_ProgrammingSlotsState",
        "cozytouch_{sub}_overkiz_io_RateManagementState",
        "cozytouch_{sub}_overkiz_io_SmartGridOptionState",
    ],
    "switch": [
        "{sub}_pagosa_absence",
        "{sub}_pagosa_boost",
        "{sub}_pagosa_eco",
    ],
    "time": [
        "{sub}_pagosa_slot1_end",
        "{sub}_pagosa_slot1_start",
        "{sub}_pagosa_slot2_end",
        "{sub}_pagosa_slot2_start",
    ],
}


def hub() -> PagosaHub:
    """A PagosaHub holding the capture's setup, without a session."""
    capture = json.loads(CAPTURE.read_text())
    the_hub = object.__new__(PagosaHub)
    the_hub._deviceId = "io://0000-1111-2222/1234567#1"
    the_hub._pagosa_optimistic_states = {}
    the_hub._setup = copy.deepcopy(capture["setupviewv2"][0])
    the_hub._is_overkiz = True
    the_hub.online = True
    the_hub.last_update_success = True
    the_hub._apply_overkiz_setup(capture["overkiz_setup"])
    return the_hub


def built(platform: str) -> list:
    entities: list = []
    context = pagosa.PagosaContext(
        SUBENTRY, "Pagosa", {"deviceId": "io://0000-1111-2222/1234567#1"}
    )
    module = pagosa._PLATFORMS[platform]
    asyncio.run(
        module.async_setup_pagosa(
            hub(), context, lambda new, *_: entities.extend(new)
        )
    )
    return entities


def test_every_platform_builds_the_unique_ids_of_1_4():
    for platform, expected in UNIQUE_IDS_14.items():
        got = sorted(entity.unique_id for entity in built(platform))
        assert got == sorted(u.format(sub=SUBENTRY) for u in expected), platform


def test_no_platform_builds_more_than_1_4_did():
    assert set(pagosa._PLATFORMS) == set(UNIQUE_IDS_14)


def test_an_overkiz_device_url_is_told_from_a_cozytouch_device_id():
    assert is_overkiz_device_id("io://0000-1111-2222/1234567#1")
    assert not is_overkiz_device_id(12345)
    assert not is_overkiz_device_id("12345")
