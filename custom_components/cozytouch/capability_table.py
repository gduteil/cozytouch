"""The capability table : what each id is, on each product.

The mechanism that reads this lives in `capability.py`. Everything here is
data -- one row per capability id, and the tables that say what a descriptor's
number means. Adding a device means adding rows here; see CLAUDE.md.
"""

from collections.abc import Mapping
from dataclasses import dataclass

from homeassistant.const import UnitOfEnergy, UnitOfPower, UnitOfPressure, UnitOfTime

from .const import (
    HVAC_MODE_BITS,
    PROGRAM_BLOCKS,
    SERVICE_VALUES,
    CozytouchCapabilityVariableType,
    program_block,
)
from .infos import (
    CapabilityCategory,
    CapabilityInfos,
    CapabilityType,
    ModelInfos,
    TimestampInfos,
)
from .model import CozytouchDeviceType

# Both report the same ids and mean the same things by them, so the rows that
# differ from the default differ together. See capability.py for why the API
# splits them at all.
ELECTRIC_HEATERS = (CozytouchDeviceType.TOWEL_RACK, CozytouchDeviceType.RADIATOR)

# What the Cozytouch app drags its hot-water cursor between, whichever id the
# tank stores the setpoint in. See docs/decisions.md.
_DHW_USER_TARGET_BOUNDS = {
    "lowestValueCapabilityId": 253,
    "highestValueCapabilityId": 252,
    "step": 1,
}


_CONTROL_MODE_BITS = (
    (1, "basic"),
    (2, "prog"),
    (4, "lifestyle_prog"),
    (8, "heating_anticipation"),
    (16, "unexpected_events"),
    (32, "auto"),
    (256, "energy_saving"),
    (1024, "absence"),
    (2048, "scheduled_absence"),
)

_DHW_MODE_BITS = (
    (1, "manual"),
    (2, "eco_comfort_schedule"),
    (4, "auto"),
    (8, "prog"),
    (256, "boost"),
    (512, "scheduled_boost"),
    (1024, "absence"),
    (2048, "scheduled_absence"),
    (4096, "antilegionella"),
    (8192, "smart_grid"),
    (16384, "on_off"),
)

_DHW_HEATING_TYPE_BITS = (
    (1, "heat"),
    (2, "scheduled_heat"),
    (4, "off_peak_heat"),
    (8, "self_consumption_heat"),
)

_AIR_CIRCULATION_MODE_BITS = (
    (1, "off"),
    (2, "auto_temperature"),
    (4, "auto_season"),
    (8, "cool"),
    (16, "heat"),
    (128, "fan"),
    (256, "dry"),
)

_VENTILATION_OPTION_BITS = (
    (1, "temperature"),
    (2, "open_window_detection"),
    (4, "presence_detection"),
    (32, "adaptive_planning"),
)

_VENTILATION_CONTROL_BITS = (
    (1, "temperature"),
    (2, "hygrometry"),
    (4, "emergency_temperature"),
    (8, "powerful_mode"),
    (16, "boost_with_fan"),
    (32, "boost_without_fan"),
    (64, "horizontal_blade_position"),
    (128, "vertical_blade_position"),
)

# The speed selectors name a whole set rather than one speed, so each value
# spells its set out. A third mechanism next to the two tables above, and the
# app's own: `buildListFromValue`. See docs/decisions.md.
_SPEED_SETS = {
    "0": "low, medium, high",
    "1": "low, high",
    "2": "low, medium, high, auto",
    "3": "low, high, auto",
    "4": "auto",
}


def hidden_by_a_calendar(capabilityId: int, availableCapabilityIds: set[int]) -> bool:
    """Whether this id is a program day whose whole block the device reports.

    All seven days is the calendar platform's condition for building one, so it
    is also the condition for the per-day sensors arriving disabled: a device
    with a partial block has no calendar, and its per-day sensors stay its only
    view. See docs/decisions.md.

    Which ids are program days is not declared on the rows -- PROGRAM_BLOCKS
    says where each block starts, and a row repeating that would be a number to
    keep in step by hand.
    """
    return any(
        capabilityId in program_block(first)
        and all(day in availableCapabilityIds for day in program_block(first))
        for firsts in PROGRAM_BLOCKS.values()
        for first in firsts
    )


@dataclass(frozen=True, kw_only=True, slots=True)
class Entity:
    """What a capability becomes when the id alone decides it.

    Most of the mapping is this : a name, a type, and which category the
    entity lands in. `CAPABILITIES` below is the answer to "what is id N", and
    the chain in `get_capability_infos` is the ids that need more than an
    answer -- the ones that read the model, the value, or another capability.

    Fields are keyword-only : a row reading Entity("x", "y") tells the next
    reader nothing about what x and y are.

    name    the entity name and its translation key, so a new one needs an
            entry in strings.json and in every file under translations/.
    type    the platform that builds it. Only claim one whose unit is known.
    enabled_by_default
            has no default on purpose : every row states it, so whether an
            entity shows up on a device page is answered by reading the row
            rather than by knowing what the field falls back to.
    bits    the value is a *sum*: one number saying several things at once.
            166 reading 411 is 1+2+4+16+128+256, so the unit does off, auto,
            cool, heat, fan and dry. The question it answers is "which of
            these can I do".
    reads_as
            the value is looked up whole. Usually that is an enum -- 73
            reading 4 is the fourth member, cooling_and_heating -- but not
            always: 350 reading 2 is "low, medium, high, auto", four speeds
            named by one number. Hence reads_as and not values, which would
            promise a member every time.

            At most one of the two, and the choice is not cosmetic: 4 read as
            a sum is the third flag, looked up whole it is the fourth member,
            and both readings look perfectly sensible. Only the id says which,
            which is why a row setting both fails a test. The way to tell them
            apart is whether the device can report two of these at once.
    extra   the remaining keys a platform reads off a capability -- the bounds
            of a number, a step, a modelList. Spelled out rather than given
            fields of their own, because each is read by one platform only.

    The last four say the same id does not mean the same thing on every
    product, which is why this is a table of rows rather than of strings.
    All four key on what a device *is*, never on which model id it carries :
    the vendor's own app dispatches on the device class, and a row keyed on
    an id is a list that grows by one with every report. See
    docs/decisions.md.

    absent_on   device types with no such entity at all.
    needs_flag  a flag from model.py that has to hold for the entity to exist.
                A model that does not mention it is taken to have it.
    per_type    the keys to merge in last, for the device types named in the
                key -- a tuple, like absent_on, so two products reading an id
                the same way say so once.
    valid_above the entity exists only while the value is above this. Atlantic
                sends a far-out-of-range reading rather than nothing when a
                probe has nothing to say.
    """

    name: str
    type: CapabilityType
    category: CapabilityCategory = CapabilityCategory.SENSOR
    icon: str | None = None
    enabled_by_default: bool
    bits: tuple[tuple[int, str], ...] | None = None
    reads_as: Mapping[str, str] | None = None
    extra: Mapping[str, object] | None = None
    absent_on: tuple[CozytouchDeviceType, ...] = ()
    needs_flag: str | None = None
    per_type: Mapping[tuple[CozytouchDeviceType, ...], Mapping[str, object]] | None = (
        None
    )
    valid_above: float | None = None

    def resolve(
        self, capability: CapabilityInfos, modelInfos: ModelInfos, value: str = "0"
    ) -> CapabilityInfos:
        """Fill the capability in, or hand back an empty one where it does not exist."""
        if modelInfos.type in self.absent_on:
            return CapabilityInfos()
        if self.needs_flag and not modelInfos.get(self.needs_flag, True):
            return CapabilityInfos()
        if self.valid_above is not None and float(value) <= self.valid_above:
            return CapabilityInfos()

        capability.name = self.name
        capability.type = self.type
        capability.category = self.category
        if self.icon is not None:
            capability.icon = self.icon
        if not self.enabled_by_default:
            capability.enabled_by_default = False
        overrides = [self.extra]
        overrides += [
            override
            for deviceTypes, override in (self.per_type or {}).items()
            if modelInfos.type in deviceTypes
        ]
        for source in overrides:
            for key, setting in (source or {}).items():
                capability[key] = setting
        return capability


# The two ends of the away window, which arrive as one comma-separated value.
AWAY_MODE_TIMESTAMPS = (
    TimestampInfos("away_mode_start", "mdi:airplane-takeoff"),
    TimestampInfos("away_mode_stop", "mdi:airplane-landing"),
)

# Ids the mapping deliberately drops: reported, understood, and not wanted as
# an entity of their own.
SUPPRESSED_CAPABILITIES: frozenset[int] = frozenset()


_AVAILABILITY = {"0": "unavailable", "1": "available"}
_ACTIVITY = {"0": "inactive", "1": "active"}
_OFF_ON = {"0": "off", "1": "on"}
# The vendor writes an unknown reading as three dashes, and in two of these
# tables it is the zero rather than the last member.
_VALVE = {"0": "off", "1": "opening", "2": "closing", "3": "unknown"}
# The vendor writes an unknown circulator reading as three dashes, and puts it
# on the zero rather than at the end.
# What a thermal generator can be, as a sum. 103026 answers it for a room and
# 359 for a device, with the same members; the vendor's `Reserved` on bit 1 is
# left out because naming a reserved bit promises it means something.
_THERMAL_GENERATOR_BITS = (
    (2, "air_to_water_heat_pump"),
    (4, "boiler"),
    (8, "air_to_air_split_heat_pump"),
    (16, "electric_panel_heater"),
    (32, "electric_towel_dryer"),
    (64, "electric_floor_heater"),
    (128, "electric_panel_heater_i2g"),
    (256, "electric_towel_dryer_i2g"),
)

_CIRCULATOR = {"0": "unknown", "1": "off", "2": "on"}

_PROFILE = {
    "0": "stop",
    "1": "comfort",
    "2": "eco",
    "3": "external_setpoint",
    "4": "absence",
    "5": "manual",
    "6": "frost_protection",
    "7": "derogation",
}

CAPABILITIES: dict[int, Entity] = {
    3: Entity(
        name="dhw_profile",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as=_PROFILE,
    ),
    4: Entity(
        name="cooling_profile_z1",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as=_PROFILE,
    ),
    5: Entity(
        name="cooling_profile_z2",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as=_PROFILE,
    ),
    6: Entity(
        name="generator_error_code",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    7: Entity(
        # The climate entity is built from this id by _climate_entity, which
        # runs first; the row is what lets the raw reading beside it read as a
        # word instead of a number.
        name="air_conditioner",
        type=CapabilityType.CLIMATE,
        enabled_by_default=True,
        icon="mdi:air-conditioner",
        reads_as=SERVICE_VALUES,
    ),
    9: Entity(
        name="extra_heating_power_z2",
        type=CapabilityType.POWER,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    11: Entity(
        name="extra_dhw_power",
        type=CapabilityType.POWER,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    15: Entity(
        name="dhw_service_type",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "instantaneous",
            "1": "semi_accumulated",
            "2": "accumulated",
        },
    ),
    16: Entity(
        name="dhw_available",
        type=CapabilityType.BINARY,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    17: Entity(
        # The setpoint actually in force, which is not always the one that was
        # asked for: 40 is what somebody set, this is what the program or an
        # override left running. A heat pump steers its first zone on this id,
        # and there _climate_entity claims it before this row is reached.
        name="control_setpoint",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    18: Entity(
        # Room 2's setpoint in force, as 17 is room 1's. A heat pump steers its
        # second zone on this id and the climate entity claims it there first,
        # so the row surfaces only where it is reported without being steered.
        name="control_setpoint_z2",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    19: Entity(
        name="temperature_setpoint",
        type=CapabilityType.TEMPERATURE,
        enabled_by_default=True,
    ),
    20: Entity(
        name="temperature_setpoint_z2",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    21: Entity(
        name="emergency_mode",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "inactive",
            "1": "active",
            "2": "heat_pump_locked",
            "3": "boiler_locked",
        },
    ),
    22: Entity(
        # 160/161 are the room's bounds, and a tank that reports its own
        # answers on 253/252. See docs/decisions.md.
        name="target_temperature_dhw",
        type=CapabilityType.TEMPERATURE_ADJUSTMENT_NUMBER,
        enabled_by_default=True,
        extra={"lowestValueCapabilityId": 160, "highestValueCapabilityId": 161},
        per_type={(CozytouchDeviceType.WATER_HEATER,): _DHW_USER_TARGET_BOUNDS},
    ),
    23: Entity(
        name="dhw_comfort_setpoint",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    24: Entity(
        name="compressor_starts",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    25: Entity(
        name="number_of_starts_ch_pump",
        type=CapabilityType.INT,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
        icon="mdi:water-pump",
    ),
    26: Entity(
        name="number_of_starts_dhw_pump",
        type=CapabilityType.INT,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
        icon="mdi:water-pump",
    ),
    27: Entity(
        name="compressor_running_time",
        type=CapabilityType.TIME,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        extra={"displayed_unit_of_measurement": UnitOfTime.SECONDS},
    ),
    28: Entity(
        name="number_of_hours_ch_pump",
        type=CapabilityType.INT,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
        icon="mdi:water-pump",
    ),
    29: Entity(
        name="number_of_hours_dhw_pump",
        type=CapabilityType.INT,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
        icon="mdi:water-pump",
    ),
    30: Entity(
        name="external_input_1_function",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "smart_grid",
            "1": "ejp_tariff",
            "2": "external_control",
        },
    ),
    31: Entity(
        name="external_input_2_function",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "off_peak_hours",
            "1": "smart_grid",
        },
    ),
    36: Entity(
        name="external_input_1",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as=_ACTIVITY,
    ),
    37: Entity(
        name="external_input_2",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as=_ACTIVITY,
    ),
    38: Entity(
        name="external_input_3",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as=_ACTIVITY,
    ),
    39: Entity(
        name="dhw_eco_setpoint",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    40: Entity(
        name="target_temperature",
        type=CapabilityType.TEMPERATURE_ADJUSTMENT_NUMBER,
        enabled_by_default=True,
        extra={
            "lowestValueCapabilityId": 160,
            "highestValueCapabilityId": 161,
        },
    ),
    41: Entity(
        name="target_temperature_eco_z1",
        type=CapabilityType.TEMPERATURE_ADJUSTMENT_NUMBER,
        enabled_by_default=True,
        extra={
            "lowestValueCapabilityId": 160,
            "highestValueCapabilityId": 161,
        },
    ),
    42: Entity(
        name="target_temperature_comfort_z2",
        type=CapabilityType.TEMPERATURE_ADJUSTMENT_NUMBER,
        enabled_by_default=True,
        extra={
            "lowestValueCapabilityId": 160,
            "highestValueCapabilityId": 161,
        },
    ),
    43: Entity(
        name="target_temperature_eco_z2",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    44: Entity(
        name="ch_power_consumption",
        type=CapabilityType.ENERGY,
        enabled_by_default=True,
        icon="mdi:radiator",
        extra={
            "displayed_unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        },
    ),
    45: Entity(
        name="dhw_power_consumption",
        type=CapabilityType.ENERGY,
        enabled_by_default=True,
        icon="mdi:faucet",
        extra={
            "displayed_unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        },
    ),
    46: Entity(
        name="total_power_consumption",
        type=CapabilityType.ENERGY,
        enabled_by_default=True,
        icon="mdi:water-boiler",
        extra={
            "displayed_unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        },
    ),
    47: Entity(
        # µA, which Home Assistant only gained after the version hacs.json
        # declares, so this is a plain reading until the floor moves. See
        # docs/decisions.md.
        name="generator_burner_flame",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    48: Entity(
        name="dhw_current_flow",
        type=CapabilityType.FLOW_RATE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    49: Entity(
        name="generator_flame_status",
        type=CapabilityType.BINARY,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    50: Entity(
        name="generator_modulation_level",
        type=CapabilityType.PERCENTAGE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    51: Entity(
        name="compressor",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as=_OFF_ON,
    ),
    52: Entity(
        name="circulator_z1",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as=_CIRCULATOR,
    ),
    53: Entity(
        name="circulator_z2",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as=_CIRCULATOR,
    ),
    56: Entity(
        name="mixing_valve_z1",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as=_VALVE,
    ),
    57: Entity(
        name="power_consumption",
        type=CapabilityType.ENERGY,
        enabled_by_default=True,
        extra={
            "displayed_unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        },
    ),
    58: Entity(
        name="cooling_power_consumption",
        type=CapabilityType.ENERGY,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        extra={"displayed_unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR},
    ),
    59: Entity(
        name="power_consumption",
        type=CapabilityType.ENERGY,
        enabled_by_default=True,
        extra={
            "displayed_unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR,
        },
    ),
    60: Entity(
        name="total_electricity_consumption",
        type=CapabilityType.ENERGY,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        extra={"displayed_unit_of_measurement": UnitOfEnergy.KILO_WATT_HOUR},
    ),
    61: Entity(
        name="fuel_heating_consumption",
        type=CapabilityType.VOLUME,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    62: Entity(
        name="fuel_dhw_consumption",
        type=CapabilityType.VOLUME,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    63: Entity(
        name="fuel_total_consumption",
        type=CapabilityType.VOLUME,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    64: Entity(
        name="dhw_extra_electric_heater",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as=_OFF_ON,
    ),
    65: Entity(
        name="fan_status",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "off",
            "1": "on",
        },
    ),
    66: Entity(
        name="dhw_circulator_status",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "off",
            "1": "on",
        },
    ),
    67: Entity(
        name="generator_flow_from_burner_pump",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    68: Entity(
        name="extra_electric_stage_1",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "unknown",
            "1": "modulating",
            "2": "off",
            "3": "on",
        },
    ),
    69: Entity(
        name="directional_valve",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "unknown",
            "1": "off",
            "2": "on",
        },
    ),
    70: Entity(
        name="extra_electric_stage_2",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "unknown",
            "1": "off",
            "2": "on",
        },
    ),
    71: Entity(
        name="boiler_contact",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "unknown",
            "1": "off",
            "2": "on",
        },
    ),
    72: Entity(
        name="compressor_modulation",
        type=CapabilityType.PERCENTAGE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    73: Entity(
        name="available_thermostat_modes",
        type=CapabilityType.STRING,
        reads_as={
            "0": "cooling_only",
            "1": "cooling_with_reheat",
            "2": "heating_only",
            "3": "heating_with_reheat",
            "4": "cooling_and_heating",
            "5": "cooling_and_heating_with_reheat",
        },
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    74: Entity(
        name="available_thermostat_modes_z2",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "cooling_only",
            "1": "cooling_with_reheat",
            "2": "heating_only",
            "3": "heating_with_reheat",
            "4": "cooling_and_heating",
            "5": "cooling_and_heating_with_reheat",
        },
    ),
    75: Entity(
        name="ambient_compensation_z1",
        type=CapabilityType.PERCENTAGE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    76: Entity(
        name="ambient_compensation_z2",
        type=CapabilityType.PERCENTAGE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    77: Entity(
        name="outside_compensation_slope_z1",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    78: Entity(
        name="outside_compensation_offset_z1",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    79: Entity(
        name="outside_compensation_slope_z2",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    81: Entity(
        name="outside_compensation_offset_z2",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    82: Entity(
        name="heating_cooling_switch_temperature",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    83: Entity(
        name="simulated_outside_temperature",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    86: Entity(
        name="domestic_hot_water",
        type=CapabilityType.SWITCH,
        enabled_by_default=True,
        icon="mdi:faucet",
    ),
    87: Entity(
        name="domestic_hot_water_mode",
        type=CapabilityType.SELECT,
        enabled_by_default=True,
        icon="mdi:water-boiler",
        extra={
            "modelList": "HeatingModes",
        },
    ),
    88: Entity(
        name="model_name",
        type=CapabilityType.STRING,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
        icon="mdi:tag",
    ),
    89: Entity(
        name="generator_heating_successful_burner_starts",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    90: Entity(
        name="generator_dhw_burner_starts",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    91: Entity(
        # the 3-way valve; see docs/decisions.md
        name="active_circuit",
        type=CapabilityType.STRING,
        icon="mdi:valve",
        reads_as={
            "1": "heating",
            "3": "domestic_hot_water",
        },
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    92: Entity(
        name="generator_hours_flame_too_low",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    93: Entity(
        name="zones_count",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    94: Entity(
        name="product_number",
        type=CapabilityType.STRING,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
        icon="mdi:tag",
    ),
    96: Entity(
        name="target_temperature_comfort_cool_z1",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    97: Entity(
        name="target_temperature_eco_cool_z1",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    98: Entity(
        name="product_number",
        type=CapabilityType.STRING,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
        icon="mdi:tag",
    ),
    99: Entity(
        name="dhw_pump",
        type=CapabilityType.BINARY,
        enabled_by_default=True,
        icon="mdi:faucet",
        per_type={
            (CozytouchDeviceType.WATER_HEATER,): {
                "name": "resistance",
                "icon": "mdi:radiator",
            }
        },
    ),
    100: Entity(
        name="water_pressure",
        type=CapabilityType.PRESSURE,
        enabled_by_default=True,
        icon="mdi:gauge",
        extra={
            "displayed_unit_of_measurement": UnitOfPressure.BAR,
        },
    ),
    101: Entity(
        name="Capability_101",
        type=CapabilityType.STRING,
        enabled_by_default=True,
        extra={"value_type": CozytouchCapabilityVariableType.ARRAY},
    ),
    102: Entity(
        name="Capability_102",
        type=CapabilityType.STRING,
        enabled_by_default=True,
        extra={"value_type": CozytouchCapabilityVariableType.ARRAY},
    ),
    103: Entity(
        name="Capability_103",
        type=CapabilityType.STRING,
        enabled_by_default=True,
        extra={"value_type": CozytouchCapabilityVariableType.ARRAY},
    ),
    104: Entity(
        name="Capability_104",
        type=CapabilityType.STRING,
        enabled_by_default=True,
        extra={"value_type": CozytouchCapabilityVariableType.ARRAY},
    ),
    106: Entity(
        name="nominal_heating_power",
        type=CapabilityType.POWER,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    107: Entity(
        name="nominal_dhw_power",
        type=CapabilityType.POWER,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    109: Entity(
        name="boiler_water_temperature",
        type=CapabilityType.TEMPERATURE,
        enabled_by_default=True,
    ),
    110: Entity(
        name="boiler_water_temperature_z2",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    111: Entity(
        name="dhw_temperature",
        type=CapabilityType.TEMPERATURE,
        enabled_by_default=True,
    ),
    112: Entity(
        name="circulator_flow_rate",
        type=CapabilityType.FLOW_RATE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    113: Entity(
        name="target_temperature_comfort_cool_z2",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    114: Entity(
        name="target_temperature_eco_cool_z2",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    116: Entity(
        name="exhaust_temperature",
        type=CapabilityType.TEMPERATURE,
        enabled_by_default=True,
        needs_flag="exhaustTemperatureAvailable",
    ),
    117: Entity(
        name="thermostat_temperature_z1",
        type=CapabilityType.TEMPERATURE,
        enabled_by_default=True,
    ),
    118: Entity(
        name="thermostat_temperature_z2",
        type=CapabilityType.TEMPERATURE,
        enabled_by_default=True,
    ),
    119: Entity(
        # Atlantic sends -327.68 rather than nothing when there is no probe.
        name="outside_temperature",
        type=CapabilityType.TEMPERATURE,
        enabled_by_default=True,
        valid_above=-327.68,
    ),
    120: Entity(
        # Atlantic calls it ProductType, and it answers for the whole range
        # rather than the two things the old name offered. See
        # docs/decisions.md.
        name="product_type",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "accumulation_domestic_hot_water",
            "1": "air_conditioning",
            "2": "boiler",
            "3": "convector",
            "4": "double_flow_ventilation",
            "5": "heat_pump",
            "6": "heater",
            "7": "hybrid",
            "8": "single_flow_ventilation",
            "9": "thermodynamic_domestic_hot_water",
            "10": "zone_controller",
            "11": "undefined",
        },
    ),
    121: Entity(
        name="version",
        type=CapabilityType.STRING,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
        icon="mdi:tag",
    ),
    147: Entity(
        name="mixing_valve_z2",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as=_VALVE,
    ),
    148: Entity(
        name="away_period_start",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    149: Entity(
        name="away_period_end",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    150: Entity(
        name="home_error_code",
        type=CapabilityType.ERROR_CODE,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
        icon="mdi:alert-circle-outline",
    ),
    152: Entity(
        name="away_mode",
        type=CapabilityType.AWAY_MODE_SWITCH,
        enabled_by_default=True,
        icon="mdi:airplane",
        extra={
            "value_off": "0",
            "value_on": "1",
            "value_pending": "2",
            "timestampsCapabilityId": 222,
        },
    ),
    153: Entity(
        # Three states, not two: the app reads it as HeatingStatus { OFF,
        # HEAT_UP, COOL_DOWN } and never gives it a label of its own. See
        # docs/decisions.md.
        name="heating_status",
        type=CapabilityType.STRING,
        enabled_by_default=False,
        icon="mdi:heat-wave",
        reads_as={"0": "off", "1": "heating", "2": "cooling"},
    ),
    154: Entity(
        name="zone_1",
        type=CapabilityType.STRING,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
        icon="mdi:home-floor-1",
    ),
    155: Entity(
        name="zone_2",
        type=CapabilityType.STRING,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
        icon="mdi:home-floor-2",
    ),
    157: Entity(
        name="override_setpoint_activation",
        type=CapabilityType.BINARY,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    158: Entity(
        # An hour at a time, from one to twenty-four, which is the grid the
        # Cozytouch app offers. See docs/decisions.md.
        name="override_total_time_z1",
        type=CapabilityType.DURATION_SELECT,
        enabled_by_default=True,
        icon="mdi:clock-outline",
        extra={"lowest_value": 60, "highest_value": 1440, "step": 60},
        per_type={ELECTRIC_HEATERS: {"name": "override_total_time"}},
    ),
    159: Entity(
        name="override_remain_time_z1",
        type=CapabilityType.TIME,
        enabled_by_default=True,
        icon="mdi:clock-outline",
        per_type={ELECTRIC_HEATERS: {"name": "override_remain_time"}},
    ),
    160: Entity(
        name="temperature_adjustment_min",
        type=CapabilityType.TEMPERATURE,
        enabled_by_default=False,
        category=CapabilityCategory.DIAG,
        icon="mdi:thermometer-chevron-down",
    ),
    161: Entity(
        name="temperature_adjustment_max",
        type=CapabilityType.TEMPERATURE,
        enabled_by_default=False,
        category=CapabilityCategory.DIAG,
        icon="mdi:thermometer-chevron-up",
    ),
    162: Entity(
        # The cooling counterpart of the 160/161 heating bounds. Two independent
        # reverse-engineering efforts name these the same way, so the unit is
        # not a guess -- but nothing reads them yet. Wiring them as the climate
        # entity's min and max while cooling is a separate change.
        name="cooling_temperature_min",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    163: Entity(
        name="cooling_temperature_max",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    164: Entity(
        name="energy_consumption_supported",
        type=CapabilityType.STRING,
        bits=(
            (1, "gas_heating"),
            (2, "electricity_heating"),
            (4, "electricity_cooling"),
            (8, "gas_dhw"),
            (16, "electricity_dhw"),
            (32, "fuel_heating"),
            (64, "fuel_dhw"),
            (256, "heating_production"),
            (512, "cooling_production"),
            (1024, "dhw_production"),
        ),
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    165: Entity(
        # water-boiler icon: a domestic-hot-water boost, not the generic boost.
        name="domestic_hot_water_boost",
        type=CapabilityType.SWITCH,
        enabled_by_default=True,
        icon="mdi:water-boiler",
        per_type={
            (CozytouchDeviceType.HEAT_PUMP,): {"value_off": "false", "value_on": "true"}
        },
    ),
    166: Entity(
        name="system_operating_mode",
        type=CapabilityType.STRING,
        bits=HVAC_MODE_BITS,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    168: Entity(
        name="available_dhw_modes",
        type=CapabilityType.STRING,
        bits=_DHW_MODE_BITS,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    169: Entity(
        name="radio_signal",
        type=CapabilityType.PERCENTAGE,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
        icon="mdi:radio-tower",
    ),
    170: Entity(
        name="signal_quality",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "good",
            "1": "normal",
            "2": "low",
            "3": "very_low",
        },
    ),
    171: Entity(
        # The cooling half of the absence setpoint, 172 being the heating one.
        # Read-only where 172 is a number. See docs/decisions.md.
        name="away_mode_cooling_temperature",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        needs_flag="awayModeTemperatureAvailable",
        enabled_by_default=False,
    ),
    172: Entity(
        # Absence setpoint. Only the heating products act on it. An air
        # conditioner reports it and stores what is written, but never reads it
        # back: absence there stops the units until the return date, and the
        # weekly program keeps driving 40 and 177 throughout. Exposing a number
        # nothing honours would promise a setting the Cozytouch app does not
        # even offer on this hardware.
        name="away_mode_temperature",
        type=CapabilityType.TEMPERATURE_ADJUSTMENT_NUMBER,
        enabled_by_default=True,
        needs_flag="awayModeTemperatureAvailable",
        extra={"lowestValueCapabilityId": 160, "highestValueCapabilityId": 161},
    ),
    176: Entity(
        name="heating_schedule_available_z1",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as=_AVAILABILITY,
    ),
    177: Entity(
        name="target_cool_temperature",
        type=CapabilityType.TEMPERATURE_ADJUSTMENT_NUMBER,
        enabled_by_default=True,
        absent_on=(CozytouchDeviceType.GAZ_BOILER,),
        extra={"lowestValueCapabilityId": 162, "highestValueCapabilityId": 163},
    ),
    178: Entity(
        name="target_temperature_cool_z2",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    179: Entity(
        name="wifi_signal",
        type=CapabilityType.SIGNAL,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
        icon="mdi:wifi",
    ),
    180: Entity(
        name="outdoor_unit_error_code",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    181: Entity(
        # The service actually running, against the one 7 asked for. Diag and
        # off by default: it is the answer to "is it doing what I told it",
        # which nobody needs until they are asking.
        name="service_in_progress",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        icon="mdi:air-conditioner",
        reads_as=SERVICE_VALUES,
    ),
    182: Entity(
        name="home_active_errors",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    183: Entity(
        name="room_active_errors",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    184: Entity(
        name="prog_mode",
        type=CapabilityType.SWITCH,
        enabled_by_default=True,
        icon="mdi:clock-outline",
    ),
    185: Entity(
        name="prog_mode_z2",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "basic",
            "1": "prog",
            "2": "auto",
            "4": "prog_off",
        },
    ),
    186: Entity(
        name="override_setpoint_activation_z2",
        type=CapabilityType.BINARY,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    187: Entity(
        name="override_remain_time_z2",
        type=CapabilityType.TIME,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    188: Entity(
        name="home_services",
        type=CapabilityType.STRING,
        bits=(
            (1, "thermal_comfort"),
            (2, "dhw"),
            (4, "ventilation"),
            (8, "light"),
            (256, "away"),
        ),
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    189: Entity(
        name="heating_schedule_available_z2",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as=_AVAILABILITY,
    ),
    190: Entity(
        name="cooling_schedule_available_z1",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as=_AVAILABILITY,
    ),
    191: Entity(
        name="cooling_schedule_available_z2",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as=_AVAILABILITY,
    ),
    192: Entity(
        name="flow_temperature_at_minus_ten",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    193: Entity(
        name="flow_temperature_at_twenty",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    194: Entity(
        name="cooling_flow_temperature_at_thirty_five",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    195: Entity(
        name="cooling_flow_temperature_at_twenty_five",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    196: Entity(
        name="prog_heating_monday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    197: Entity(
        name="prog_heating_tuesday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    198: Entity(
        name="prog_heating_wednesday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    199: Entity(
        name="prog_heating_thursday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    200: Entity(
        name="prog_heating_friday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    201: Entity(
        name="prog_heating_saturday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    202: Entity(
        name="prog_heating_sunday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    203: Entity(
        name="prog_cooling_monday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    204: Entity(
        name="prog_cooling_tuesday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    205: Entity(
        name="prog_cooling_wednesday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    206: Entity(
        name="prog_cooling_thursday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    207: Entity(
        name="prog_cooling_friday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    208: Entity(
        name="prog_cooling_saturday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    209: Entity(
        name="prog_cooling_sunday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    210: Entity(
        name="dhw_comfort_schedule_monday",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    211: Entity(
        name="dhw_comfort_schedule_tuesday",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    212: Entity(
        name="dhw_comfort_schedule_wednesday",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    213: Entity(
        name="dhw_comfort_schedule_thursday",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    214: Entity(
        name="dhw_comfort_schedule_friday",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    215: Entity(
        name="dhw_comfort_schedule_saturday",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    216: Entity(
        name="dhw_comfort_schedule_sunday",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    217: Entity(
        name="system_setpoint_mode",
        type=CapabilityType.STRING,
        bits=_CONTROL_MODE_BITS,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    218: Entity(
        # Not a wifi flag and never was: Atlantic calls it
        # ConnectivityDiagnosis and publishes the seven codes it answers. A
        # zone gets nothing at all, having no readings to go with it. See
        # docs/decisions.md.
        name="connectivity_diagnosis",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        icon="mdi:lan-connect",
        absent_on=(CozytouchDeviceType.ZONE,),
        reads_as={
            "0": "ok",
            "1": "product_unreachable_from_bridge",
            "2": "bridge_offline",
            "3": "product_unreachable_from_interface",
            "4": "interface_offline",
            "5": "cloud_issue",
            "6": "maintenance",
        },
        enabled_by_default=False,
    ),
    219: Entity(
        name="wifi_ssid",
        type=CapabilityType.STRING,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
        icon="mdi:wifi",
    ),
    220: Entity(
        name="adjusted_heat_setpoint",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    221: Entity(
        name="heat_cool_request",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "off",
            "1": "heat",
            "2": "cool",
        },
    ),
    222: Entity(
        name="away_mode",
        type=CapabilityType.AWAY_MODE_TIMESTAMPS,
        enabled_by_default=True,
        extra={
            "timestamps": AWAY_MODE_TIMESTAMPS,
            "timezoneCapabilityId": 315,
            "capabilityDuplicate": 226,
        },
    ),
    223: Entity(
        name="dhw_system_operating_mode",
        type=CapabilityType.STRING,
        bits=_DHW_HEATING_TYPE_BITS,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    224: Entity(
        name="dhw_estimation_supported",
        type=CapabilityType.STRING,
        bits=(
            (1, "water_temperature"),
            (2, "water_flow"),
            (4, "cold_water_temperature"),
            (8, "hot_water_temperature"),
            (16, "tank_v40"),
            (32, "tank_energy"),
            (64, "tank_power"),
        ),
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    226: Entity(
        name="away_mode",
        type=CapabilityType.AWAY_MODE_TIMESTAMPS,
        enabled_by_default=True,
        extra={
            "timestamps": AWAY_MODE_TIMESTAMPS,
            "timezoneCapabilityId": 315,
            "capabilityDuplicate": 222,
        },
    ),
    227: Entity(
        name="away_mode",
        type=CapabilityType.AWAY_MODE_SWITCH,
        enabled_by_default=True,
        icon="mdi:airplane",
        extra={
            "value_off": "0",
            "value_on": "1",
            "value_pending": "2",
            "timestampsCapabilityId": 226,
        },
    ),
    228: Entity(
        name="absence_dhw_temperature",
        type=CapabilityType.TEMPERATURE,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    230: Entity(
        name="dhw_operating_mode",
        type=CapabilityType.STRING,
        reads_as={
            "0": "heat",
            "1": "scheduled_heat",
            "2": "off_peak_heat",
        },
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    231: Entity(
        name="target_temperature",
        type=CapabilityType.TEMPERATURE_ADJUSTMENT_NUMBER,
        enabled_by_default=True,
        extra={
            "lowestValueCapabilityId": 105301,
            "highestValueCapabilityId": 105304,
        },
        per_type={(CozytouchDeviceType.WATER_HEATER,): _DHW_USER_TARGET_BOUNDS},
    ),
    232: Entity(
        name="boost_total_time",
        type=CapabilityType.TIME,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
        icon="mdi:clock-outline",
    ),
    233: Entity(
        name="boost_remaining_time",
        type=CapabilityType.TIME,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
        icon="mdi:clock-outline",
    ),
    234: Entity(
        name="boost_target_temperature",
        type=CapabilityType.TEMPERATURE,
        enabled_by_default=True,
        icon="mdi:thermometer-high",
    ),
    236: Entity(
        name="max_dhw_schedule_slots_per_day",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    237: Entity(
        name="dhw_prog_monday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    238: Entity(
        name="dhw_prog_tuesday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    239: Entity(
        name="dhw_prog_wednesday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    240: Entity(
        name="dhw_prog_thursday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    241: Entity(
        name="dhw_prog_friday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    242: Entity(
        name="dhw_prog_saturday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    243: Entity(
        name="dhw_prog_sunday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    244: Entity(
        name="max_schedule_ranges_per_day",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    245: Entity(
        name="prog_01",
        type=CapabilityType.PROGTIME,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    246: Entity(
        name="prog_02",
        type=CapabilityType.PROGTIME,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    247: Entity(
        name="prog_03",
        type=CapabilityType.PROGTIME,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    248: Entity(
        name="prog_04",
        type=CapabilityType.PROGTIME,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    249: Entity(
        name="prog_05",
        type=CapabilityType.PROGTIME,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    250: Entity(
        name="prog_06",
        type=CapabilityType.PROGTIME,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    251: Entity(
        name="prog_07",
        type=CapabilityType.PROGTIME,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    252: Entity(
        name="target_temperature_max",
        type=CapabilityType.TEMPERATURE,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    253: Entity(
        name="target_temperature_min",
        type=CapabilityType.TEMPERATURE,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    254: Entity(
        name="dhw_setpoint_without_override",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    256: Entity(
        name="dhw_heat_hot_water_status",
        type=CapabilityType.BINARY,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    258: Entity(
        name="tank_capacity",
        type=CapabilityType.VOLUME,
        enabled_by_default=True,
    ),
    264: Entity(
        # Atlantic's own list, and the corpus agrees : 264 < 267 < 266. See
        # docs/decisions.md.
        name="tank_bottom_temperature",
        type=CapabilityType.TEMPERATURE,
        enabled_by_default=True,
    ),
    265: Entity(
        name="tank_middle_temperature",
        type=CapabilityType.TEMPERATURE,
        enabled_by_default=True,
    ),
    266: Entity(
        name="tank_top_temperature",
        type=CapabilityType.TEMPERATURE,
        enabled_by_default=True,
    ),
    267: Entity(
        name="tank_average_temperature",
        type=CapabilityType.TEMPERATURE,
        enabled_by_default=True,
    ),
    268: Entity(
        name="v40_water_available",
        type=CapabilityType.VOLUME,
        enabled_by_default=True,
        icon="mdi:water-thermometer",
    ),
    269: Entity(
        name="water_consumption",
        type=CapabilityType.WATER_CONSUMPTION,
        enabled_by_default=True,
        icon="mdi:water-pump",
    ),
    270: Entity(
        name="v40_water_capacity",
        type=CapabilityType.VOLUME,
        enabled_by_default=True,
        icon="mdi:water-thermometer",
    ),
    271: Entity(
        name="hot_water_available",
        type=CapabilityType.PERCENTAGE,
        enabled_by_default=True,
    ),
    278: Entity(
        # Atlantic names it "puissance electrique instantanee du ballon". One
        # corpus reading, and it is 0, so the unit is not claimed yet. See
        # docs/decisions.md.
        name="dhw_instant_power",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        icon="mdi:flash",
    ),
    280: Entity(
        name="cold_water_temperature",
        type=CapabilityType.TEMPERATURE,
        enabled_by_default=True,
        icon="mdi:coolant-temperature",
    ),
    281: Entity(
        name="dhw_heating_demand",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    283: Entity(
        name="off_peak_hours",
        type=CapabilityType.BINARY,
        enabled_by_default=True,
        icon="mdi:clock-outline",
    ),
    284: Entity(
        name="dhw_sg_level_status",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "normal",
            "1": "switch_on",
            "2": "switch_off",
            "3": "forced_on",
        },
    ),
    285: Entity(
        name="dhw_sg_power_electrical_request",
        type=CapabilityType.BINARY,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    286: Entity(
        name="dhw_sg_electrical_setpoint",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    287: Entity(
        name="dhw_smart_grid_api_connected",
        type=CapabilityType.BINARY,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    288: Entity(
        name="dhw_system_services_state",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "off",
            "1": "off_antifrost",
            "2": "on",
            "3": "on_reduced",
        },
    ),
    290: Entity(
        name="dhw_error_code",
        type=CapabilityType.ERROR_CODE,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
        icon="mdi:alert-circle-outline",
    ),
    292: Entity(
        name="hot_water_showers_expected",
        type=CapabilityType.INT,
        enabled_by_default=True,
        icon="mdi:water-plus",
    ),
    293: Entity(
        name="hot_water_showers_remaining",
        type=CapabilityType.INT,
        enabled_by_default=True,
        icon="mdi:water-check",
    ),
    294: Entity(
        name="target_temperature_step",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    295: Entity(
        name="schedule_time_step",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    296: Entity(
        name="schedule_minimum_interval",
        type=CapabilityType.TIME,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    297: Entity(
        name="control_temperature_mode",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "off",
            "3": "cool",
            "4": "heat",
        },
    ),
    298: Entity(
        name="total_consumption",
        type=CapabilityType.ENERGY,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    299: Entity(
        name="heat_cool_switch_type",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "switch_by_master",
            "1": "switch_by_slave",
        },
    ),
    300: Entity(
        name="cooling_activation_threshold",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    301: Entity(
        name="eeprom_version",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    302: Entity(
        name="development_index",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    303: Entity(
        name="error_code",
        type=CapabilityType.ERROR_CODE,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
        icon="mdi:alert-circle-outline",
    ),
    304: Entity(
        name="time_synchronized",
        type=CapabilityType.BINARY,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    306: Entity(
        name="max_schedule_slots_per_day",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    307: Entity(
        name="heating_period_min_duration",
        type=CapabilityType.TIME,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    308: Entity(
        name="dhw_smart_grid_level_request",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "normal",
            "1": "switch_on",
            "2": "switch_off",
            "3": "forced_on",
        },
    ),
    309: Entity(
        name="dhw_smart_grid_power_setpoint",
        type=CapabilityType.POWER,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        extra={"displayed_unit_of_measurement": UnitOfPower.WATT},
    ),
    310: Entity(
        name="dhw_thermal_generator_capabilities",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        bits=(
            (1, "electric_heater"),
            (2, "heat_pump"),
            (4, "boiler"),
        ),
    ),
    311: Entity(
        name="dhw_smart_grid_request_capabilities",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        bits=(
            (1, "smart_grid_level_wired"),
            (2, "schedule_self_consumption"),
            (4, "smart_grid_level_cloud"),
            (8, "schedule_from_cloud"),
            (16, "power_request"),
        ),
    ),
    312: Entity(
        # Read-only: the app has a getter and no writer, unlike 231 beside it.
        # See docs/decisions.md.
        name="dhw_current_control_target",
        type=CapabilityType.TEMPERATURE,
        enabled_by_default=True,
    ),
    313: Entity(
        name="dhw_self_consumption_status",
        type=CapabilityType.BINARY,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    315: Entity(
        name="timezone",
        type=CapabilityType.TIMEZONE,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
        icon="mdi:map-clock-outline",
    ),
    316: Entity(
        name="interface_fw",
        type=CapabilityType.STRING,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
        icon="mdi:tag",
    ),
    317: Entity(
        name="second_heating_circuit_available",
        type=CapabilityType.BINARY,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    318: Entity(
        name="error_code_1",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    319: Entity(
        name="error_code_2",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    320: Entity(
        name="error_code_3",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    321: Entity(
        name="error_code_4",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    322: Entity(
        name="error_code_5",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    323: Entity(
        name="error_code_6",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    324: Entity(
        name="error_code_7",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    325: Entity(
        name="error_code_8",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    326: Entity(
        name="error_code_9",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    327: Entity(
        name="error_code_10",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    328: Entity(
        name="main_error_code",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    329: Entity(
        name="min_schedule_ranges_per_day",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    330: Entity(
        name="schedule_range_step",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    331: Entity(
        name="schedule_range_max_duration",
        type=CapabilityType.TIME,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    332: Entity(
        name="schedule_range_min_duration",
        type=CapabilityType.TIME,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    333: Entity(
        name="heating_period_max_duration",
        type=CapabilityType.TIME,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    334: Entity(
        name="main_error_code_display",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    335: Entity(
        name="serial_number",
        type=CapabilityType.STRING,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
        icon="mdi:tag",
    ),
    336: Entity(
        name="dhw_panel_capabilities",
        type=CapabilityType.STRING,
        bits=(
            (1, "v40_state_of_charge"),
            (2, "main_setpoint_cursor"),
            (4, "secondary_setpoint_cursor"),
            (8, "data_inside"),
        ),
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    337: Entity(
        name="main_cursor_information",
        type=CapabilityType.STRING,
        reads_as={
            "0": "nothing",
            "1": "away",
            "2": "boost",
            "3": "photovoltaic",
            "4": "smart_grid",
            "5": "antilegionella",
            "6": "water_setpoint",
        },
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    338: Entity(
        name="secondary_cursor_information",
        type=CapabilityType.STRING,
        reads_as={
            "0": "nothing",
            "1": "eco",
            "2": "water_setpoint",
        },
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    339: Entity(
        name="dhw_panel_data",
        type=CapabilityType.STRING,
        reads_as={
            "0": "nothing",
            "1": "v40_state_of_charge",
            "2": "water_setpoint",
        },
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    340: Entity(
        name="water_setpoint_step",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    341: Entity(
        name="auto_mode_running_state",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "off",
            # What it says while the device is not in auto at all, which is
            # not the same as off.
            "1": "unavailable",
            "3": "cool",
            "4": "heat",
        },
    ),
    342: Entity(
        name="dhw_setpoint_without_override_sif",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    343: Entity(
        name="fuel_tank_capacity",
        type=CapabilityType.VOLUME,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    344: Entity(
        name="room_count",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    345: Entity(
        name="boiler_error_code",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    346: Entity(
        name="dhw_minimum_weekly_slots",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    347: Entity(
        name="daily_schedule_transitions",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    348: Entity(
        name="weekly_schedule_transitions",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    349: Entity(
        name="dhw_maximum_weekly_slots",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    350: Entity(
        name="air_circulation_supported_speeds",
        type=CapabilityType.STRING,
        reads_as=_SPEED_SETS,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    351: Entity(
        name="connectivity_display_capabilities",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        # Read as a sum: the name is plural and the one member the catalogue
        # declares sits on bit 1.
        bits=((1, "dhw_v40_consumption"),),
    ),
    352: Entity(
        name="absence_day_heating_temperature",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    353: Entity(
        name="presence_day_heating_temperature",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    354: Entity(
        name="presence_night_heating_temperature",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    355: Entity(
        name="absence_day_cooling_temperature",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    356: Entity(
        name="presence_day_cooling_temperature",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    357: Entity(
        name="presence_night_cooling_temperature",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    358: Entity(
        name="thermal_ambiance_scope",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    359: Entity(
        name="thermal_comfort_compatibility",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        bits=_THERMAL_GENERATOR_BITS,
    ),
    360: Entity(
        name="boost_end_time",
        type=CapabilityType.TIME,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        extra={"displayed_unit_of_measurement": UnitOfTime.SECONDS},
    ),
    361: Entity(
        name="boost_duration_step",
        type=CapabilityType.TIME,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    362: Entity(
        name="boost_duration_min",
        type=CapabilityType.TIME,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    380: Entity(
        name="outdoor_unit_error_code_cesa",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    381: Entity(
        name="ble_pairing_compatibility",
        type=CapabilityType.BINARY,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    400: Entity(
        name="interface_capabilities",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        bits=(
            (1, "wifi"),
            (2, "zigbee"),
            (4, "io_homecontrol"),
            (8, "bluetooth"),
            (256, "opentherm"),
            (512, "modbus"),
        ),
    ),
    58773: Entity(
        name="target_temperature_comfort_z1",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100000: Entity(
        name="thermal_zones_count",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100002: Entity(
        name="ventilation_options_supported",
        type=CapabilityType.STRING,
        bits=_VENTILATION_OPTION_BITS,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100004: Entity(
        name="ventilation_controls_available",
        type=CapabilityType.STRING,
        bits=_VENTILATION_CONTROL_BITS,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100010: Entity(
        name="hydraulic_heater_type",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "hydraulic_heater",
            "1": "hydraulic_floor",
            "2": "hydraulic_ceiling",
            "3": "dynamic_radiator",
        },
    ),
    100013: Entity(
        name="available_schedule_types",
        type=CapabilityType.STRING,
        bits=(
            (1, "on_off"),
            (2, "boost"),
        ),
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100014: Entity(
        # What the device calls itself. Not what model.py classifies on -- it
        # reads 255 on hardware that types perfectly well from its productId --
        # so this is a reading and not a source. See docs/decisions.md.
        name="device_type",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        # A zone is a name and a place in the device tree, not a thing with
        # readings, and it is the one product that reports this id without
        # being a device. See docs/decisions.md.
        absent_on=(CozytouchDeviceType.ZONE,),
        reads_as={
            "0": "hub",
            "1": "thermodynamic_water_heater",
            "2": "zigbee_interface_indoor_unit_fujitsu",
            "3": "heat_pump_generator",
            "4": "thermostat",
            "5": "electric_water_heater",
            "6": "electric_panel_heater",
            "7": "electric_towel_dryer_heater",
            "8": "electric_floor_heater",
            "9": "zigbee_interface_plenum",
            "10": "thermostat_central",
            "11": "thermostat_local",
            "255": "unknown",
        },
    ),
    100021: Entity(
        name="ventilation_controls_supported",
        type=CapabilityType.STRING,
        bits=_VENTILATION_CONTROL_BITS,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100022: Entity(
        name="supported_system_operating_modes",
        type=CapabilityType.STRING,
        bits=HVAC_MODE_BITS,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100023: Entity(
        name="supported_system_modes",
        type=CapabilityType.STRING,
        bits=_CONTROL_MODE_BITS,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100024: Entity(
        name="ventilation_options_available",
        type=CapabilityType.STRING,
        bits=_VENTILATION_OPTION_BITS,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100044: Entity(
        name="zigbee_mac_address",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100078: Entity(
        # A control where the app offers the identify button and a reading
        # everywhere else, which `winkable` decides. See docs/decisions.md.
        name="identify_request",
        type=CapabilityType.BINARY,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        icon="mdi:bell-ring-outline",
    ),
    100100: Entity(
        # The mode that was asked for, beside 7 which is the one running. Two
        # of its members are the vendor's own French, and one account reports
        # the string "None" on it, so it is read and never written.
        name="requested_thermal_comfort",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "off",
            "1": "auto",
            "3": "cool",
            "4": "heat",
            "5": "emergency_heat",
            "6": "pre_cooling",
            "7": "fan",
            "8": "dry",
            "9": "sleep",
            "10": "off",
            "11": "on",
        },
    ),
    100102: Entity(
        name="adaptive_planning",
        type=CapabilityType.BINARY,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100103: Entity(
        name="unexpected_events",
        type=CapabilityType.BINARY,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100105: Entity(
        name="generator_dhw_operating_mode",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "no_override",
            "1": "auto",
            "2": "antilegionella",
            "3": "comfort",
            "4": "reduced",
            "5": "protection",
            "6": "off",
        },
    ),
    100196: Entity(
        name="absence_programming_state",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100197: Entity(
        name="night_programming_state",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100198: Entity(
        name="presence_programming_state",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100260: Entity(
        name="away_mode",
        type=CapabilityType.AWAY_MODE_TIMESTAMPS,
        enabled_by_default=True,
        extra={
            "timestamps": AWAY_MODE_TIMESTAMPS,
            "timezoneCapabilityId": 315,
        },
    ),
    100261: Entity(
        # Three states like the gateway's switch, 2 being an absence still
        # to come. See docs/decisions.md.
        name="away_mode",
        type=CapabilityType.STRING,
        enabled_by_default=True,
        icon="mdi:airplane",
        reads_as={"0": "off", "1": "on", "2": "pending"},
    ),
    100300: Entity(
        name="schedule_start_day",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "sunday",
            "1": "monday",
            "2": "tuesday",
            "3": "wednesday",
            "4": "thursday",
            "5": "friday",
            "6": "saturday",
        },
    ),
    100301: Entity(
        name="max_schedule_slots_per_week",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100306: Entity(
        name="summer_winter_detection_threshold",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100320: Entity(
        name="prog_heat_monday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    100321: Entity(
        name="prog_heat_tuesday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    100322: Entity(
        name="prog_heat_wednesday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    100323: Entity(
        name="prog_heat_thursday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    100324: Entity(
        name="prog_heat_friday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    100325: Entity(
        name="prog_heat_saturday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    100326: Entity(
        name="prog_heat_sunday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    100327: Entity(
        name="prog_cool_monday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    100328: Entity(
        name="prog_cool_tuesday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    100329: Entity(
        name="prog_cool_wednesday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    100330: Entity(
        name="prog_cool_thursday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    100331: Entity(
        name="prog_cool_friday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    100332: Entity(
        name="prog_cool_saturday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    100333: Entity(
        name="prog_cool_sunday",
        type=CapabilityType.PROG,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    100334: Entity(
        name="lifestyle_prog_monday",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100335: Entity(
        name="lifestyle_prog_tuesday",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100336: Entity(
        name="lifestyle_prog_wednesday",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100337: Entity(
        name="lifestyle_prog_thursday",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100338: Entity(
        name="lifestyle_prog_friday",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100339: Entity(
        name="lifestyle_prog_saturday",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100340: Entity(
        name="occupancy_schedule_sunday",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100341: Entity(
        name="lifestyle_prog_sunday",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100400: Entity(
        name="generator_unsuccessful_burner_starts",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100402: Entity(
        name="number_of_hours_burner",
        type=CapabilityType.INT,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
        icon="mdi:fire",
    ),
    100406: Entity(
        name="number_of_starts_burner",
        type=CapabilityType.INT,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
        icon="mdi:fire",
    ),
    100409: Entity(
        name="generator_dhw_burner_hours",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100450: Entity(
        name="schedule_anticipation",
        type=CapabilityType.SWITCH,
        enabled_by_default=True,
        icon="mdi:clock-fast",
    ),
    100503: Entity(
        name="wifi_fw",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100505: Entity(
        name="powerful_mode",
        type=CapabilityType.SWITCH,
        enabled_by_default=True,
        icon="mdi:wind-power",
    ),
    100506: Entity(
        # Towel dryers only: no capture has one reporting it, and the branch
        # predates the room radiators, which do report it and are sold on the
        # presence detection.
        name="presence_mode",
        type=CapabilityType.SWITCH,
        enabled_by_default=True,
        icon="mdi:account",
        absent_on=(CozytouchDeviceType.TOWEL_RACK,),
    ),
    100507: Entity(
        # Same story as the absence setpoint in 172: the air conditioners report
        # eco mode without the Cozytouch app ever offering it. Reported is not
        # supported, so let the model table decide.
        name="eco_mode",
        type=CapabilityType.SWITCH,
        enabled_by_default=True,
        icon="mdi:flower-outline",
        needs_flag="ecoModeAvailable",
    ),
    100600: Entity(
        name="flow_control_heat",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "error",
            "1": "manual",
            "2": "outside_temperature_compensation",
            "3": "outside_temperature_compensation_with_room",
            "4": "pid",
        },
    ),
    100601: Entity(
        name="flow_control_cool",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "error",
            "1": "manual",
            "2": "outside_temperature_compensation",
            "3": "outside_temperature_compensation_with_room",
            "4": "pid",
        },
    ),
    100607: Entity(
        name="ambient_compensation_cool",
        type=CapabilityType.PERCENTAGE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100636: Entity(
        name="dhw_mode_b2b",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "volume_eco",
            "1": "volume_comfort",
            "10": "constant_setpoint",
            "12": "eco_comfort_schedule",
            "13": "automatic",
            "14": "milestone_schedule",
        },
    ),
    100800: Entity(
        name="available_fan_speeds",
        type=CapabilityType.STRING,
        reads_as=_SPEED_SETS,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    100801: Entity(
        # The speed the fan is actually running, which the climate entity
        # drives as its fan mode. The row is what gives the reading beside it a
        # word instead of a number. Its value space is not 350's: that one
        # names a whole *set* of speeds, this one names one speed.
        name="fan_speed",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={"1": "low", "2": "medium", "3": "high", "5": "auto"},
    ),
    100802: Entity(
        name="quiet_mode",
        type=CapabilityType.SWITCH,
        enabled_by_default=True,
        icon="mdi:fan-minus",
    ),
    100803: Entity(
        # Six flap positions on a Fujitsu indoor unit, plus a zero the vendor
        # itself calls unknown. The climate entity drives it as the swing mode.
        name="louver_position",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "unknown",
            "1": "position_1",
            "2": "position_2",
            "3": "position_3",
            "4": "position_4",
            "5": "position_5",
            "6": "position_6",
        },
    ),
    100804: Entity(
        name="swing_mode",
        type=CapabilityType.SWITCH,
        enabled_by_default=True,
        icon="mdi:arrow-oscillating",
    ),
    101302: Entity(
        name="outside_temperature_available",
        type=CapabilityType.BINARY,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    102004: Entity(
        name="air_circulation_speed",
        type=CapabilityType.SELECT,
        # The fan built from 102024 sets this, so the dropdown is redundant
        # and arrives switched off. See docs/decisions.md.
        enabled_by_default=False,
        icon="mdi:fan",
        extra={
            "modelList": "AirCirculationSpeeds",
        },
    ),
    102005: Entity(
        name="air_circulation_supported_modes",
        type=CapabilityType.STRING,
        bits=_AIR_CIRCULATION_MODE_BITS,
        category=CapabilityCategory.DIAG,
        icon="mdi:fan",
        enabled_by_default=False,
    ),
    102006: Entity(
        name="air_circulation_available_modes",
        type=CapabilityType.STRING,
        bits=_AIR_CIRCULATION_MODE_BITS,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    102020: Entity(
        # Named `AIR_MIXING_ACTUAL_MODE` by the vendor and read as air
        # circulation here for a year : it is the service the whole system
        # runs, and writing it is what moves every room -- 0 is the app's
        # general stop. See
        # docs/decisions.md.
        name="system_service",
        type=CapabilityType.SYSTEM_SERVICE,
        reads_as={
            "0": "off",
            "1": "auto_temperature",
            "2": "auto_season",
            "3": "cool",
            "4": "heat",
            "7": "fan",
            "8": "dry",
        },
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    102021: Entity(
        name="air_circulation_total_time",
        type=CapabilityType.DURATION_SELECT,
        enabled_by_default=True,
        icon="mdi:fan-clock",
        extra={
            "lowestValueCapabilityId": 102025,
            "highestValueCapabilityId": 102026,
            "stepCapabilityId": 102022,
            "lowest_value": 15,
            "highest_value": 300,
            "step": 15,
        },
    ),
    102022: Entity(
        name="air_circulation_time_step",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        icon="mdi:fan-clock",
        enabled_by_default=False,
    ),
    102023: Entity(
        name="air_circulation_remaining_time",
        type=CapabilityType.TIME,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
        icon="mdi:fan-clock",
    ),
    102024: Entity(
        name="air_circulation",
        # A fan as well as a switch : both platforms read this row, the way
        # CLIMATE feeds a climate entity and a sensor. See docs/decisions.md.
        type=CapabilityType.FAN,
        enabled_by_default=True,
        icon="mdi:fan",
        extra={
            "speedCapabilityId": 102004,
            "modelList": "AirCirculationSpeeds",
        },
    ),
    102025: Entity(
        name="air_circulation_time_min",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        icon="mdi:fan-clock",
        enabled_by_default=False,
    ),
    102026: Entity(
        name="air_circulation_time_max",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        icon="mdi:fan-clock",
        enabled_by_default=False,
    ),
    103014: Entity(
        name="room_type",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    103026: Entity(
        # What drives this room, which capability.py says a room slot cannot
        # tell you. It can. Read as a sum, since a room can sit in front of
        # more than one generator. See docs/decisions.md.
        name="thermal_generator",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        bits=_THERMAL_GENERATOR_BITS,
    ),
    103034: Entity(
        name="room_controls_capabilities",
        type=CapabilityType.STRING,
        bits=(
            (1, "light_control"),
            (2, "restriction_control"),
            (4, "central_heating"),
            (8, "baby_care"),
            (16, "antifrost"),
        ),
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    103114: Entity(
        name="boost_with_fan",
        type=CapabilityType.BINARY,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    103115: Entity(
        name="boost_duration",
        type=CapabilityType.TIME,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    103116: Entity(
        name="boost_duration_max",
        type=CapabilityType.TIME,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    103118: Entity(
        name="boost_without_fan_duration",
        type=CapabilityType.TIME,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    103119: Entity(
        name="boost_with_fan_duration",
        type=CapabilityType.TIME,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    103150: Entity(
        name="ambient_temperature_available",
        type=CapabilityType.BINARY,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    103199: Entity(
        name="antifrost_temperature",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    103450: Entity(
        name="schedule_anticipation_state",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    103626: Entity(
        name="flow_temperature_offset_heat",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    103627: Entity(
        name="flow_temperature_offset_cool",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    104025: Entity(
        name="zone_maximum_electrical_power",
        type=CapabilityType.POWER,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        extra={"displayed_unit_of_measurement": UnitOfPower.WATT},
    ),
    104044: Entity(
        name="boost_mode",
        type=CapabilityType.SWITCH,
        enabled_by_default=True,
        icon="mdi:heat-wave",
    ),
    104047: Entity(
        name="boost_timeout_max",
        type=CapabilityType.MINUTES_ADJUSTMENT_NUMBER,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
        icon="mdi:clock-outline",
        extra={
            "lowest_value": 5,
            "highest_value": 60,
            "step": 5,
        },
    ),
    104050: Entity(
        name="open_window_detection",
        type=CapabilityType.BINARY,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    104051: Entity(
        name="open_window_state",
        type=CapabilityType.BINARY,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    105011: Entity(
        name="supported_dhw_modes",
        type=CapabilityType.STRING,
        bits=_DHW_MODE_BITS,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    105012: Entity(
        name="supported_dhw_system_operating_modes",
        type=CapabilityType.STRING,
        bits=_DHW_HEATING_TYPE_BITS,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    105122: Entity(
        name="dhw_boost_end_timestamp",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    105300: Entity(
        name="water_temperature_limit",
        type=CapabilityType.TEMPERATURE,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    105301: Entity(
        name="dhw_lowest_water_setpoint",
        type=CapabilityType.TEMPERATURE,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    105304: Entity(
        name="max_target_temperature_derogation",
        type=CapabilityType.TEMPERATURE,
        enabled_by_default=True,
        category=CapabilityCategory.DIAG,
    ),
    105636: Entity(
        name="dhw_comfort_mode",
        type=CapabilityType.STRING,
        reads_as={
            "0": "eco",
            "1": "comfort",
        },
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    105906: Entity(
        name="v40_applied_setpoint",
        type=CapabilityType.TEMPERATURE_PERCENT_ADJUSTMENT_NUMBER,
        enabled_by_default=True,
        extra={
            "temperatureMin": 15.0,
            "temperatureMax": 65.0,
        },
    ),
    105907: Entity(
        name="v40_setpoint_filled_by_user",
        type=CapabilityType.TEMPERATURE_PERCENT_ADJUSTMENT_NUMBER,
        enabled_by_default=True,
        extra={
            "temperatureMin": 15.0,
            "temperatureMax": 65.0,
        },
    ),
    # Whether a room slot holds this circuit's setpoint. Named from what it
    # coincides with rather than from anything the vendor says -- see
    # docs/decisions.md for the seven circuits it was read on. Diagnostic and
    # off by default: it is read to decide whether the circuit is a device of
    # its own, and it is nobody's control.
    106000: Entity(
        name="circuit_driven_by_room",
        type=CapabilityType.BINARY,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        icon="mdi:home-thermometer",
    ),
    107060: Entity(
        name="generator_external_input_1_function",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "not_connected",
            "1": "off_peak",
            "2": "self_consumption",
            "3": "smart_grid",
        },
    ),
    107078: Entity(
        name="boiler_switch_type",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "undefined",
            "1": "cop",
            "2": "cop",
        },
    ),
    107079: Entity(
        name="cop_threshold",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    107083: Entity(
        name="backup_heater_type",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "none",
            "1": "electric",
            "2": "boiler",
        },
    ),
    107106: Entity(
        name="generator_setpoint_mode",
        type=CapabilityType.STRING,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
        reads_as={
            "0": "off",
            "4": "schedule",
            "5": "peak_and_offpeak_schedule",
            "6": "peak_and_offpeak",
        },
    ),
    107451: Entity(
        name="peak_electricity_price",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    107452: Entity(
        name="off_peak_electricity_price",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    107453: Entity(
        name="gas_price",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
    207451: Entity(
        name="base_electricity_price",
        type=CapabilityType.INT,
        category=CapabilityCategory.DIAG,
        enabled_by_default=False,
    ),
}
