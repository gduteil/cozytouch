"""Atlantic Cozytouch device model mapping.

Mandatory :
    * modelId : modelId of the device
    * name : commercial name of the device.
    * type : device type from CozytouchDeviceType enum.
    * HVACModes : list of available HVAC value/mode pairs

Optional :
    * currentTemperatureAvailable : enable current temperature availability (default : True)
    * currentTemperatureAvailableZ1 : enable current temperature availability for Z1 (used for HEAT_PUMP, default : True)
    * currentTemperatureAvailableZ2 : enable current temperature availability for Z2 (used for HEAT_PUMP, default : True)
    * exhaustTemperatureAvailable : enable exhaust temperature availability (default : True)
    * fanModes : list of value/mode pairs
    * swingModes : list of value/mode pairs
    * quietModeAvailable : enable quiet mode availability (default : False)

"""  # noqa: D205

from enum import StrEnum

from homeassistant.components.climate import HVACMode
from homeassistant.components.climate.const import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    FAN_OFF,
    FAN_ON,
)

from .const import (
    HEATING_MODE_ECO_PLUS,
    HEATING_MODE_MANUAL,
    HEATING_MODE_PROG,
    SWING_MODE_DOWN,
    SWING_MODE_MIDDLE_DOWN,
    SWING_MODE_MIDDLE_UP,
    SWING_MODE_UP,
)


class CozytouchDeviceType(StrEnum):
    """Device types enum."""

    UNKNOWN = "unknown"
    THERMOSTAT = "thermostat"
    GAZ_BOILER = "gaz_boiler"
    HEAT_PUMP = "heat_pump"
    WATER_HEATER = "water_heater"
    TOWEL_RACK = "towel_rack"
    AC = "ac"
    AC_CONTROLLER = "ac_controller"
    HUB = "hub"


def get_model_infos(modelId: int, zoneName: str | None = None):
    """Return infos from model ID."""
    modelInfos = {"modelId": modelId, "HVACModesCapabilityId": {7, 8}}

    if modelId == 56:
        modelInfos["name"] = "Naema 2 Micro 25"
        modelInfos["type"] = CozytouchDeviceType.GAZ_BOILER
        modelInfos["HVACModes"] = {
            0: HVACMode.OFF,
            4: HVACMode.HEAT,
        }

    elif modelId == 61:
        modelInfos["name"] = "Naia 2 Micro 25"
        modelInfos["type"] = CozytouchDeviceType.GAZ_BOILER
        modelInfos["HVACModes"] = {
            0: HVACMode.OFF,
            4: HVACMode.HEAT,
        }

    elif modelId == 65:
        modelInfos["name"] = "Naema 2 Duo 25"
        modelInfos["type"] = CozytouchDeviceType.GAZ_BOILER
        modelInfos["HVACModes"] = {
            0: HVACMode.OFF,
            4: HVACMode.HEAT,
        }

    elif modelId == 76:
        modelInfos["name"] = "Alfea Extensa Duo AI UE"
        modelInfos["type"] = CozytouchDeviceType.HEAT_PUMP
        modelInfos["currentTemperatureAvailableZ1"] = False
        modelInfos["currentTemperatureAvailableZ2"] = True
        modelInfos["HVACModes"] = {
            0: HVACMode.OFF,
            4: HVACMode.HEAT,
        }

        modelInfos["HeatingModes"] = {
            0: HEATING_MODE_MANUAL,
        }

        modelInfos["exhaustTemperatureAvailable"] = False

    elif modelId == 211:
        modelInfos["name"] = "Alfea Extensa Duo A.I. 3 R32"
        modelInfos["type"] = CozytouchDeviceType.HEAT_PUMP
        modelInfos["currentTemperatureAvailableZ1"] = True
        modelInfos["currentTemperatureAvailableZ2"] = True

        modelInfos["HVACModesCapabilityId"] = {1, 2}

        modelInfos["HVACModes"] = {
            0: HVACMode.OFF,
            1: HVACMode.HEAT,
            2: HVACMode.AUTO,
        }

        modelInfos["HeatingModes"] = {
            0: HEATING_MODE_MANUAL,
        }

        modelInfos["exhaustTemperatureAvailable"] = False

    elif modelId == 235:
        modelInfos["name"] = "Thermostat Navilink Connect"
        modelInfos["type"] = CozytouchDeviceType.THERMOSTAT
        modelInfos["HVACModes"] = {
            0: HVACMode.OFF,
            4: HVACMode.HEAT,
        }

    elif modelId == 236:
        modelInfos["name"] = "Sauter Phazy"
        modelInfos["type"] = CozytouchDeviceType.WATER_HEATER
        modelInfos["HVACModes"] = {
            0: HVACMode.OFF,
            4: HVACMode.HEAT,
        }
        modelInfos["HeatingModes"] = {
            0: HEATING_MODE_MANUAL,
            3: HEATING_MODE_ECO_PLUS,
            4: HEATING_MODE_PROG,
        }

    elif modelId == 390:
        modelInfos["name"] = "AQUEO ACI HYB VM 150L 2200M"
        modelInfos["type"] = CozytouchDeviceType.WATER_HEATER
        modelInfos["HVACModes"] = {
            0: HVACMode.OFF,
            4: HVACMode.HEAT,
        }
        modelInfos["HeatingModes"] = {
            0: HEATING_MODE_MANUAL,
            3: HEATING_MODE_ECO_PLUS,
            4: HEATING_MODE_PROG,
        }

    elif modelId == 418:
        modelInfos["name"] = "Atlantic Loria Duo 6006"
        modelInfos["type"] = CozytouchDeviceType.THERMOSTAT
        modelInfos["exhaustTemperatureAvailable"] = True
        modelInfos["currentTemperatureAvailableZ1"] = True
        modelInfos["currentTemperatureAvailableZ2"] = False
        modelInfos["overrideModeAvailable"] = True

        modelInfos["HVACModes"] = {
            0: HVACMode.OFF,
            4: HVACMode.HEAT,
        }

    elif modelId == 556:
        modelInfos["name"] = "Naviclim Hub"
        modelInfos["type"] = CozytouchDeviceType.HUB
        modelInfos["HVACModes"] = {
            0: HVACMode.OFF,
        }

    elif modelId >= 557 and modelId <= 561:
        name = "Air Conditioner "
        if zoneName is not None:
            modelInfos["name"] = name + "(" + zoneName + ")"
        else:
            modelInfos["name"] = name + "(#" + str(modelId - 556) + ")"

        modelInfos["type"] = CozytouchDeviceType.AC
        modelInfos["currentTemperatureAvailable"] = False
        modelInfos["quietModeAvailable"] = True

        modelInfos["fanModes"] = {
            1: FAN_LOW,
            2: FAN_MEDIUM,
            3: FAN_HIGH,
            5: FAN_AUTO,
        }

        modelInfos["swingModes"] = {
            1: SWING_MODE_UP,
            2: SWING_MODE_MIDDLE_UP,
            3: SWING_MODE_MIDDLE_DOWN,
            4: SWING_MODE_DOWN,
        }

        modelInfos["HVACModes"] = {
            0: HVACMode.OFF,
            1: HVACMode.AUTO,
            3: HVACMode.COOL,
            4: HVACMode.HEAT,
            7: HVACMode.FAN_ONLY,
            8: HVACMode.DRY,
        }

    elif modelId >= 562 and modelId <= 566:
        name = "Air Conditioner User Interface "
        if zoneName is not None:
            modelInfos["name"] = name + "(" + zoneName + ")"
        else:
            modelInfos["name"] = name + "(#" + str(modelId - 561) + ")"

        modelInfos["type"] = CozytouchDeviceType.AC_CONTROLLER
        modelInfos["HVACModes"] = {
            0: HVACMode.OFF,
        }

    elif modelId == 1353:
        modelInfos["name"] = "Calypso Split Interface"
        modelInfos["type"] = CozytouchDeviceType.HUB
        modelInfos["HVACModes"] = {
            0: HVACMode.OFF,
        }

    elif modelId in (1369, 1376):
        modelInfos["name"] = "Calypso Split"
        modelInfos["type"] = CozytouchDeviceType.WATER_HEATER
        modelInfos["HVACModes"] = {
            0: HVACMode.OFF,
            4: HVACMode.HEAT,
        }

        modelInfos["HeatingModes"] = {
            0: HEATING_MODE_MANUAL,
            3: HEATING_MODE_ECO_PLUS,
            4: HEATING_MODE_PROG,
        }

    elif modelId in (1371, 1372):
        modelInfos["name"] = "Aeromax SPLIT 3"
        modelInfos["type"] = CozytouchDeviceType.WATER_HEATER
        modelInfos["HVACModes"] = {
            0: HVACMode.OFF,
            4: HVACMode.HEAT,
        }

        modelInfos["HeatingModes"] = {
            0: HEATING_MODE_MANUAL,
            3: HEATING_MODE_ECO_PLUS,
            4: HEATING_MODE_PROG,
        }

    elif modelId == 1381:
        modelInfos["name"] = "KELUD 1750W BLC"
        modelInfos["type"] = CozytouchDeviceType.TOWEL_RACK
        modelInfos["HVACModes"] = {
            0: HVACMode.OFF,
            4: HVACMode.HEAT,
        }

    elif modelId == 1382:
        modelInfos["name"] = "KELUD 1750W Anthracite Standard"
        modelInfos["type"] = CozytouchDeviceType.TOWEL_RACK
        modelInfos["HVACModes"] = {
            0: HVACMode.OFF,
            4: HVACMode.HEAT,
        }

    elif modelId == 1388:
        modelInfos["name"] = "Doris étroit 1500W BLC"
        modelInfos["type"] = CozytouchDeviceType.TOWEL_RACK
        modelInfos["HVACModes"] = {
            0: HVACMode.OFF,
            4: HVACMode.HEAT,
        }

    elif modelId == 1444:
        modelInfos["name"] = "Naema 3 Micro 25"
        modelInfos["type"] = CozytouchDeviceType.GAZ_BOILER
        modelInfos["HVACModes"] = {
            0: HVACMode.OFF,
            4: HVACMode.HEAT,
        }

    elif modelId == 1543:
        modelInfos["name"] = "Asama Connecté II Ventilo 1750W Blanc"
        modelInfos["type"] = CozytouchDeviceType.TOWEL_RACK
        modelInfos["HVACModes"] = {
            0: HVACMode.OFF,
            4: HVACMode.HEAT,
        }

    elif modelId == 1622:
        modelInfos["name"] = "Thermor Riva 5"
        modelInfos["type"] = CozytouchDeviceType.TOWEL_RACK
        modelInfos["HVACModes"] = {
            0: HVACMode.OFF,
            4: HVACMode.HEAT,
        }

    else:
        modelInfos["name"] = "Unknown product (" + str(modelId) + ")"
        modelInfos["type"] = CozytouchDeviceType.UNKNOWN
        modelInfos["HVACModes"] = {
            0: HVACMode.OFF,
            4: HVACMode.HEAT,
        }

    return modelInfos
