"""Atlantic Cozytouch capabilility mapping."""


def get_capability_infos(modelId: int, capabilityId: int) -> {}:
    """Get capabilities for a device."""
    if modelId == 235:
        return get_capability_infos_navilink(capabilityId)

    return None


def get_capability_infos_navilink(capabilityId: int) -> {}:
    """Get capabilities for a Navilink device."""
    modelId = 235

    if capabilityId == 7:
        return {
            "modelId": modelId,
            "name": "Central Heating",
            "type": "switch",
            "category": "sensor",
            "icon": "mdi:radiator",
            "value_off": "0",
            "value_on": "4",
        }
    elif capabilityId == 19:
        return {
            "modelId": modelId,
            "name": "Temperature Setpoint",
            "type": "temperature",
            "category": "sensor",
        }
    elif capabilityId == 40:
        return {
            "modelId": modelId,
            "name": "Target Temperature",
            "type": "temperature_adjustment",
            "category": "sensor",
            "activeCapabilityId": 7,
            "currentValueCapabilityId": 117,
            "lowestValueCapabilityId": 160,
            "highestValueCapabilityId": 161,
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
    elif capabilityId == 184:
        return {
            "modelId": modelId,
            "name": "Time Control",
            "type": "switch",
            "category": "sensor",
            "icon": "mdi:clock-outline",
        }
    elif capabilityId == 172:
        return {
            "modelId": modelId,
            "name": "Away Mode Temperature",
            "type": "away_temperature_adjustment",
            "category": "sensor",
            "lowestValueCapabilityId": 160,
            "highestValueCapabilityId": 161,
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

    return None
