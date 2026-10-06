"""Contract tests for the model table.

get_model_infos is the single place that says what a device can do: capability.py
reads the flags it returns to decide which entities to create, so a group that
silently gains or loses one changes the entity list of every user who owns that
hardware. One case per branch of the table, plus the ids inside a branch that
resolve differently -- 1734-1737 share the air conditioner branch with 557-561
but come out with their own set of flags, and only a case each pins that down.

These are characterisation tests. The expectations were read off the mapping as
it stands, so they say nothing about whether a model is mapped *correctly* --
several are guesses from a single user's capture. What they catch is a change
nobody meant to make.
"""

import pytest

from custom_components.cozytouch.const import (
    AIR_CIRCULATION_SPEED_HIGH,
    AIR_CIRCULATION_SPEED_LOW,
    AIR_CIRCULATION_SPEED_MEDIUM,
    HEATING_MODE_ECO_PLUS,
    HEATING_MODE_MANUAL,
    HEATING_MODE_PROG,
    SWING_MODE_DOWN,
    SWING_MODE_MIDDLE_DOWN,
    SWING_MODE_MIDDLE_UP,
    SWING_MODE_UP,
)
from custom_components.cozytouch.model import (
    MODEL_NAMES,
    CozytouchDeviceType,
    get_device_model_infos,
    get_model_infos,
)
from custom_components.cozytouch.model_catalogue import MODEL_CATALOGUE
from homeassistant.components.climate import HVACMode
from homeassistant.components.climate.const import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
)

MODEL_GROUPS = [
    (
        56,
        {
            "modelId": 56,
            "HVACModesCapabilityId": {7, 8},
            "name": "Naema 2 Micro 25",
            "type": CozytouchDeviceType.GAZ_BOILER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
        },
    ),
    (
        61,
        {
            "modelId": 61,
            "HVACModesCapabilityId": {7, 8},
            "name": "Naia 2 Micro 25",
            "type": CozytouchDeviceType.GAZ_BOILER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
        },
    ),
    (
        65,
        {
            "modelId": 65,
            "HVACModesCapabilityId": {7, 8},
            "name": "Naema 2 Duo 25",
            "type": CozytouchDeviceType.GAZ_BOILER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
        },
    ),
    (
        76,
        {
            "modelId": 76,
            "HVACModesCapabilityId": {7, 8},
            "name": "Alfea Extensa Duo AI UE: 6kW, 8kW, 10kW App: 3kW",
            "type": CozytouchDeviceType.HEAT_PUMP,
            "currentTemperatureAvailableZ1": False,
            "currentTemperatureAvailableZ2": True,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {0: HEATING_MODE_MANUAL},
            "exhaustTemperatureAvailable": False,
        },
    ),
    (
        211,
        {
            "modelId": 211,
            "HVACModesCapabilityId": {1, 2},
            "name": "Alfea Extensa Duo A.I. 3 R32",
            "type": CozytouchDeviceType.HEAT_PUMP,
            "currentTemperatureAvailableZ1": True,
            "currentTemperatureAvailableZ2": True,
            "HVACModes": {0: HVACMode.OFF, 1: HVACMode.HEAT, 2: HVACMode.AUTO},
            "HeatingModes": {0: HEATING_MODE_MANUAL},
            "exhaustTemperatureAvailable": False,
        },
    ),
    (
        2303,
        {
            "modelId": 2303,
            "HVACModesCapabilityId": set(),
            "name": "Alfea Extensa S Duo",
            "type": CozytouchDeviceType.HEAT_PUMP,
            "HVACModes": {},
        },
    ),
    (
        2327,
        {
            "modelId": 2327,
            "HVACModesCapabilityId": set(),
            "name": "Alfea Extensa S Duo",
            "type": CozytouchDeviceType.HEAT_PUMP,
            "HVACModes": {},
        },
    ),
    (
        1691,
        {
            "modelId": 1691,
            "HVACModesCapabilityId": set(),
            "name": "ALFEA EXCELLIA S",
            "type": CozytouchDeviceType.HEAT_PUMP,
            "HVACModes": {},
        },
    ),
    (
        1391,
        {
            "modelId": 1391,
            "HVACModesCapabilityId": set(),
            "name": "Generator",
            "type": CozytouchDeviceType.HEAT_PUMP,
            "HVACModes": {},
        },
    ),
    (
        235,
        {
            "modelId": 235,
            "HVACModesCapabilityId": {7, 8},
            "name": "Thermostat Navilink Connect",
            "type": CozytouchDeviceType.THERMOSTAT,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
        },
    ),
    (
        236,
        {
            "modelId": 236,
            "HVACModesCapabilityId": {7, 8},
            "name": "Sauter Phazy",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        386,
        {
            "modelId": 386,
            "HVACModesCapabilityId": {7, 8},
            "name": "PHAZY VS 300L 3000M",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        387,
        {
            "modelId": 387,
            "HVACModesCapabilityId": {7, 8},
            "name": "PHAZY VM 150L 2200M",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        388,
        {
            "modelId": 388,
            "HVACModesCapabilityId": {7, 8},
            "name": "PHAZY VM 200L 2200M",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        389,
        {
            "modelId": 389,
            "HVACModesCapabilityId": {7, 8},
            "name": "AQUEO ACI HYB VS 300L 3000M",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        390,
        {
            "modelId": 390,
            "HVACModesCapabilityId": {7, 8},
            "name": "AQUEO ACI HYB VM 150L 2200M",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        391,
        {
            "modelId": 391,
            "HVACModesCapabilityId": {7, 8},
            "name": "AQUEO ACI HYB VM 200L 2200M",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        392,
        {
            "modelId": 392,
            "HVACModesCapabilityId": {7, 8},
            "name": "DURALIS CONNECT ACI HYB VS 300L 3000M",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        393,
        {
            "modelId": 393,
            "HVACModesCapabilityId": {7, 8},
            "name": "DURALIS CONNECT ACI HYB VM 150L 2200M",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        394,
        {
            "modelId": 394,
            "HVACModesCapabilityId": {7, 8},
            "name": "DURALIS CONNECT ACI HYB VM 200L 2200M",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        418,
        {
            "modelId": 418,
            "HVACModesCapabilityId": {7, 8},
            "name": "LORIA 3 DUO R32",
            "type": CozytouchDeviceType.THERMOSTAT,
            "exhaustTemperatureAvailable": True,
            "currentTemperatureAvailableZ1": True,
            "currentTemperatureAvailableZ2": False,
            "overrideModeAvailable": True,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
        },
    ),
    (
        556,
        {
            "modelId": 556,
            "HVACModesCapabilityId": {7, 8},
            "name": "Naviclim Hub",
            "type": CozytouchDeviceType.HUB,
            "awayModeTemperatureAvailable": False,
            "HVACModes": {0: HVACMode.OFF},
        },
    ),
    (
        1457,
        {
            "modelId": 1457,
            "HVACModesCapabilityId": {7, 8},
            "name": "HUB ATLANTIC COZYTOUCH",
            "type": CozytouchDeviceType.HUB,
            "awayModeTemperatureAvailable": False,
            "HVACModes": {0: HVACMode.OFF},
        },
    ),
    (
        1681,
        {
            "modelId": 1681,
            "HVACModesCapabilityId": {7, 8},
            "name": "HUB Navizone",
            "type": CozytouchDeviceType.HUB,
            "awayModeTemperatureAvailable": False,
            "HVACModes": {0: HVACMode.OFF},
        },
    ),
    (
        1758,
        {
            "modelId": 1758,
            "HVACModesCapabilityId": {7, 8},
            "name": "HUB Navizone",
            "type": CozytouchDeviceType.HUB,
            "awayModeTemperatureAvailable": False,
            "HVACModes": {0: HVACMode.OFF},
        },
    ),
    (
        2448,
        {
            "modelId": 2448,
            "HVACModesCapabilityId": {7, 8},
            "name": "Hub IO Thermor",
            "type": CozytouchDeviceType.HUB,
            "awayModeTemperatureAvailable": False,
            "HVACModes": {0: HVACMode.OFF},
        },
    ),
    (
        2449,
        {
            "modelId": 2449,
            "HVACModesCapabilityId": {7, 8},
            "name": "Hub IO Atlantic",
            "type": CozytouchDeviceType.HUB,
            "awayModeTemperatureAvailable": False,
            "HVACModes": {0: HVACMode.OFF},
        },
    ),
    (
        2450,
        {
            "modelId": 2450,
            "HVACModesCapabilityId": {7, 8},
            "name": "Hub IO Inter",
            "type": CozytouchDeviceType.HUB,
            "awayModeTemperatureAvailable": False,
            "HVACModes": {0: HVACMode.OFF},
        },
    ),
    (
        2447,
        {
            "modelId": 2447,
            "HVACModesCapabilityId": {7, 8},
            "name": "Hub IO Sauter",
            "type": CozytouchDeviceType.HUB,
            "awayModeTemperatureAvailable": False,
            "HVACModes": {0: HVACMode.OFF},
        },
    ),
    (
        557,
        {
            "modelId": 557,
            "HVACModesCapabilityId": {7, 8},
            "name": "Room (#1)",
            "type": CozytouchDeviceType.ROOM,
            "quietModeAvailable": True,
            "awayModeTemperatureAvailable": False,
            "ecoModeAvailable": False,
            "AirCirculationSpeeds": {
                1: AIR_CIRCULATION_SPEED_LOW,
                2: AIR_CIRCULATION_SPEED_MEDIUM,
                3: AIR_CIRCULATION_SPEED_HIGH,
            },
            "fanModes": {1: FAN_LOW, 2: FAN_MEDIUM, 3: FAN_HIGH, 5: FAN_AUTO},
            "swingModes": {
                1: SWING_MODE_UP,
                2: SWING_MODE_MIDDLE_UP,
                3: SWING_MODE_MIDDLE_DOWN,
                4: SWING_MODE_DOWN,
            },
            "HVACModes": {
                0: HVACMode.OFF,
                1: HVACMode.AUTO,
                3: HVACMode.COOL,
                4: HVACMode.HEAT,
                7: HVACMode.FAN_ONLY,
                8: HVACMode.DRY,
            },
        },
    ),
    (
        561,
        {
            "modelId": 561,
            "HVACModesCapabilityId": {7, 8},
            "name": "Room (#5)",
            "type": CozytouchDeviceType.ROOM,
            "quietModeAvailable": True,
            "awayModeTemperatureAvailable": False,
            "ecoModeAvailable": False,
            "AirCirculationSpeeds": {
                1: AIR_CIRCULATION_SPEED_LOW,
                2: AIR_CIRCULATION_SPEED_MEDIUM,
                3: AIR_CIRCULATION_SPEED_HIGH,
            },
            "fanModes": {1: FAN_LOW, 2: FAN_MEDIUM, 3: FAN_HIGH, 5: FAN_AUTO},
            "swingModes": {
                1: SWING_MODE_UP,
                2: SWING_MODE_MIDDLE_UP,
                3: SWING_MODE_MIDDLE_DOWN,
                4: SWING_MODE_DOWN,
            },
            "HVACModes": {
                0: HVACMode.OFF,
                1: HVACMode.AUTO,
                3: HVACMode.COOL,
                4: HVACMode.HEAT,
                7: HVACMode.FAN_ONLY,
                8: HVACMode.DRY,
            },
        },
    ),
    (
        1734,
        {
            "modelId": 1734,
            "HVACModesCapabilityId": {7, 8},
            "name": "Room (#1)",
            "type": CozytouchDeviceType.ROOM,
            "quietModeAvailable": True,
            "awayModeTemperatureAvailable": False,
            "ecoModeAvailable": False,
            "AirCirculationSpeeds": {
                1: AIR_CIRCULATION_SPEED_LOW,
                2: AIR_CIRCULATION_SPEED_MEDIUM,
                3: AIR_CIRCULATION_SPEED_HIGH,
            },
            "fanModes": {1: FAN_LOW, 2: FAN_MEDIUM, 3: FAN_HIGH, 5: FAN_AUTO},
            "swingModes": {
                1: SWING_MODE_UP,
                2: SWING_MODE_MIDDLE_UP,
                3: SWING_MODE_MIDDLE_DOWN,
                4: SWING_MODE_DOWN,
            },
            "HVACModes": {
                0: HVACMode.OFF,
                1: HVACMode.AUTO,
                3: HVACMode.COOL,
                4: HVACMode.HEAT,
                7: HVACMode.FAN_ONLY,
                8: HVACMode.DRY,
            },
        },
    ),
    (
        1737,
        {
            "modelId": 1737,
            "HVACModesCapabilityId": {7, 8},
            "name": "Room (#4)",
            "type": CozytouchDeviceType.ROOM,
            "quietModeAvailable": True,
            "awayModeTemperatureAvailable": False,
            "ecoModeAvailable": False,
            "AirCirculationSpeeds": {
                1: AIR_CIRCULATION_SPEED_LOW,
                2: AIR_CIRCULATION_SPEED_MEDIUM,
                3: AIR_CIRCULATION_SPEED_HIGH,
            },
            "fanModes": {1: FAN_LOW, 2: FAN_MEDIUM, 3: FAN_HIGH, 5: FAN_AUTO},
            "swingModes": {
                1: SWING_MODE_UP,
                2: SWING_MODE_MIDDLE_UP,
                3: SWING_MODE_MIDDLE_DOWN,
                4: SWING_MODE_DOWN,
            },
            "HVACModes": {
                0: HVACMode.OFF,
                1: HVACMode.AUTO,
                3: HVACMode.COOL,
                4: HVACMode.HEAT,
                7: HVACMode.FAN_ONLY,
                8: HVACMode.DRY,
            },
        },
    ),
    (
        562,
        {
            "modelId": 562,
            "HVACModesCapabilityId": {7, 8},
            "name": "Air Conditioner User Interface (#1)",
            "type": CozytouchDeviceType.AC_CONTROLLER,
            "HVACModes": {0: HVACMode.OFF},
            "winkable": True,
        },
    ),
    (
        570,
        {
            "modelId": 570,
            "HVACModesCapabilityId": {7, 8},
            "name": "Air Conditioner User Interface (#9)",
            "type": CozytouchDeviceType.AC_CONTROLLER,
            "HVACModes": {0: HVACMode.OFF},
            "winkable": True,
        },
    ),
    (
        1353,
        {
            "modelId": 1353,
            "HVACModesCapabilityId": {7, 8},
            "name": "Calypso Split Interface",
            "type": CozytouchDeviceType.HUB,
            "HVACModes": {0: HVACMode.OFF},
        },
    ),
    (
        754,
        {
            "modelId": 754,
            "HVACModesCapabilityId": {7, 8},
            "name": "CALYPSO SPLIT VM 200L",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        1368,
        {
            "modelId": 1368,
            "HVACModesCapabilityId": {7, 8},
            "name": "Calypso SPLIT VM 200L",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        664,
        {
            "modelId": 664,
            "HVACModesCapabilityId": {7, 8},
            "name": "CALYPSO SPLIT VS 270L",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        1369,
        {
            "modelId": 1369,
            "HVACModesCapabilityId": {7, 8},
            "name": "Calypso SPLIT VS 270L",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        1376,
        {
            "modelId": 1376,
            "HVACModesCapabilityId": {7, 8},
            "name": "Domestic hot water",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        1371,
        {
            "modelId": 1371,
            "HVACModesCapabilityId": {7, 8},
            "name": "Aeromax SPLIT 3 VM 200L",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        1372,
        {
            "modelId": 1372,
            "HVACModesCapabilityId": {7, 8},
            "name": "Aeromax SPLIT 3 VS 270L",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        1381,
        {
            "modelId": 1381,
            "HVACModesCapabilityId": {7, 8},
            "name": "KELUD 1750W BLC",
            "type": CozytouchDeviceType.TOWEL_RACK,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "winkable": True,
        },
    ),
    (
        1382,
        {
            "modelId": 1382,
            "HVACModesCapabilityId": {7, 8},
            "name": "KELUD 1750W ANTH",
            "type": CozytouchDeviceType.TOWEL_RACK,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "winkable": True,
        },
    ),
    (
        1388,
        {
            "modelId": 1388,
            "HVACModesCapabilityId": {7, 8},
            "name": "Heating circuit (#1)",
            "type": CozytouchDeviceType.ZONE,
            "HVACModes": {},
        },
    ),
    (
        1390,
        {
            "modelId": 1390,
            "HVACModesCapabilityId": {7, 8},
            "name": "Heating circuit (#3)",
            "type": CozytouchDeviceType.ZONE,
            "HVACModes": {},
        },
    ),
    (
        1588,
        {
            "modelId": 1588,
            "HVACModesCapabilityId": {7, 8},
            "name": "DORIS ETROIT 1500W BLC",
            "type": CozytouchDeviceType.TOWEL_RACK,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "winkable": True,
        },
    ),
    (
        1595,
        {
            "modelId": 1595,
            "HVACModesCapabilityId": {7, 8},
            "name": "DORIS ETROIT 1300W CARAT",
            "type": CozytouchDeviceType.TOWEL_RACK,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "winkable": True,
        },
    ),
    (
        1444,
        {
            "modelId": 1444,
            "HVACModesCapabilityId": {7, 8},
            "name": "NAEMA 3 MICRO 25",
            "type": CozytouchDeviceType.GAZ_BOILER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
        },
    ),
    (
        1447,
        {
            "modelId": 1447,
            "HVACModesCapabilityId": {7, 8},
            "name": "NAEMA 3 DUO 25",
            "type": CozytouchDeviceType.GAZ_BOILER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
        },
    ),
    (
        1543,
        {
            "modelId": 1543,
            "HVACModesCapabilityId": {7, 8},
            "name": "ASAMA CONNECTE II 1750W BLC",
            "type": CozytouchDeviceType.TOWEL_RACK,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "winkable": True,
        },
    ),
    (
        1546,
        {
            "modelId": 1546,
            "HVACModesCapabilityId": {7, 8},
            "name": "ASAMA CONNECTE II 1500W ANTH",
            "type": CozytouchDeviceType.TOWEL_RACK,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "winkable": True,
        },
    ),
    (
        1547,
        {
            "modelId": 1547,
            "HVACModesCapabilityId": {7, 8},
            "name": "ASAMA CONNECTE II 1750W ANTH",
            "type": CozytouchDeviceType.TOWEL_RACK,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "winkable": True,
        },
    ),
    (
        1551,
        {
            "modelId": 1551,
            "HVACModesCapabilityId": {7, 8},
            "name": "ASAMA CONNECTE II 1750W NOIR",
            "type": CozytouchDeviceType.TOWEL_RACK,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "winkable": True,
        },
    ),
    (
        1622,
        {
            "modelId": 1622,
            "HVACModesCapabilityId": {7, 8},
            "name": "RIVA 5 ETROIT 1300W BLC BRI",
            "type": CozytouchDeviceType.TOWEL_RACK,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "winkable": True,
        },
    ),
    (
        1641,
        {
            "modelId": 1641,
            "HVACModesCapabilityId": {7, 8},
            "name": "TD 200 VS ATE 1200M TYB V5S",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        1642,
        {
            "modelId": 1642,
            "HVACModesCapabilityId": {7, 8},
            "name": "TD 270 VS ATE 1200M TYB V5S",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        1644,
        {
            "modelId": 1644,
            "HVACModesCapabilityId": {7, 8},
            "name": "TD 240 VS ATE 1200M TYB V5S SERP",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        1645,
        {
            "modelId": 1645,
            "HVACModesCapabilityId": {7, 8},
            "name": "TD 270 VS ATE 1200M TYB V5S SERP",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        1656,
        {
            "modelId": 1656,
            "HVACModesCapabilityId": {7, 8},
            "name": "TD 240 VS TH 1200M TYB V5S",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        1669,
        {
            "modelId": 1669,
            "HVACModesCapabilityId": {7, 8},
            "name": "THE CV5 AEROMAX PREMIUM WH 100L NP",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        1657,
        {
            "modelId": 1657,
            "HVACModesCapabilityId": {7, 8},
            "name": "TD 200 VS AT 1200M TYB V5S - LRY 1007",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        1658,
        {
            "modelId": 1658,
            "HVACModesCapabilityId": {7, 8},
            "name": "TD 240 VS AT 1200M TYB V5S - LRY 1007",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        1763,
        {
            "modelId": 1763,
            "HVACModesCapabilityId": {7, 8},
            "name": "FLAT/S4 IOTHUB",
            "type": CozytouchDeviceType.HUB,
            "HVACModes": {0: HVACMode.OFF},
        },
    ),
    (
        1962,
        {
            "modelId": 1962,
            "HVACModesCapabilityId": {7, 8},
            "name": "MALICIO 3 MP 065L 2250W",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        1966,
        {
            "modelId": 1966,
            "HVACModesCapabilityId": {7, 8},
            "name": "MALICIO 3 VM 120L 2400W",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        1957,
        {
            "modelId": 1957,
            "HVACModesCapabilityId": {7, 8},
            "name": "LINEO CONNECTE MP 100L 2250W",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {0: HEATING_MODE_MANUAL, 3: HEATING_MODE_ECO_PLUS},
        },
    ),
    (
        1010,
        {
            "modelId": 1010,
            "HVACModesCapabilityId": {7, 8},
            "name": "EGEO VS 250L",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        2346,
        {
            "modelId": 2346,
            "HVACModesCapabilityId": {7, 8},
            "name": "TD 250 VS ATL 1800M TYB CA",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        2374,
        {
            "modelId": 2374,
            "HVACModesCapabilityId": {7, 8},
            "name": "AE CV5 DACH FS 270L PE COIL (DE)",
            "type": CozytouchDeviceType.WATER_HEATER,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
            "HeatingModes": {
                0: HEATING_MODE_MANUAL,
                3: HEATING_MODE_ECO_PLUS,
                4: HEATING_MODE_PROG,
            },
        },
    ),
    (
        9999,
        {
            "modelId": 9999,
            "HVACModesCapabilityId": {7, 8},
            "name": "Unknown product (9999)",
            "type": CozytouchDeviceType.UNKNOWN,
            "HVACModes": {0: HVACMode.OFF, 4: HVACMode.HEAT},
        },
    ),
]


@pytest.mark.parametrize(
    ("modelId", "expected"),
    MODEL_GROUPS,
    ids=[f"{modelId}-{expected['name']}" for modelId, expected in MODEL_GROUPS],
)
def test_model_group(modelId, expected):
    """Every branch of the table declares exactly what it declares today."""
    assert get_model_infos(modelId) == expected


@pytest.mark.parametrize("modelId", [557, 561, 562, 570])
def test_a_zone_name_replaces_the_numbered_name(modelId):
    """Units in a zone are named after the room, not their position."""
    assert get_model_infos(modelId, "Chambre parentale")["name"].endswith(
        "(Chambre parentale)"
    )


# --------------------------------------------------------------- the zones


@pytest.mark.parametrize(
    ("modelId", "deviceName"),
    [
        (1505, "THZONE_0"),
        (1510, "THZONE_5"),
        # A zone the captured range would have missed. The ids look like they
        # count the zones rather than name a product -- 1505 is THZONE_0, 1506
        # is THZONE_1 -- so an installation with more zones than the one that
        # was captured walks off the end of any range guessed from it.
        (1512, "THZONE_7"),
        (999999, "THZONE_2"),
    ],
)
def test_a_zone_is_recognised_by_the_name_the_api_gives_it(modelId, deviceName):
    assert get_model_infos(modelId, None, deviceName)["type"] is (
        CozytouchDeviceType.ZONE
    )


def test_the_name_outranks_a_mapped_product_id():
    """Checked before the id chain on purpose: an id that also belongs to a
    real product would otherwise turn a zone into a heat pump.
    """
    assert get_model_infos(76, None, "THZONE_2")["type"] is CozytouchDeviceType.ZONE
    assert get_model_infos(76)["type"] is CozytouchDeviceType.HEAT_PUMP


def test_a_named_room_replaces_the_api_name():
    """A household that named the zone gets the room; one that did not keeps
    what the app shows, which is better than a number of our own invention.
    """
    assert get_model_infos(1505, "Chambre", "THZONE_0")["name"] == "Zone (Chambre)"
    assert get_model_infos(1505, None, "THZONE_0")["name"] == "THZONE_0"


def test_a_zone_claims_no_hvac_mode():
    """It reports no climate capability, so there is nothing to claim -- and the
    unknown fall-through's {OFF, HEAT} is what made a zone read as a thermostat
    that could heat.
    """
    assert get_model_infos(1505, None, "THZONE_0")["HVACModes"] == {}
    assert get_model_infos(424242)["HVACModes"] != {}


def test_a_zone_id_is_a_zone_without_being_told():
    """1505-1509 carry productId 65-69, which the vendor calls TH_ZONE.

    The name test stays for the household of issue #93, whose zones arrive
    under their parent's model id and so have no productId of their own --
    which is why hub.py hands the device name to every lookup it makes.
    """
    assert get_model_infos(1505)["type"] is CozytouchDeviceType.ZONE
    assert get_model_infos(76)["type"] is CozytouchDeviceType.HEAT_PUMP
    assert get_model_infos(76, None, "THZONE_2")["type"] is CozytouchDeviceType.ZONE


def test_an_unmapped_model_falls_through_to_unknown():
    """A device nobody has mapped still yields a usable, clearly labelled entry."""
    infos = get_model_infos(424242)
    assert infos["type"] == CozytouchDeviceType.UNKNOWN
    assert infos["name"] == "Unknown product (424242)"


def test_an_unmapped_model_the_vendor_names_arrives_under_that_name():
    """The catalogue names a model the table has no branch for -- and names it
    only : it stays UNKNOWN, which is what the repair asking for a dump reads.
    """
    infos = get_model_infos(207)
    assert infos["name"] == "Alfea Extensa A.I. 3 R32"
    assert infos["type"] == CozytouchDeviceType.UNKNOWN


def test_the_catalogue_names_a_mapped_model_too():
    """The vendor spells its own products, and this project no longer does.

    The names written here used to differ on 91 ids, and were often less
    precise -- three Aeromax SPLIT 3 volumes shared one string where the
    catalogue names each. Six ids keep a name of their own, and only because
    the catalogue carries none. See docs/decisions.md.
    """
    assert get_model_infos(1457)["name"] == MODEL_CATALOGUE[1457]
    assert 1457 not in MODEL_NAMES
    assert get_model_infos(1376)["name"] == "Domestic hot water"
    assert 1376 not in MODEL_CATALOGUE


# --------------------------------------------------------- the room slots


@pytest.mark.parametrize(
    ("gateway", "family"),
    [
        (2447, "Connectivity_Box"),
        (1457, "Connectivity_Box"),
        (1758, "Air_Conditioning"),
    ],
)
@pytest.mark.parametrize("modelId", [557, 558, 559, 560, 561])
def test_a_room_is_a_room_whatever_drives_it(modelId, gateway, family):
    """557-561 is the room's index under a gateway and says nothing about the
    hardware : the same ids, productIds and ROOM_n names arrive behind a
    Navizone driving air conditioners (Mathieu's account), behind a CozyBox
    driving connected electric radiators (gduteil/cozytouch#172) and behind a
    HUB Cozytouch driving air conditioners again. Nothing they report tells
    the three apart -- 153, 100022 and the ventilation ids were all measured
    and none of them splits the set.

    So this stops trying. The vendor's own client builds one class for every
    room behind a gateway and lets the capabilities decide what it offers,
    and so does this. See docs/decisions.md.
    """
    box = {
        "deviceId": 2,
        "modelId": gateway,
        "productId": 0,
        "modelFamily": family,
        "name": "",
    }
    room = {
        "deviceId": 1,
        "modelId": modelId,
        "productId": modelId - 531,
        "masterDeviceId": 2,
        "name": f"ROOM_{modelId - 557}",
    }

    infos = get_device_model_infos([box, room], room, "Billard R-1")

    assert infos["type"] is CozytouchDeviceType.ROOM
    assert infos["name"] == "Room (Billard R-1)"


@pytest.mark.parametrize("masterModelId", [2295, 2303, 2317, 1691, 1692])
@pytest.mark.parametrize("modelId", [557, 558, 559, 560, 561])
def test_a_room_slot_behind_an_alfea_is_a_heating_circuit(modelId, masterModelId):
    """The third master the same room index arrives behind : a heat pump's
    connected interface, where the slot is the room control of a heating
    circuit and not an air conditioner. Issue #93.

    The modes are the app's OFF / ON / AUTO, which is what capability 166
    reads on the captured unit -- 21, bits off, auto and heat. Cooling is
    deliberately absent : the appliance supports it (100022 sets the cool
    bit) but the reporter's has no cooling kit, and nothing shows how a unit
    that has one differs.
    """
    infos = get_model_infos(
        modelId, "Circuit 1", f"ROOM_{modelId - 557}", masterModelId
    )

    assert infos["type"] is CozytouchDeviceType.THERMOSTAT
    assert infos["name"] == "Heating circuit (Circuit 1)"
    assert infos["HVACModes"] == {
        0: HVACMode.OFF,
        1: HVACMode.AUTO,
        4: HVACMode.HEAT,
    }


def test_a_heating_circuit_without_its_zone_is_numbered_like_the_others():
    assert get_model_infos(560, None, "ROOM_3", 2303)["name"] == "Heating circuit (#4)"


@pytest.mark.parametrize("masterModelId", [None, 556, 1681, 1758, 2326, 2447])
def test_a_room_slot_answers_the_same_behind_every_gateway(masterModelId):
    """Including behind no gateway at all : a room whose interface is not on
    the account is still a room, where refusing to answer would drop the
    entities of anybody who never added their box.

    The Alfea interface is the one exception, and it has its own case above :
    its slots are heating circuits and it says so with a productId of its own.
    """
    infos = get_model_infos(557, "Chambre parentale", "ROOM_0", masterModelId)

    assert infos["type"] is CozytouchDeviceType.ROOM


def test_the_hub_a_device_hangs_off_is_read_off_the_account():
    """What a caller actually has is the device list, and the master is
    resolved through it -- a child whose hub is not on the account falls back
    to the answer the id alone gives.
    """
    cozybox = {
        "deviceId": 28008536,
        "modelId": 2447,
        "name": "CozyBox",
        "modelFamily": "Connectivity_Box",
    }
    room = {
        "deviceId": 28008564,
        "modelId": 560,
        "name": "ROOM_3",
        "masterDeviceId": 28008536,
    }

    assert (
        get_device_model_infos([cozybox, room], room, "Billard R-1")["type"]
        is CozytouchDeviceType.ROOM
    )
    assert (
        get_device_model_infos([room], room, "Billard R-1")["type"]
        is CozytouchDeviceType.ROOM
    )


# ------------------------------------------------ the catalogue boilers


@pytest.mark.parametrize(
    ("modelId", "name"),
    [
        (1, "Naema Micro 30"),
        (8, "Naia 12"),
        (12, "Naia Duo 30"),
        (54, "Naema 2 12"),
        (55, "Naema 2 20"),
    ],
)
def test_a_catalogue_boiler_is_named_and_typed(modelId, name):
    """These come from the vendor's own model catalogue rather than a capture,
    so they claim the least a boiler can claim: the name Atlantic gives them,
    the type its `productId` of 1 implies, and the off/heat pair the
    fall-through already handed them. No flag, because no dump.
    """
    infos = get_model_infos(modelId)

    assert infos["name"] == name
    assert infos["type"] is CozytouchDeviceType.GAZ_BOILER
    assert infos["HVACModes"] == {0: HVACMode.OFF, 4: HVACMode.HEAT}
    assert set(infos) == {
        "modelId",
        "HVACModesCapabilityId",
        "name",
        "type",
        "HVACModes",
    }


def test_the_catalogue_boilers_do_not_shadow_a_mapped_model():
    """56, 61 and 65 were mapped from reports and keep their own branches."""
    assert get_model_infos(56)["name"] == "Naema 2 Micro 25"
    assert get_model_infos(61)["name"] == "Naia 2 Micro 25"
    assert get_model_infos(65)["name"] == "Naema 2 Duo 25"


# ------------------------------------------------ the towel rack variants


@pytest.mark.parametrize(
    ("modelId", "name"),
    [
        (1540, "ASAMA CONNECTE II 0500W BLC"),
        (1555, "ASAMA CONNECTE II 1750W CAPP"),
        (1562, "DORIS ETROIT 0300W BLC"),
        (1600, "DORIS ETROIT 1500W NOIR"),
        (1623, "RIVA 5 ETROIT 1500W BLC BRI"),
        (1635, "RIVA 5 ETROIT 1500W CARBONE"),
    ],
)
def test_a_towel_rack_variant_is_named_and_typed(modelId, name):
    """A wattage or a finish of a range already mapped. The name is the house
    spelling of the catalogue's, and the claim is the least a towel rack can
    make -- the same one its mapped siblings were already making.
    """
    infos = get_model_infos(modelId)

    assert infos["name"] == name
    assert infos["type"] is CozytouchDeviceType.TOWEL_RACK
    assert infos["HVACModes"] == {0: HVACMode.OFF, 4: HVACMode.HEAT}
    assert set(infos) == {
        "modelId",
        "HVACModesCapabilityId",
        "name",
        "type",
        "HVACModes",
        "winkable",
    }


@pytest.mark.parametrize("modelId", [1543, 1551, 1546, 1595, 1588, 1622])
def test_a_towel_rack_is_named_by_the_vendor(modelId):
    """These were spelled here once, in the house style, and are not any more.

    The vendor's own string is what the app shows and what the catalogue
    carries ; it is louder -- ASAMA CONNECTE II 1750W BLC -- and it is the
    same product. See docs/decisions.md.
    """
    assert get_model_infos(modelId)["name"] == MODEL_CATALOGUE[modelId]
    assert get_model_infos(modelId)["type"] is CozytouchDeviceType.TOWEL_RACK


# ------------------------------------------------ the Alfea Extensa S halves


@pytest.mark.parametrize(
    "modelId",
    [*range(2295, 2318), *range(2326, 2329), *range(1691, 1693)],
)
def test_every_alfea_extensa_s_id_resolves_off_the_catalogue(modelId):
    """The branch names these out of MODEL_CATALOGUE rather than a table of
    its own, so an id the catalogue does not carry would raise a KeyError at
    setup instead of falling through to a name.
    """
    infos = get_model_infos(modelId)

    assert infos["name"] == MODEL_CATALOGUE[modelId]
    assert infos["type"] == CozytouchDeviceType.HEAT_PUMP
    # Neither half carries a room setpoint : the control is on the slots
    # under them, and capability 8 on the interface is not a mode.
    assert infos["HVACModesCapabilityId"] == set()


def test_a_heating_circuit_slot_is_named_after_its_zone():
    """The slot ids say nothing but the index, so the zone is the only name a
    user recognises -- the same rule the room slots follow.
    """
    assert (
        get_model_infos(1388, zoneName="Circuit 1")["name"]
        == "Heating circuit (Circuit 1)"
    )
    assert get_model_infos(1389)["name"] == "Heating circuit (#2)"


def test_the_generator_slot_is_the_generator_under_another_name():
    """An Alfea Excellia S reports its generator as the slot 1391 rather than
    as a catalogue id, so it cannot be named off the catalogue the way the
    Extensa S halves are. Issue gduteil/cozytouch#173.
    """
    infos = get_model_infos(1391)

    assert infos["name"] == "Generator"
    assert infos["type"] == CozytouchDeviceType.HEAT_PUMP
    assert infos["HVACModesCapabilityId"] == set()


# ------------------------------------------------ the fourth ACI HYB badge


@pytest.mark.parametrize(
    ("modelId", "name"),
    [
        (1364, "THE DURALIS CONNECT VM 150 2200M PE"),
        (1365, "THE DURALIS CONNECT VM 200 2200M PE"),
        (1366, "THE DURALIS CONNECT VS 300 3000M PE"),
    ],
)
def test_a_catalogue_aci_hyb_water_heater_joins_the_platform(modelId, name):
    """The Duralis Connect under a fourth badge, read off the catalogue rather
    than a report : same product line, same volume, same power as 392-394. It
    claims what the nine captured ids claim and nothing more.
    """
    infos = get_model_infos(modelId)

    assert infos["name"] == name
    assert infos["type"] is CozytouchDeviceType.WATER_HEATER
    assert infos["HeatingModes"] == get_model_infos(393)["HeatingModes"]


def test_the_explorer_v5_coil_variant_reads_like_its_siblings():
    """1643 is TD 200 VS ATE 1200M TYB V5S SERP -- the 200L of 1641 with the
    coil of 1645, and the one id of the Atlantic badge left unmapped. The
    catalogue is the whole of the evidence, so it claims what they claim.
    """
    infos = get_model_infos(1643)

    assert infos["name"] == MODEL_CATALOGUE[1643]
    assert infos == {**get_model_infos(1641), "modelId": 1643, "name": infos["name"]}


@pytest.mark.parametrize("modelId", [1646, 1650, 1655, 1659, 1660, 1663])
def test_another_badge_of_the_explorer_platform_is_still_a_water_heater(modelId):
    """Eight brands share the platform and only Atlantic's has a commercial
    name we know, so these keep the catalogue's string -- the same text they
    already displayed. What they gain is the type, and the two entities that
    read it: a resistance sensor rather than a pump, and a hot water mode
    select with options in it.
    """
    infos = get_model_infos(modelId)

    assert infos["name"] == MODEL_CATALOGUE[modelId]
    assert infos["type"] is CozytouchDeviceType.WATER_HEATER
    assert infos["HeatingModes"] == get_model_infos(1641)["HeatingModes"]


# ------------------------------------------------ the catalogue line gaps


@pytest.mark.parametrize(
    ("modelId", "sibling", "name"),
    [
        (227, 54, "Naema 2 30"),
        (1445, 1444, "NAEMA 3 MICRO 30"),
        (1446, 1444, "NAEMA 3 MICRO 35"),
        (1448, 1447, "NAEMA 3 DUO 35"),
        (957, 1010, "EGEO VS 200L"),
        (1367, 1368, "Calypso SPLIT VM 150L"),
        (1670, 1669, "THE CV5 AEROMAX PREMIUM WH 150L NP"),
        (1954, 1957, "LINEO CONNECTE MP 040L 2250W"),
        (1961, 1962, "MALICIO 3 MP 040L 2250W"),
        (1967, 1966, "MALICIO 3 VM 150L 2400W"),
        (2345, 2346, "TD 200 VS ATL 1800M TYB CA"),
        (2375, 2374, "AE CV5 DACH FS 270L PE (DE)"),
        (219, 211, "Alfea Extensa Duo A.I. 3 R32 Thermor"),
    ],
)
def test_a_line_gap_claims_exactly_what_its_sibling_claims(modelId, sibling, name):
    """Another volume, another badge or another country of a line already
    mapped. The catalogue is the whole of the evidence, so none of these may
    claim anything its captured sibling does not -- only the name differs.
    """
    infos = get_model_infos(modelId)

    assert infos["name"] == name
    assert infos == {**get_model_infos(sibling), "modelId": modelId, "name": name}


def test_the_two_hundred_litre_malicio_says_which_form_factor_it_is():
    """MP and VM both exist at 100L and the captured names drop that letter.
    Dropping it here would give two products one name.
    """
    assert "MP" in get_model_infos(1964)["name"]
    assert "VM" in get_model_infos(1965)["name"]
    assert get_model_infos(1964)["name"] != get_model_infos(1965)["name"]


def test_the_lineo_volumes_inherit_the_missing_prog_mode():
    """1957 came from a capture and declares no prog mode. The volumes beside
    it are the same appliance, so copying the generic three would be inventing
    a mode nobody has seen this range offer.
    """
    for modelId in (1954, 1955, 1956):
        assert get_model_infos(modelId)["HeatingModes"] == {
            0: HEATING_MODE_MANUAL,
            3: HEATING_MODE_ECO_PLUS,
        }
