"""Atlantic Cozytouch capabilility mapping."""

from homeassistant.const import UnitOfEnergy, UnitOfPressure

from .const import CozytouchCapabilityVariableType
from .model import CozytouchDeviceType


def get_capability_infos(modelInfos: dict, capabilityId: int, capabilityValue: str):  # noqa: C901
    """Get capabilities for a device."""
    modelId = modelInfos["modelId"]

    capability = {"modelId": modelId, "capabilityId": capabilityId}

    if (
        capabilityId in (1, 2, 7, 8)
        and capabilityId in modelInfos["HVACModesCapabilityId"]
    ):
        # Default Ids
        capability["targetCapabilityId"] = 40
        capability["lowestValueCapabilityId"] = 160
        capability["highestValueCapabilityId"] = 161

        if modelInfos.get("currentTemperatureAvailable", True):
            capability["currentValueCapabilityId"] = 117

        if modelInfos["type"] == CozytouchDeviceType.GAZ_BOILER:
            capability["name"] = "central_heating"
            capability["icon"] = "mdi:radiator"
            capability["progCapabilityId"] = 184
            capability["progOverrideCapabilityId"] = 157
            capability["progOverrideTotalTimeCapabilityId"] = 158
            capability["progOverrideTimeCapabilityId"] = 159
        elif modelInfos["type"] == CozytouchDeviceType.TOWEL_RACK:
            capability["name"] = "heat"
            capability["icon"] = "mdi:heating-coil"
            capability["progCapabilityId"] = 184
            capability["progOverrideCapabilityId"] = 157
            capability["progOverrideTotalTimeCapabilityId"] = 158
            capability["progOverrideTimeCapabilityId"] = 159
        elif modelInfos["type"] == CozytouchDeviceType.AC:
            capability["name"] = "air_conditioner"
            capability["icon"] = "mdi:air-conditioner"
            capability["targetCoolCapabilityId"] = 177
            capability["lowestCoolValueCapabilityId"] = 162
            capability["highestCoolValueCapabilityId"] = 163
            capability["activityCapabilityId"] = 100506
            capability["ecoCapabilityId"] = 100507
            capability["boostCapabilityId"] = 100505
        elif modelInfos["type"] == CozytouchDeviceType.HEAT_PUMP:
            if capabilityId in (1, 7):
                capability["name"] = "heat_pump_z1"
                capability["targetCapabilityId"] = 17
                if modelInfos.get("currentTemperatureAvailableZ1", True):
                    capability["currentValueCapabilityId"] = 117
                else:
                    capability["currentValueCapabilityId"] = None
            else:
                capability["name"] = "heat_pump_z2"
                capability["targetCapabilityId"] = 18
                if modelInfos.get("currentTemperatureAvailableZ2", True):
                    capability["currentValueCapabilityId"] = 118
                else:
                    capability["currentValueCapabilityId"] = None

            # capability["lowestValueCapabilityId"] = 172
            # capability["highestValueCapabilityId"] = 171
            capability.pop("lowestValueCapabilityId")
            capability.pop("highestValueCapabilityId")
            capability["icon"] = "mdi:heat-pump"
        elif modelInfos["type"] == CozytouchDeviceType.THERMOSTAT:
            # V2 electric heater / underfloor thermostat (e.g. Atlantic DIVALI,
            # Atlantic Thermostat PRE). Uses ROOM_CURRENT_HEATING_TARGET_TEMPERATURE
            # (cap 40) as setpoint, no cooling.
            capability["name"] = "heat"
            capability["icon"] = "mdi:thermostat"
        else:
            capability["name"] = "heat"

        capability["type"] = "climate"
        capability["category"] = "sensor"

        if "fanModes" in modelInfos:
            capability["fanModeCapabilityId"] = 100801

        if modelInfos.get("quietModeAvailable", False):
            capability["quietModeCapabilityId"] = 100802

        if modelInfos.get("overrideModeAvailable", True):
            capability["progCapabilityId"] = 184
            capability["progOverrideCapabilityId"] = 157
            capability["progOverrideTotalTimeCapabilityId"] = 158
            capability["progOverrideTimeCapabilityId"] = 159

        if "swingModes" in modelInfos:
            capability["swingModeCapabilityId"] = 100803
            capability["swingOnCapabilityId"] = 100804

    elif capabilityId == 19:
        capability["name"] = "temperature_setpoint"
        capability["type"] = "temperature"
        capability["category"] = "sensor"

    elif capabilityId == 22:
        capability["name"] = "target_temperature_dhw"
        capability["type"] = "temperature_adjustment_number"
        capability["category"] = "sensor"
        capability["lowestValueCapabilityId"] = 160
        capability["highestValueCapabilityId"] = 161

    elif capabilityId == 25:
        capability["name"] = "number_of_starts_ch_pump"
        capability["type"] = "int"
        capability["category"] = "diag"
        capability["icon"] = "mdi:water-pump"

    elif capabilityId == 26:
        capability["name"] = "number_of_starts_dhw_pump"
        capability["type"] = "int"
        capability["category"] = "diag"
        capability["icon"] = "mdi:water-pump"

    elif capabilityId == 28:
        capability["name"] = "number_of_hours_ch_pump"
        capability["type"] = "int"
        capability["category"] = "diag"
        capability["icon"] = "mdi:water-pump"

    elif capabilityId == 29:
        capability["name"] = "number_of_hours_dhw_pump"
        capability["type"] = "int"
        capability["category"] = "diag"
        capability["icon"] = "mdi:water-pump"

    elif capabilityId == 40:
        capability["name"] = "target_temperature"
        capability["type"] = "temperature_adjustment_number"
        capability["category"] = "sensor"
        capability["lowestValueCapabilityId"] = 160
        capability["highestValueCapabilityId"] = 161

    elif capabilityId == 41:
        capability["name"] = "target_temperature_eco_z1"
        capability["type"] = "temperature_adjustment_number"
        capability["category"] = "sensor"
        capability["lowestValueCapabilityId"] = 160
        capability["highestValueCapabilityId"] = 161

    elif capabilityId == 42:
        capability["name"] = "target_temperature_eco_z2"
        capability["type"] = "temperature_adjustment_number"
        capability["category"] = "sensor"
        capability["lowestValueCapabilityId"] = 160
        capability["highestValueCapabilityId"] = 161

    elif capabilityId == 44:
        capability["name"] = "ch_power_consumption"
        capability["type"] = "energy"
        capability["displayed_unit_of_measurement"] = UnitOfEnergy.KILO_WATT_HOUR
        capability["category"] = "sensor"
        capability["icon"] = "mdi:radiator"

    elif capabilityId == 45:
        capability["name"] = "dhw_power_consumption"
        capability["type"] = "energy"
        capability["displayed_unit_of_measurement"] = UnitOfEnergy.KILO_WATT_HOUR
        capability["category"] = "sensor"
        capability["icon"] = "mdi:faucet"

    elif capabilityId == 46:
        capability["name"] = "total_power_consumption"
        capability["type"] = "energy"
        capability["displayed_unit_of_measurement"] = UnitOfEnergy.KILO_WATT_HOUR
        capability["category"] = "sensor"
        capability["icon"] = "mdi:water-boiler"

    elif capabilityId in (57, 59):
        capability["name"] = "power_consumption"
        capability["type"] = "energy"
        capability["displayed_unit_of_measurement"] = UnitOfEnergy.KILO_WATT_HOUR
        capability["category"] = "sensor"

    elif capabilityId == 86:
        capability["name"] = "domestic_hot_water"
        capability["type"] = "switch"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:faucet"

    elif capabilityId == 87:
        capability["name"] = "heating_mode"
        capability["type"] = "select"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:water-boiler"
        capability["modelList"] = "HeatingModes"

    elif capabilityId == 88:
        capability["name"] = "model_name"
        capability["type"] = "string"
        capability["category"] = "diag"
        capability["icon"] = "mdi:tag"

    elif capabilityId in (94, 98):
        capability["name"] = "product_number"
        capability["type"] = "string"
        capability["category"] = "diag"
        capability["icon"] = "mdi:tag"

    elif capabilityId == 99:
        if modelInfos["type"] == CozytouchDeviceType.WATER_HEATER:
            capability["name"] = "resistance"
            capability["icon"] = "mdi:radiator"
        else:
            capability["name"] = "dhw_pump"
            capability["icon"] = "mdi:faucet"

        capability["type"] = "binary"
        capability["category"] = "sensor"

    elif capabilityId == 100:
        capability["name"] = "water_pressure"
        capability["type"] = "pressure"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:gauge"
        capability["displayed_unit_of_measurement"] = UnitOfPressure.BAR

    elif capabilityId in (101, 102, 103, 104):
        capability["name"] = "Capability_" + str(capabilityId)
        capability["type"] = "string"
        capability["value_type"] = CozytouchCapabilityVariableType.ARRAY
        capability["category"] = "sensor"

    elif capabilityId == 109:
        capability["name"] = "boiler_water_temperature"
        capability["type"] = "temperature"
        capability["category"] = "sensor"

    elif capabilityId == 111:
        capability["name"] = "dhw_temperature"
        capability["type"] = "temperature"
        capability["category"] = "sensor"

    elif capabilityId == 116:
        if modelInfos.get("exhaustTemperatureAvailable", True):
            capability["name"] = "exhaust_temperature"
            capability["type"] = "temperature"
            capability["category"] = "sensor"
        else:
            return {}

    elif capabilityId == 117:
        capability["name"] = "thermostat_temperature_z1"
        capability["type"] = "temperature"
        capability["category"] = "sensor"

    elif capabilityId == 118:
        capability["name"] = "thermostat_temperature_z2"
        capability["type"] = "temperature"
        capability["category"] = "sensor"

    elif capabilityId == 119:
        # Outside temperature is invalid when value is -327.68
        if float(capabilityValue) > -327.68:
            capability["name"] = "outside_temperature"
            capability["type"] = "temperature"
            capability["category"] = "sensor"
        else:
            return {}

    elif capabilityId == 121:
        capability["name"] = "version"
        capability["type"] = "string"
        capability["category"] = "diag"
        capability["icon"] = "mdi:tag"

    elif capabilityId in (152, 227):
        capability["name"] = "away_mode"
        capability["type"] = "away_mode_switch"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:airplane"
        capability["value_off"] = "0"
        capability["value_on"] = "1"
        capability["value_pending"] = "2"
        if capabilityId == 152:
            capability["timestampsCapabilityId"] = 222
        elif capabilityId == 227:
            capability["timestampsCapabilityId"] = 226

    elif capabilityId == 153:
        if modelInfos["type"] == CozytouchDeviceType.TOWEL_RACK:
            capability["name"] = "resistance"
            capability["icon"] = "mdi:radiator"
        else:
            capability["name"] = "flame"
            capability["icon"] = "mdi:fire"

        capability["type"] = "binary"
        capability["category"] = "sensor"

    elif capabilityId == 154:
        capability["name"] = "zone_1"
        capability["type"] = "string"
        capability["category"] = "diag"
        capability["icon"] = "mdi:home-floor-1"

    elif capabilityId == 155:
        capability["name"] = "zone_2"
        capability["type"] = "string"
        capability["category"] = "diag"
        capability["icon"] = "mdi:home-floor-2"

    # elif capabilityId == 157:
    #    # Prog override flag
    #    return {}

    elif capabilityId == 158:
        if modelInfos["type"] == CozytouchDeviceType.TOWEL_RACK:
            capability["name"] = "override_total_time"
        else:
            capability["name"] = "override_total_time_z1"

        capability["type"] = "hours_adjustment_number"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:clock-outline"
        capability["lowest_value"] = 1
        capability["highest_value"] = 24

    elif capabilityId == 159:
        if modelInfos["type"] == CozytouchDeviceType.TOWEL_RACK:
            capability["name"] = "override_remain_time"
        else:
            capability["name"] = "override_remain_time_z1"

        capability["type"] = "time"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:clock-outline"

    elif capabilityId == 160:
        # Target temperature adjustment min limit
        capability["name"] = "temperature_adjustment_min"
        capability["type"] = "temperature"
        capability["category"] = "diag"
        capability["icon"] = "mdi:thermometer-chevron-down"

    elif capabilityId == 161:
        # Target temperature adjustment max limit
        capability["name"] = "temperature_adjustment_max"
        capability["type"] = "temperature_adjustment_number"
        capability["category"] = "diag"
        capability["icon"] = "mdi:thermometer-chevron-up"
        capability["lowest_value"] = 19
        capability["highest_value"] = 28
        capability["step"] = 0.5

    elif capabilityId == 165:
        capability["name"] = "boost_mode"
        capability["type"] = "switch"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:water-boiler"

        if modelInfos["type"] == CozytouchDeviceType.HEAT_PUMP:
            capability["value_off"] = "false"
            capability["value_on"] = "true"

    elif capabilityId == 169:
        capability["name"] = "radio_signal"
        capability["type"] = "percentage"
        capability["category"] = "diag"
        capability["icon"] = "mdi:radio-tower"

    elif capabilityId == 172:
        capability["name"] = "away_mode_temperature"
        capability["type"] = "temperature_adjustment_number"
        capability["category"] = "sensor"
        capability["lowestValueCapabilityId"] = 160
        capability["highestValueCapabilityId"] = 161

    elif capabilityId == 177:
        if modelInfos["type"] in (
            CozytouchDeviceType.GAZ_BOILER,
            CozytouchDeviceType.THERMOSTAT,
        ):
            # AC-only setpoint. Heating-only devices don't have a cool target.
            return {}

        capability["name"] = "target_cool_temperature"
        capability["type"] = "temperature_adjustment_number"
        capability["category"] = "sensor"
        capability["lowestValueCapabilityId"] = 162
        capability["highestValueCapabilityId"] = 163

    elif capabilityId == 179:
        capability["name"] = "wifi_signal"
        capability["type"] = "signal"
        capability["category"] = "diag"
        capability["icon"] = "mdi:wifi"

    elif capabilityId == 181:
        # Ignore, same as heat sensor (7, 8)
        return {}

    elif capabilityId == 184:
        capability["name"] = "prog_mode"
        capability["type"] = "switch"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:clock-outline"

    elif capabilityId == 196:
        capability["name"] = "prog_01_z1"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 197:
        capability["name"] = "prog_02_z1"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 198:
        capability["name"] = "prog_03_z1"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 199:
        capability["name"] = "prog_04_z1"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 200:
        capability["name"] = "prog_05_z1"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 201:
        capability["name"] = "prog_06_z1"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 202:
        capability["name"] = "prog_07_z1"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 203:
        capability["name"] = "prog_08_z2"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 204:
        capability["name"] = "prog_09_z2"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 205:
        capability["name"] = "prog_10_z2"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 206:
        capability["name"] = "prog_11_z2"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 207:
        capability["name"] = "prog_12_z2"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 208:
        capability["name"] = "prog_13_z2"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 209:
        capability["name"] = "prog_14_z2"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 219:
        capability["name"] = "wifi_ssid"
        capability["type"] = "string"
        capability["category"] = "diag"
        capability["icon"] = "mdi:wifi"

    elif capabilityId in (222, 226):
        capability["name"] = "away_mode"
        capability["name_0"] = "away_mode_start"
        capability["name_1"] = "away_mode_stop"
        capability["type"] = "away_mode_timestamps"
        capability["category"] = "sensor"
        capability["icon_0"] = "mdi:airplane-takeoff"
        capability["icon_1"] = "mdi:airplane-landing"
        capability["timezoneCapabilityId"] = 315
        if capabilityId == 222:
            capability["capabilityDuplicate"] = 226
        else:
            capability["capabilityDuplicate"] = 222

    elif capabilityId == 231:
        capability["name"] = "target_temperature"
        capability["type"] = "temperature_adjustment_number"
        capability["category"] = "sensor"
        capability["lowestValueCapabilityId"] = 105301
        capability["highestValueCapabilityId"] = 105304

    elif capabilityId == 232:
        capability["name"] = "boost_total_time"
        capability["type"] = "time"
        capability["category"] = "diagnostic"
        capability["icon"] = "mdi:clock-outline"

    elif capabilityId == 233:
        capability["name"] = "boost_remaining_time"
        capability["type"] = "time"
        capability["category"] = "diagnostic"
        capability["icon"] = "mdi:clock-outline"

    elif capabilityId == 245:
        capability["name"] = "prog_01"
        capability["type"] = "progtime"
        capability["category"] = "diag"

    elif capabilityId == 246:
        capability["name"] = "prog_02"
        capability["type"] = "progtime"
        capability["category"] = "diag"

    elif capabilityId == 247:
        capability["name"] = "prog_03"
        capability["type"] = "progtime"
        capability["category"] = "diag"

    elif capabilityId == 248:
        capability["name"] = "prog_04"
        capability["type"] = "progtime"
        capability["category"] = "diag"

    elif capabilityId == 249:
        capability["name"] = "prog_05"
        capability["type"] = "progtime"
        capability["category"] = "diag"

    elif capabilityId == 250:
        capability["name"] = "prog_06"
        capability["type"] = "progtime"
        capability["category"] = "diag"

    elif capabilityId == 251:
        capability["name"] = "prog_07"
        capability["type"] = "progtime"
        capability["category"] = "diag"

    elif capabilityId == 258:
        capability["name"] = "tank_capacity"
        capability["type"] = "volume"
        capability["category"] = "sensor"

    elif capabilityId == 264:
        capability["name"] = "condenser_temperature"
        capability["type"] = "temperature"
        capability["category"] = "sensor"

    elif capabilityId == 265:
        capability["name"] = "tank_middle_temperature"
        capability["type"] = "temperature"
        capability["category"] = "sensor"

    elif capabilityId == 266:
        capability["name"] = "tank_top_temperature"
        capability["type"] = "temperature"
        capability["category"] = "sensor"

    elif capabilityId == 267:
        capability["name"] = "tank_bottom_temperature"
        capability["type"] = "temperature"
        capability["category"] = "sensor"

    elif capabilityId == 268:
        capability["name"] = "v40_water_available"
        capability["type"] = "volume"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:water-thermometer"

    elif capabilityId == 269:
        capability["name"] = "water_consumption"
        capability["type"] = "water_consumption"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:water-pump"

    elif capabilityId == 270:
        capability["name"] = "v40_water_capacity"
        capability["type"] = "volume"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:water-thermometer"

    elif capabilityId == 271:
        capability["name"] = "hot_water_available"
        capability["type"] = "percentage"
        capability["category"] = "sensor"

    elif capabilityId == 283:
        capability["name"] = "off_peak_hours"
        capability["type"] = "binary"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:clock-outline"

    elif capabilityId == 315:
        capability["name"] = "timezone"
        capability["type"] = "timezone"
        capability["category"] = "diag"
        capability["icon"] = "mdi:map-clock-outline"

    elif capabilityId == 316:
        capability["name"] = "interface_fw"
        capability["type"] = "string"
        capability["category"] = "diag"
        capability["icon"] = "mdi:tag"

    elif capabilityId == 335:
        capability["name"] = "serial_number"
        capability["type"] = "string"
        capability["category"] = "diag"
        capability["icon"] = "mdi:tag"

    elif capabilityId == 100402:
        capability["name"] = "number_of_hours_burner"
        capability["type"] = "int"
        capability["category"] = "diag"
        capability["icon"] = "mdi:fire"

    elif capabilityId == 100406:
        capability["name"] = "number_of_starts_burner"
        capability["type"] = "int"
        capability["category"] = "diag"
        capability["icon"] = "mdi:fire"

    elif capabilityId == 100505:
        # APK: VENTILATION_CURRENT_POWERFUL_MODE — AC's "boost" mode.
        if modelInfos["type"] == CozytouchDeviceType.THERMOSTAT:
            return {}
        capability["name"] = "powerful_mode"
        capability["type"] = "switch"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:wind-power"

    elif capabilityId == 100506:
        # APK: VENTILATION_CURRENT_PRESENCE_DETECTION_MODE.
        # Enum values: 0=COMFORT (presence detection off), 1=PRESENCE_DETECTION (auto).
        # Hidden on TOWEL_RACK (upstream choice) but exposed for THERMOSTAT
        # (electric heaters like the Atlantic DIVALI do support presence detection).
        if modelInfos["type"] == CozytouchDeviceType.TOWEL_RACK:
            capability = {}
        else:
            capability["name"] = "presence_mode"
            capability["type"] = "switch"
            capability["category"] = "sensor"
            capability["icon"] = "mdi:account"

    elif capabilityId == 100507:
        # APK: VENTILATION_CURRENT_ENERGY_SAVING_MODE — AC eco switch.
        # On THERMOSTAT (electric heaters) the eco temperature is expressed via the
        # PROG_ABSENCE / PROG_NIGHT presets (caps 100196 / 100197), not this switch.
        if modelInfos["type"] == CozytouchDeviceType.THERMOSTAT:
            return {}
        capability["name"] = "eco_mode"
        capability["type"] = "switch"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:flower-outline"

    elif capabilityId == 100320:
        capability["name"] = "prog_heat_monday"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100321:
        capability["name"] = "prog_heat_tuesday"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100322:
        capability["name"] = "prog_heat_wednesday"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100323:
        capability["name"] = "prog_heat_thursday"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100324:
        capability["name"] = "prog_heat_friday"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100325:
        capability["name"] = "prog_heat_saturday"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100326:
        capability["name"] = "prog_heat_sunday"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100327:
        capability["name"] = "prog_cool_monday"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100328:
        capability["name"] = "prog_cool_tuesday"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100329:
        capability["name"] = "prog_cool_wednesday"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100330:
        capability["name"] = "prog_cool_thursday"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100331:
        capability["name"] = "prog_cool_friday"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100332:
        capability["name"] = "prog_cool_saturday"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100333:
        capability["name"] = "prog_cool_sunday"
        capability["type"] = "prog"
        capability["category"] = "diag"

    elif capabilityId == 100802:
        # APK: VENTILATION_QUIET_MODE — AC quiet/silent fan setting.
        if modelInfos["type"] == CozytouchDeviceType.THERMOSTAT:
            return {}
        capability["name"] = "quiet_mode"
        capability["type"] = "switch"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:fan-minus"

    elif capabilityId == 100804:
        # APK: VENTILATION_SWING_MODE — AC louver swing on/off.
        if modelInfos["type"] == CozytouchDeviceType.THERMOSTAT:
            return {}
        capability["name"] = "swing_mode"
        capability["type"] = "switch"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:arrow-oscillating"

    elif capabilityId == 104044:
        capability["name"] = "boost_mode"
        capability["type"] = "switch"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:heat-wave"

    elif capabilityId == 104050:
        # APK: VENTILATION_OPEN_WINDOW_DETECTION. Toggle (0/1) for the heater's
        # built-in open-window detection (auto-shutoff on a sudden temp drop).
        # Present on electric heaters in this V2 family (e.g. Atlantic DIVALI).
        capability["name"] = "open_window_detection"
        capability["type"] = "switch"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:window-open-variant"

    elif capabilityId == 104047:
        # Boost timeout max. in minutes
        capability["name"] = "boost_timeout_max"
        capability["type"] = "minutes_adjustment_number"
        capability["category"] = "diag"
        capability["icon"] = "mdi:clock-outline"
        capability["lowest_value"] = 5
        capability["highest_value"] = 60
        capability["step"] = 5

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

    # ---- Cap names decoded from the Cozytouch Android APK (v3.28.0, 2026-05-28) ----
    # Class fr.modulotech.app.domain.model.devices.Capabilities. Caps below appear
    # on V2 electric heaters (e.g. Atlantic DIVALI, Doris, Equateur, Galapagos)
    # and other devices in the same V2 family. See docs/cozytouch.md for the full
    # mapping and value-enum semantics.

    elif capabilityId == 218:
        # WIFI_CONNECTED — enum (0=UNKNOWN, 1=BLINKING, 2=NOT_BLINKING).
        # NOT a boolean — value "0" means "LED state unknown", not "disconnected".
        capability["name"] = "wifi_connected"
        capability["type"] = "string"
        capability["category"] = "diag"
        capability["icon"] = "mdi:wifi"

    elif capabilityId == 100013:
        # THERMOSTAT_MILESTONES_AVAILABLE_TYPES — bitmask of supported milestone
        # types for the weekly schedule (Mon-Sun caps 100334-100341).
        capability["name"] = "milestones_available_types"
        capability["type"] = "string"
        capability["category"] = "diag"
        capability["icon"] = "mdi:format-list-bulleted-type"

    elif capabilityId == 100014:
        # ROOM_TYPE — enum of room categories (bedroom, living, etc.).
        capability["name"] = "room_type"
        capability["type"] = "string"
        capability["category"] = "diag"
        capability["icon"] = "mdi:home-search"

    elif capabilityId == 100022:
        # SYSTEM_OPERATING_SERVICE_SUPPORTED_CAPABILITIES — bitmask (companion to
        # cap 166 which is the "_AVAILABLE_" form).
        capability["name"] = "service_supported_capabilities"
        capability["type"] = "string"
        capability["category"] = "diag"

    elif capabilityId == 100023:
        # SYSTEM_SUPPORTED_MODES_CAPABILITIES — bitmask of supported HVAC modes
        # (companion to cap 217, which is "_AVAILABLE_").
        capability["name"] = "modes_supported_capabilities"
        capability["type"] = "string"
        capability["category"] = "diag"

    elif capabilityId == 100024:
        # VENTILATION_OPTIONS_AVAILABLE — bitmask:
        # 1=TEMPERATURE, 2=OPEN_WINDOW_DETECTION, 4=PRESENCE_DETECTION, 32=ADAPTIVE_PLANNING.
        capability["name"] = "options_available"
        capability["type"] = "string"
        capability["category"] = "diag"

    elif capabilityId == 100196:
        # PROG_ABSENCE — setpoint for the "Absence" lifestyle preset, used by the
        # weekly schedule (state value 2 = UNOCCUPIED). Format: "[temp, mode]".
        capability["name"] = "prog_absence_setpoint"
        capability["type"] = "string"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:home-export-outline"

    elif capabilityId == 100197:
        # PROG_NIGHT — setpoint for the "Night" lifestyle preset (schedule state
        # value 3 = FORCED_OCCUPIED). Format: "[temp, mode]".
        capability["name"] = "prog_night_setpoint"
        capability["type"] = "string"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:weather-night"

    elif capabilityId == 100198:
        # PROG_PRESENCE — setpoint for the "Presence" lifestyle preset (schedule
        # state value 1 = OCCUPIED). Format: "[temp, mode]".
        capability["name"] = "prog_presence_setpoint"
        capability["type"] = "string"
        capability["category"] = "sensor"
        capability["icon"] = "mdi:home-account"

    elif capabilityId == 100334:
        # THERMOSTAT_LIFESTYLE_HEATING_MONDAY — array of [minutesSinceMidnight,
        # LifestyleMilestoneState] where state: 1=OCCUPIED (→ uses PROG_PRESENCE),
        # 2=UNOCCUPIED (→ PROG_ABSENCE), 3=FORCED_OCCUPIED (→ PROG_NIGHT).
        capability["name"] = "lifestyle_schedule_monday"
        capability["type"] = "string"
        capability["category"] = "diag"

    elif capabilityId == 100335:
        capability["name"] = "lifestyle_schedule_tuesday"
        capability["type"] = "string"
        capability["category"] = "diag"

    elif capabilityId == 100336:
        capability["name"] = "lifestyle_schedule_wednesday"
        capability["type"] = "string"
        capability["category"] = "diag"

    elif capabilityId == 100337:
        capability["name"] = "lifestyle_schedule_thursday"
        capability["type"] = "string"
        capability["category"] = "diag"

    elif capabilityId == 100338:
        capability["name"] = "lifestyle_schedule_friday"
        capability["type"] = "string"
        capability["category"] = "diag"

    elif capabilityId == 100339:
        capability["name"] = "lifestyle_schedule_saturday"
        capability["type"] = "string"
        capability["category"] = "diag"

    # Note: capability 100340 is deliberately skipped — Atlantic doesn't use it
    # on this device class. Sunday is on 100341.

    elif capabilityId == 100341:
        capability["name"] = "lifestyle_schedule_sunday"
        capability["type"] = "string"
        capability["category"] = "diag"

    elif capabilityId == 100503:
        # WIFI_SOFTWARE_VERSION — companion firmware string on the HUB
        # (the per-device "interface_fw" is cap 316).
        capability["name"] = "wifi_software_version"
        capability["type"] = "string"
        capability["category"] = "diag"
        capability["icon"] = "mdi:tag"

    # ---- end APK-decoded additions ----

    # For test
    elif capabilityId == 312:
        capability["name"] = "Temp_" + str(capabilityId)
        capability["type"] = "temperature_adjustment_number"
        capability["category"] = "sensor"

    else:
        return None

    return capability
