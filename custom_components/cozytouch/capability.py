"""Atlantic Cozytouch capabilility mapping."""

from homeassistant.const import UnitOfEnergy

from .const import CozytouchCapabilityVariableType
from .model import CozytouchDeviceType


def get_capability_infos(modelInfos: dict, capabilityId: int, capabilityValue: str):  # noqa: C901
    """Get capabilities for a device."""
    modelId = modelInfos["modelId"]

    capability = {"modelId": modelId}

    if capabilityId in (7, 8):
        # Default Ids
        capability["targetCapabilityId"] = 40
        capability["lowestValueCapabilityId"] = 160
        capability["highestValueCapabilityId"] = 161

        if modelInfos.get("currentTemperatureAvailable", True):
            capability["currentValueCapabilityId"] = 117

        if modelInfos["type"] == CozytouchDeviceType.GAZ_BOILER:
            capability["name"] = "Central Heating"
            capability["icon"] = "mdi:radiator"
            capability["progCapabilityId"] = 184
            capability["progOverrideCapabilityId"] = 157
            capability["progOverrideTotalTimeCapabilityId"] = 158
            capability["progOverrideTimeCapabilityId"] = 159
        elif modelInfos["type"] == CozytouchDeviceType.TOWEL_RACK:
            capability["name"] = "Heat"
            capability["icon"] = "mdi:heating-coil"
            capability["progCapabilityId"] = 184
            capability["progOverrideCapabilityId"] = 157
            capability["progOverrideTotalTimeCapabilityId"] = 158
            capability["progOverrideTimeCapabilityId"] = 159
        elif modelInfos["type"] == CozytouchDeviceType.AC:
            capability["name"] = "Air Conditioner"
            capability["icon"] = "mdi:air-conditioner"
            capability["targetCoolCapabilityId"] = 177
            capability["lowestCoolValueCapabilityId"] = 162
            capability["highestCoolValueCapabilityId"] = 163
            capability["activityCapabilityId"] = 100506
            capability["ecoCapabilityId"] = 100507
            capability["boostCapabilityId"] = 100505
        elif modelInfos["type"] == CozytouchDeviceType.HEAT_PUMP:
            if capabilityId == 7:
                capability["name"] = "Heat Pump Z1"
                capability["targetCapabilityId"] = 17
                if modelInfos.get("currentTemperatureAvailableZ1", True):
                    capability["currentValueCapabilityId"] = 119
                else:
                    capability["currentValueCapabilityId"] = None
            else:
                capability["name"] = "Heat Pump Z2"
                capability["targetCapabilityId"] = 18
                if modelInfos.get("currentTemperatureAvailableZ2", True):
                    capability["currentValueCapabilityId"] = 118
                else:
                    capability["currentValueCapabilityId"] = None

            capability["lowestValueCapabilityId"] = 172
            capability["highestValueCapabilityId"] = 171
            capability["icon"] = "mdi:heat-pump"
        else:
            capability["name"] = "Heat"

        capability["type"] = "climate"
        capability["category"] = "sensor"

        if "fanModes" in modelInfos:
            capability["fanModeCapabilityId"] = 100801

        if modelInfos.get("quietModeAvailable", False):
            capability["quietModeCapabilityId"] = 100802

        if "swingModes" in modelInfos:
            capability["swingModeCapabilityId"] = 100803
            capability["swingOnCapabilityId"] = 100804

    elif capabilityId == 19:
        capability["name"] = "Temperature Setpoint"
        capability["type"] = "temperature"
        capability["category"] = "sensor"

    elif capabilityId == 25:
        capability["name"] = "Number of starts CH pump"
        capability["type"] = "int"
        capability["category"] = "diag"
        capability["icon"] = "mdi:water-pump"

    elif capabilityId == 26:
        capability["name"] = "Number of starts DHW pump"
        capability["type"] = "int"
        capability["category"] = "diag"
        capability["icon"] = "mdi:water-pump"

    elif capabilityId == 28:
        capability["name"] = "Number of hours CH pump"
        capability["type"] = "int"
        capability["category"] = "diag"
        capability["icon"] = "mdi:water-pump"

    elif capabilityId == 29:
        capability["name"] = "Number of hours DHW pump"
        capability["type"] = "int"
        capability["category"] = "diag"
        capability["icon"] = "mdi:water-pump"

    elif capabilityId == 40:
        capability["name"] = "Target Temperature"
        capability["type"] = "temperature_adjustment_number"
        capability["category"] = "sensor"
        capability["lowestValueCapabilityId"] = 160
        capability["highestValueCapabilityId"] = 161

    elif capabilityId == 44:
        capability["name"] = "CH Power consumption"
        capability["type"] = "energy"
        capability["displayed_unit_of_measurement"] = UnitOfEnergy.KILO_WATT_HOUR
        capability["category"] = "sensor"
        capability["icon"] = "mdi:radiator"

    elif capabilityId == 45:
        capability["name"] = "DHW Power consumption"
        capability["type"] = "energy"
        capability["displayed_unit_of_measurement"] = UnitOfEnergy.KILO_WATT_HOUR
        capability["category"] = "sensor"
        capability["icon"] = "mdi:faucet"

    elif capabilityId == 46:
        capability["name"] = "Total Power consumption"
        capability["type"] = "energy"
        capability["displayed_unit_of_measurement"] = UnitOfEnergy.KILO_WATT_HOUR
        capability["category"] = "sensor"
        capability["icon"] = "mdi:water-boiler"

    elif capabilityId in (57, 59):
        capability["name"] = "Power consumption"
        capability["type"] = "energy"
        capability["displayed_unit_of_measurement"] = UnitOfEnergy.KILO_WATT_HOUR
        capability["category"] = "sensor"

    elif capabilityId == 86:
        capability["name"] = "Domestic Hot Water"
        capability["type"] = "switch"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:faucet"

    elif capabilityId == 87:
        capability["name"] = "Heating Mode"
        capability["type"] = "select"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:water-boiler"
        capability["modelList"] = "HeatingModes"

    elif capabilityId == 99:
        if modelInfos["type"] == CozytouchDeviceType.WATER_HEATER:
            capability["name"] = "Resistance"
            capability["icon"] = "mdi:radiator"
        else:
            capability["name"] = "DHW Pump"
            capability["icon"] = "mdi:faucet"

        capability["type"] = "binary"
        capability["category"] = "sensor"

    elif capabilityId == 100:
        capability["name"] = "Water Pressure"
        capability["type"] = "pressure"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:gauge"

    elif capabilityId in (101, 102, 103, 104):
        capability["name"] = "Capability_" + str(capabilityId)
        capability["type"] = "string"
        capability["value_type"] = CozytouchCapabilityVariableType.ARRAY
        capability["category"] = "sensor"

    elif capabilityId == 109:
        capability["name"] = "Boiler Water Temperature"
        capability["type"] = "temperature"
        capability["category"] = "sensor"

    elif capabilityId == 111:
        capability["name"] = "DHW Temperature"
        capability["type"] = "temperature"
        capability["category"] = "sensor"

    elif capabilityId == 116:
        if modelInfos.get("exhaustTemperatureAvailable", True):
            capability["name"] = "Exhaust Temperature"
            capability["type"] = "temperature"
            capability["category"] = "sensor"
        else:
            return {}

    elif capabilityId == 117:
        capability["name"] = "Thermostat Temperature"
        capability["type"] = "temperature"
        capability["category"] = "sensor"

    elif capabilityId == 119:
        # Outside temperature is invalid when value is -327.68
        if float(capabilityValue) > -327.68:
            capability["name"] = "Outside Temperature"
            capability["type"] = "temperature"
            capability["category"] = "sensor"
        else:
            return {}

    elif capabilityId == 121:
        capability["name"] = "Version"
        capability["type"] = "string"
        capability["category"] = "diag"
        capability["icon"] = "mdi:tag"

    elif capabilityId in (152, 227):
        capability["name"] = "Away Mode"
        capability["type"] = "away_mode_switch"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:airplane"
        capability["value_off"] = "0"
        capability["value_on"] = "1"
        capability["value_pending"] = "2"
        capability["timestampsCapabilityId"] = 222

    elif capabilityId == 153:
        if modelInfos["type"] == CozytouchDeviceType.TOWEL_RACK:
            capability["name"] = "Resistance"
            capability["icon"] = "mdi:radiator"
        else:
            capability["name"] = "Flame"
            capability["icon"] = "mdi:fire"

        capability["type"] = "binary"
        capability["category"] = "sensor"

    elif capabilityId == 154:
        capability["name"] = "Zone 1"
        capability["type"] = "string"
        capability["category"] = "diag"
        capability["icon"] = "mdi:home-floor-1"

    elif capabilityId == 155:
        capability["name"] = "Zone 2"
        capability["type"] = "string"
        capability["category"] = "diag"
        capability["icon"] = "mdi:home-floor-2"

    # elif capabilityId == 157:
    #    # Prog override flag
    #    return {}

    elif capabilityId == 158:
        if modelInfos["type"] == CozytouchDeviceType.TOWEL_RACK:
            capability["name"] = "Override Total Time"
        else:
            capability["name"] = "Override Total Time Z1"

        capability["type"] = "hours_adjustment_number"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:clock-outline"
        capability["lowest_value"] = 1
        capability["highest_value"] = 24

    elif capabilityId == 159:
        if modelInfos["type"] == CozytouchDeviceType.TOWEL_RACK:
            capability["name"] = "Override Remaining Time"
        else:
            capability["name"] = "Override Remaining Time Z1"

        capability["type"] = "time"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:clock-outline"

    # elif capabilityId in (160, 161):
    #    # Target temperature adjustment limits
    #    return {}

    elif capabilityId == 165:
        capability["name"] = "Boost Mode"
        capability["type"] = "switch"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:water-boiler"

        if modelInfos["type"] == CozytouchDeviceType.HEAT_PUMP:
            capability["value_off"] = "false"
            capability["value_on"] = "true"

    elif capabilityId == 172:
        capability["name"] = "Away Mode Temperature"
        capability["type"] = "temperature_adjustment_number"
        capability["category"] = "sensor"
        capability["lowestValueCapabilityId"] = 160
        capability["highestValueCapabilityId"] = 161

    elif capabilityId == 177:
        capability["name"] = "Target Cool Temperature"
        capability["type"] = "temperature_adjustment_number"
        capability["category"] = "sensor"
        capability["lowestValueCapabilityId"] = 162
        capability["highestValueCapabilityId"] = 163

    elif capabilityId == 179:
        capability["name"] = "Wifi Signal"
        capability["type"] = "signal"
        capability["category"] = "diag"
        capability["icon"] = "mdi:wifi"

    elif capabilityId == 184:
        capability["name"] = "Prog mode"
        capability["type"] = "switch"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:clock-outline"

    elif capabilityId == 196:
        capability["name"] = "Prog 01 (Mon Z1)"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 197:
        capability["name"] = "Prog 02 (Tue Z1)"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 198:
        capability["name"] = "Prog 03 (Wed Z1)"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 199:
        capability["name"] = "Prog 04 (Thu Z1)"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 200:
        capability["name"] = "Prog 05 (Fri Z1)"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 201:
        capability["name"] = "Prog 06 (Sat Z1)"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 202:
        capability["name"] = "Prog 07 (Sun Z1)"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 203:
        capability["name"] = "Prog 08 (Mon Z2)"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 204:
        capability["name"] = "Prog 09 (Tue Z2)"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 205:
        capability["name"] = "Prog 10 (Wed Z2)"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 206:
        capability["name"] = "Prog 11 (Thu Z2)"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 207:
        capability["name"] = "Prog 12 (Fri Z2)"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 208:
        capability["name"] = "Prog 13 (Sat Z2)"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 209:
        capability["name"] = "Prog 14 (Sun Z2)"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 219:
        capability["name"] = "Wifi SSID"
        capability["type"] = "string"
        capability["category"] = "diag"
        capability["icon"] = "mdi:wifi"

    elif capabilityId == 222:
        capability["name"] = "Away Mode"
        capability["name_0"] = "Away Mode Start"
        capability["name_1"] = "Away Mode Stop"
        capability["type"] = "away_mode_timestamps"
        capability["category"] = "sensor"
        capability["icon_0"] = "mdi:airplane-takeoff"
        capability["icon_1"] = "mdi:airplane-landing"
        capability["timezoneCapabilityId"] = 315

    elif capabilityId == 232:
        capability["name"] = "Boost Total Time"
        capability["type"] = "time"
        capability["category"] = "diagnostic"
        capability["icon"] = "mdi:clock-outline"

    elif capabilityId == 233:
        capability["name"] = "Boost Remaining Time"
        capability["type"] = "time"
        capability["category"] = "diagnostic"
        capability["icon"] = "mdi:clock-outline"

    elif capabilityId == 245:
        capability["name"] = "Prog1 (Mon)"
        capability["type"] = "progtime"
        capability["category"] = "diag"

    elif capabilityId == 246:
        capability["name"] = "Prog2 (Tue)"
        capability["type"] = "progtime"
        capability["category"] = "diag"

    elif capabilityId == 247:
        capability["name"] = "Prog3 (Wed)"
        capability["type"] = "progtime"
        capability["category"] = "diag"

    elif capabilityId == 248:
        capability["name"] = "Prog4 (Thu)"
        capability["type"] = "progtime"
        capability["category"] = "diag"

    elif capabilityId == 249:
        capability["name"] = "Prog5 (Fri)"
        capability["type"] = "progtime"
        capability["category"] = "diag"

    elif capabilityId == 250:
        capability["name"] = "Prog6 (Sat)"
        capability["type"] = "progtime"
        capability["category"] = "diag"

    elif capabilityId == 251:
        capability["name"] = "Prog7 (Sun)"
        capability["type"] = "progtime"
        capability["category"] = "diag"

    elif capabilityId == 258:
        capability["name"] = "Tank Capacity"
        capability["type"] = "volume"
        capability["category"] = "sensor"

    elif capabilityId == 264:
        capability["name"] = "Condenser Temperature"
        capability["type"] = "temperature"
        capability["category"] = "sensor"

    elif capabilityId == 265:
        capability["name"] = "Tank Middle Temperature"
        capability["type"] = "temperature"
        capability["category"] = "sensor"

    elif capabilityId == 266:
        capability["name"] = "Tank Top Temperature"
        capability["type"] = "temperature"
        capability["category"] = "sensor"

    elif capabilityId == 267:
        capability["name"] = "Tank Bottom Temperature"
        capability["type"] = "temperature"
        capability["category"] = "sensor"

    elif capabilityId == 269:
        capability["name"] = "Water Consumption"
        capability["type"] = "volume"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:water-pump"

    elif capabilityId == 271:
        capability["name"] = "Hot Water Available"
        capability["type"] = "percentage"
        capability["category"] = "sensor"

    elif capabilityId == 283:
        capability["name"] = "Off-Peak Hours"
        capability["type"] = "binary"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:clock-outline"

    elif capabilityId == 315:
        capability["name"] = "Timezone"
        capability["type"] = "timezone"
        capability["category"] = "diag"
        capability["icon"] = "mdi:map-clock-outline"

    elif capabilityId == 316:
        capability["name"] = "Interface FW"
        capability["type"] = "string"
        capability["category"] = "diag"
        capability["icon"] = "mdi:tag"

    elif capabilityId == 100402:
        capability["name"] = "Number of hours burner"
        capability["type"] = "int"
        capability["category"] = "diag"
        capability["icon"] = "mdi:fire"

    elif capabilityId == 100406:
        capability["name"] = "Number of starts burner"
        capability["type"] = "int"
        capability["category"] = "diag"
        capability["icon"] = "mdi:fire"

    elif capabilityId == 100505:
        capability["name"] = "Powerful mode"
        capability["type"] = "switch"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:wind-power"

    elif capabilityId == 100506:
        if modelInfos["type"] == CozytouchDeviceType.TOWEL_RACK:
            capability = {}
        else:
            capability["name"] = "Presence mode"
            capability["type"] = "switch"
            capability["category"] = "sensor"
            capability["icon"] = "mdi:account"

    elif capabilityId == 100507:
        capability["name"] = "Eco mode"
        capability["type"] = "switch"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:flower-outline"

    elif capabilityId == 100320:
        capability["name"] = "Monday Heat prog"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100321:
        capability["name"] = "Tuesday Heat prog"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100322:
        capability["name"] = "Wednesday Heat prog"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100323:
        capability["name"] = "Thursday Heat prog"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100324:
        capability["name"] = "Friday Heat prog"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100325:
        capability["name"] = "Saturday Heat prog"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100326:
        capability["name"] = "Sunday Heat prog"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100327:
        capability["name"] = "Monday Cool prog"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100328:
        capability["name"] = "Tuesday Cool prog"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100329:
        capability["name"] = "Wednesday Cool prog"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100330:
        capability["name"] = "Thursday Cool prog"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100331:
        capability["name"] = "Friday Cool prog"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100332:
        capability["name"] = "Saturday Cool prog"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100333:
        capability["name"] = "Sunday Cool prog"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100802:
        capability["name"] = "Quiet mode"
        capability["type"] = "switch"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:fan-minus"

    elif capabilityId == 100804:
        capability["name"] = "Swing mode"
        capability["type"] = "switch"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:arrow-oscillating"

    elif capabilityId == 104044:
        capability["name"] = "Boost Mode"
        capability["type"] = "switch"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:heat-wave"

    elif capabilityId == 105906:
        capability["name"] = "Target 105906"
        capability["type"] = "temperature_percent_adjustment_number"
        capability["category"] = "sensor"
        capability["temperatureMin"] = 15.0
        capability["temperatureMax"] = 65.0

    elif capabilityId == 105907:
        capability["name"] = "Target 105907"
        capability["type"] = "temperature_percent_adjustment_number"
        capability["category"] = "sensor"
        capability["temperatureMin"] = 15.0
        capability["temperatureMax"] = 65.0

    # For test
    elif capabilityId in (22, 312):
        capability["name"] = "Temp_" + str(capabilityId)
        capability["type"] = "temperature_adjustment_number"
        capability["category"] = "sensor"

    else:
        return None

    return capability
