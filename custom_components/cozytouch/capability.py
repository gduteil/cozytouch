"""Atlantic Cozytouch capabilility mapping."""

from .model import CozytouchDeviceType


def get_capability_infos(modelInfos: dict, capabilityId: int):  # noqa: C901
    """Get capabilities for a device."""
    modelId = modelInfos["modelId"]

    capability = {"modelId": modelId}

    if capabilityId == 7:
        if modelInfos["type"] == CozytouchDeviceType.GAZ_BOILER:
            capability["name"] = "Central Heating"
            capability["icon"] = "mdi:radiator"
        elif modelInfos["type"] == CozytouchDeviceType.AC:
            capability["name"] = "Air Conditioner"
            capability["icon"] = "mdi:air-conditioner"
            capability["targetCoolCapabilityId"] = 177
            capability["lowestValueCapabilityId"] = 162
            capability["highestValueCapabilityId"] = 163
        else:
            capability["name"] = "Heat"

        capability["type"] = "climate"
        capability["category"] = "sensor"
        capability["targetCapabilityId"] = 40
        capability["lowestValueCapabilityId"] = 160
        capability["highestValueCapabilityId"] = 161

        if modelInfos.get("currentTemperatureAvailable", True):
            capability["currentValueCapabilityId"] = 117

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
        capability["type"] = "temperature"
        capability["category"] = "sensor"

    # elif capabilityId == 295:
    #   capability["name"]="Power consumption"
    #   capability["type"]="power"
    #   capability["category"]="sensor"

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
        capability["name"] = "DHW Pump"
        capability["type"] = "binary"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:faucet"

    elif capabilityId == 100:
        capability["name"] = "Water Pressure"
        capability["type"] = "pressure"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:gauge"

    elif capabilityId == 109:
        capability["name"] = "Boiler Water Temperature"
        capability["type"] = "temperature"
        capability["category"] = "sensor"

    elif capabilityId == 111:
        capability["name"] = "DHW Temperature"
        capability["type"] = "temperature"
        capability["category"] = "sensor"

    elif capabilityId == 116:
        capability["name"] = "Exhaust Temperature"
        capability["type"] = "temperature"
        capability["category"] = "sensor"

    elif capabilityId == 117:
        capability["name"] = "Thermostat Temperature"
        capability["type"] = "temperature"
        capability["category"] = "sensor"

    elif capabilityId == 121:
        capability["name"] = "Version"
        capability["type"] = "string"
        capability["category"] = "diag"
        capability["icon"] = "mdi:tag"

    elif capabilityId == 152:
        capability["name"] = "Away Mode"
        capability["type"] = "switch"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:airplane"
        capability["value_off"] = "0"
        capability["value_on"] = "2"

    elif capabilityId == 153:
        capability["name"] = "Flame"
        capability["type"] = "binary"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:fire"

    elif capabilityId == 154:
        capability["name"] = "Zone Zigbee"
        capability["type"] = "string"
        capability["category"] = "diag"
        capability["icon"] = "mdi:zigbee"

    elif capabilityId in (160, 161):
        # Target temperature adjustment limits
        return {}

    elif capabilityId == 165:
        capability["name"] = "Boost Mode"
        capability["type"] = "switch"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:water-boiler"

    elif capabilityId == 172:
        capability["name"] = "Away Mode Temperature"
        capability["type"] = "away_temperature_adjustment"
        capability["category"] = "sensor"
        capability["lowestValueCapabilityId"] = 160
        capability["highestValueCapabilityId"] = 161

    elif capabilityId == 179:
        capability["name"] = "Wifi Signal"
        capability["type"] = "signal"
        capability["category"] = "diag"
        capability["icon"] = "mdi:wifi"

    elif capabilityId == 184:
        capability["name"] = "Time Control"
        capability["type"] = "switch"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:clock-outline"

    elif capabilityId == 219:
        capability["name"] = "Wifi SSID"
        capability["type"] = "string"
        capability["category"] = "diag"
        capability["icon"] = "mdi:wifi"

    elif capabilityId == 222:
        capability["name"] = "Away Mode"
        capability["name_0"] = "Away Mode Start"
        capability["name_1"] = "Away Mode Stop"
        capability["type"] = "timestamp_2"
        capability["category"] = "sensor"
        capability["icon_0"] = "mdi:airplane-takeoff"
        capability["icon_1"] = "mdi:airplane-landing"

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
        capability["name"] = "Temperature_267"
        capability["type"] = "temperature"
        capability["category"] = "diag"

    elif capabilityId == 271:
        capability["name"] = "Hot Water Available"
        capability["type"] = "percentage"
        capability["category"] = "sensor"

    elif capabilityId == 283:
        capability["name"] = "Off-Peak Hours"
        capability["type"] = "binary"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:clock-outline"

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
        capability["name"] = "Presence"
        capability["type"] = "binary"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:account"

    elif capabilityId == 100507:
        capability["name"] = "Eco mode"
        capability["type"] = "switch"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:flower-outline"

    elif capabilityId == 100801:
        # FAN mode
        return None

    elif capabilityId == 100804:
        # Swing mode
        return None

    else:
        return None

    return capability
