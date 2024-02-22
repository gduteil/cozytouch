"""Atlantic Cozytouch capabilility mapping."""


def get_capability_infos(modelId: int, capabilityId: int) -> {}:
    """Get capabilities for a device."""
    if capabilityId == 7:
        if modelId in (557, 558) :
            return {
                "modelId": modelId,
                "name": "Air Conditionner",
                "type": "climate",
                "category": "sensor",
                "icon": "mdi:air-conditioner",
                "value_off": "0",
                "value_auto": "1",
                "value_cool": "3",
                "value_heat": "4",
                "value_fan": "7",
                "value_dry": "8",
                "activeCapabilityId": 7,
                "currentValueCapabilityId": 117,
                "targetHeatValueCapabilityId": 40,
                "lowestHeatValueCapabilityId": 160,
                "highestHeatValueCapabilityId": 161,
                "targetValueCapabilityId": 177,
                "lowestValueCapabilityId": 162,
                "highestValueCapabilityId": 163,
            }
        else :
            return {
                "modelId": modelId,
                "name": "Central Heating",
                "type": "climate",
                "category": "sensor",
                "icon": "mdi:radiator",
                "value_off": "0",
                "value_heat": "4",
                "activeCapabilityId": 7,
                "currentValueCapabilityId": 117,
                "targetHeatValueCapabilityId": 40,
                "lowestHeatValueCapabilityId": 160,
                "highestHeatValueCapabilityId": 161,
            }
    elif capabilityId == 19:
        return {
            "modelId": modelId,
            "name": "Temperature Setpoint",
            "type": "temperature",
            "category": "sensor",
        }
    elif capabilityId == 25:
        return {
            "modelId": modelId,
            "name": "Number of starts CH pump",
            "type": "int",
            "category": "diag",
            "icon": "mdi:water-pump",
        }
    elif capabilityId == 26:
        return {
            "modelId": modelId,
            "name": "Number of starts DHW pump",
            "type": "int",
            "category": "diag",
            "icon": "mdi:water-pump",
        }
    elif capabilityId == 28:
        return {
            "modelId": modelId,
            "name": "Number of hours CH pump",
            "type": "int",
            "category": "diag",
            "icon": "mdi:water-pump",
        }
    elif capabilityId == 29:
        return {
            "modelId": modelId,
            "name": "Number of hours DHW pump",
            "type": "int",
            "category": "diag",
            "icon": "mdi:water-pump",
        }
    elif capabilityId == 40:
        return {
            "modelId": modelId,
            "name": "Target Temperature",
            "type": "temperature",
            "category": "sensor",
        }
    elif capabilityId == 86:
        return {
            "modelId": modelId,
            "name": "Domestic Hot Water",
            "type": "switch",
            "category": "sensor",
            "icon": "mdi:faucet",
        }
    elif capabilityId == 100:
        return {
            "modelId": modelId,
            "name": "Water Pressure",
            "type": "pressure",
            "category": "sensor",
            "icon": "mdi:gauge",
        }
    elif capabilityId == 109:
        return {
            "modelId": modelId,
            "name": "Boiler Water Temperature",
            "type": "temperature",
            "category": "sensor",
        }
    elif capabilityId == 111:
        return {
            "modelId": modelId,
            "name": "DHW Temperature",
            "type": "temperature",
            "category": "sensor",
        }
    elif capabilityId == 116:
        return {
            "modelId": modelId,
            "name": "Exhaust Temperature",
            "type": "temperature",
            "category": "sensor",
        }
    elif capabilityId == 117:
        return {
            "modelId": modelId,
            "name": "Thermostat Temperature",
            "type": "temperature",
            "category": "sensor",
        }
    elif capabilityId == 152:
        return {
            "modelId": modelId,
            "name": "Away Mode",
            "type": "switch",
            "category": "sensor",
            "icon": "mdi:airplane",
            "value_off": "0",
            "value_on": "2",
        }
    elif capabilityId == 153:
        return {
            "modelId": modelId,
            "name": "Flame",
            "type": "binary",
            "category": "sensor",
            "icon": "mdi:fire",
        }
    elif capabilityId == 154:
        return {
            "modelId": modelId,
            "name": "Zone Zigbee",
            "type": "string",
            "category": "diag",
            "icon": "mdi:zigbee",
        }
    elif capabilityId in (160, 161):
        # Target temperature adjustment limits
        return {}
    elif capabilityId == 172:
        return {
            "modelId": modelId,
            "name": "Away Mode Temperature",
            "type": "away_temperature_adjustment",
            "category": "sensor",
            "lowestValueCapabilityId": 160,
            "highestValueCapabilityId": 161,
        }
    elif capabilityId == 184:
        return {
            "modelId": modelId,
            "name": "Time Control",
            "type": "switch",
            "category": "sensor",
            "icon": "mdi:clock-outline",
        }
    elif capabilityId == 219:
        return {
            "modelId": modelId,
            "name": "Wifi SSID",
            "type": "string",
            "category": "diag",
            "icon": "mdi:wifi",
        }
    elif capabilityId == 222:
        return {
            "modelId": modelId,
            "name": "Away Mode",
            "name_0": "Away Mode Start",
            "name_1": "Away Mode Stop",
            "type": "timestamp_2",
            "category": "sensor",
            "icon_0": "mdi:airplane-takeoff",
            "icon_1": "mdi:airplane-landing",
        }
    elif capabilityId == 316:
        return {
            "modelId": modelId,
            "name": "Interface FW",
            "type": "string",
            "category": "diag",
            "icon": "mdi:tag",
        }
    elif capabilityId == 100402:
        return {
            "modelId": modelId,
            "name": "Number of hours burner",
            "type": "int",
            "category": "diag",
            "icon": "mdi:fire",
        }
    elif capabilityId == 100406:
        return {
            "modelId": modelId,
            "name": "Number of starts burner",
            "type": "int",
            "category": "diag",
            "icon": "mdi:fire",
        }

    return None
