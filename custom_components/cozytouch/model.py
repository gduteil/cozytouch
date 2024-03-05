"""Atlantic Cozytouch device model mapping.

Mandatory :
    * modelId : modelId of the device
    * name : commercial name of the device.
    * type : device type from CozytouchDeviceType enum.
    * HVACModes : list of available HVAC value/mode pairs

Optional :
    * currentTemperatureAvailable : enable current temperature availability (default : True)
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


class CozytouchDeviceType(StrEnum):
    """Device types enum."""

    UNKNOWN = "unknown"
    THERMOSTAT = "thermostat"
    GAZ_BOILER = "gaz_boiler"
    HEAT_PUMP = "heat_pump"
    WATER_HEATER = "water_heater"
    AC = "ac"
    AC_CONTROLLER = "ac_controller"
    HUB = "hub"


def get_model_infos(modelId: int):
    """Return infos from model ID."""
    modelInfos = {"modelId": modelId}

    if modelId == 56:
        modelInfos["name"] = "Naema 2 Micro 25"
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
        modelInfos["HVACModes"] = {
            0: HVACMode.OFF,
            4: HVACMode.HEAT,
        }

        modelInfos["exhaustTemperatureAvailable"] = False

    elif modelId == 235:
        modelInfos["name"] = "Thermostat Navilink Connect"
        modelInfos["type"] = CozytouchDeviceType.THERMOSTAT
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

    elif modelId in (557, 558):
        if modelId == 557:
            modelInfos["name"] = "Takao M3 5.4kW"
        else:
            modelInfos["name"] = "Takao M3 2kW"

        modelInfos["type"] = CozytouchDeviceType.AC

        modelInfos["currentTemperatureAvailable"] = False
        modelInfos["quietModeAvailable"] = True

        modelInfos["fanModes"] = {
            0: FAN_OFF,
            1: FAN_ON,
            2: FAN_LOW,
            3: FAN_MEDIUM,
            4: FAN_HIGH,
            5: FAN_AUTO,
        }

        modelInfos["swingModes"] = {
            1: "Up",
            2: "Middle Up",
            3: "Middle Down",
            4: "Down",
        }

        modelInfos["HVACModes"] = {
            0: HVACMode.OFF,
            1: HVACMode.AUTO,
            3: HVACMode.COOL,
            4: HVACMode.HEAT,
            7: HVACMode.FAN_ONLY,
            8: HVACMode.DRY,
        }

    elif modelId in (562, 563):
        if modelId == 562:
            modelInfos["name"] = "Takao M3 5.4kW User Interface"
        else:
            modelInfos["name"] = "Takao M3 2kW User Interface"

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

    elif modelId == 1376:
        modelInfos["name"] = "Calypso Split 270L"
        modelInfos["type"] = CozytouchDeviceType.WATER_HEATER
        modelInfos["HVACModes"] = {
            0: HVACMode.OFF,
            4: HVACMode.HEAT,
        }

        modelInfos["HeatingModes"] = {
            0: "Manual",
            3: "Eco+",
        }

    else:
        modelInfos["name"] = "Unknown product (" + str(modelId) + ")"
        modelInfos["type"] = CozytouchDeviceType.UNKNOWN
        modelInfos["HVACModes"] = {
            0: HVACMode.OFF,
            4: HVACMode.HEAT,
        }

    return modelInfos
