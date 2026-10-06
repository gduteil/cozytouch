"""Typed attribute access over the mappings the two tables answer with.

These classes *are* dicts, equal to the literals the tests pin ; what they add
is a declared field list, so a typo'd field raises instead of landing as a
silent new key. A field is a key only when a branch sets it -- the declarations
say what a field is, never that it is present.
"""

from enum import StrEnum
from typing import TYPE_CHECKING, NamedTuple

from homeassistant.components.climate.const import HVACMode

from .const import CozytouchCapabilityVariableType

if TYPE_CHECKING:
    from .model import CozytouchDeviceType


class CapabilityType(StrEnum):
    """What a capability becomes, which decides the platform that builds it.

    The members equal the strings they replaced, so stored state and raw
    values keep comparing equal. Adding one here only
    means something once a platform picks it up; test_capability_coverage.py
    checks the two sides against each other.
    """

    AWAY_MODE_SWITCH = "away_mode_switch"
    AWAY_MODE_TIMESTAMPS = "away_mode_timestamps"
    BINARY = "binary"
    CLIMATE = "climate"
    DURATION_SELECT = "duration_select"
    ENERGY = "energy"
    FAN = "fan"
    FLOW_RATE = "flow_rate"
    ERROR_CODE = "error_code"
    INT = "int"
    MINUTES_ADJUSTMENT_NUMBER = "minutes_adjustment_number"
    PERCENTAGE = "percentage"
    POWER = "power"
    PRESSURE = "pressure"
    PROG = "prog"
    PROGTIME = "progtime"
    SELECT = "select"
    SIGNAL = "signal"
    STRING = "string"
    SWITCH = "switch"
    SYSTEM_SERVICE = "system_service"
    TEMPERATURE = "temperature"
    TEMPERATURE_ADJUSTMENT_NUMBER = "temperature_adjustment_number"
    TEMPERATURE_PERCENT_ADJUSTMENT_NUMBER = "temperature_percent_adjustment_number"
    TIME = "time"
    TIMEZONE = "timezone"
    VOLUME = "volume"
    WATER_CONSUMPTION = "water_consumption"


class CapabilityCategory(StrEnum):
    """Where the entity lands on the device page.

    CONFIG is consumer-side vocabulary: sensor.py honours it, the mapping has
    never produced it.
    """

    SENSOR = "sensor"
    DIAG = "diag"
    CONFIG = "config"


class TimestampInfos(NamedTuple):
    """One of the entities a timestamps capability fans out into.

    The capability's value is a comma-separated pair, and each half becomes
    its own entities: the position in `CapabilityInfos.timestamps` is the
    position in that value.
    """

    name: str
    icon: str


class AttributeDict(dict):
    """A dict whose entries are attributes, allowed by the subclass declaring them."""

    __slots__ = ()
    _declared: frozenset[str] = frozenset()

    def __init_subclass__(cls):
        """Collect the declared fields once; the annotations are the declaration."""
        super().__init_subclass__()
        cls._declared = frozenset(cls.__annotations__)

    def __init__(self, **fields):
        """Start from keyword fields, checked like any other attribute write."""
        super().__init__()
        for key, value in fields.items():
            setattr(self, key, value)

    def __getattr__(self, key):
        """Fall back to the mapping; a missing key reads as a missing attribute."""
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key) from None

    def __setattr__(self, key, value):
        """Write into the mapping, refusing a field the class does not declare."""
        if key not in self._declared:
            raise AttributeError(f"{type(self).__name__} declares no field {key!r}")
        self[key] = value

    def __delattr__(self, key):
        """Drop the entry; a missing key reads as a missing attribute."""
        try:
            del self[key]
        except KeyError:
            raise AttributeError(key) from None


class ModelInfos(AttributeDict):
    """What the model table says about one device."""

    modelId: int
    name: str
    type: "CozytouchDeviceType"
    HVACModes: dict[int, HVACMode]
    HVACModesCapabilityId: set[int]
    HeatingModes: dict[int, str]
    fanModes: dict[int, str]
    swingModes: dict[int, str]
    AirCirculationSpeeds: dict[int, str]

    # The optional flags, present only on the models that declare them.
    currentTemperatureAvailable: bool
    currentTemperatureAvailableZ1: bool
    currentTemperatureAvailableZ2: bool
    exhaustTemperatureAvailable: bool
    quietModeAvailable: bool
    awayModeTemperatureAvailable: bool
    ecoModeAvailable: bool
    overrideModeAvailable: bool
    winkable: bool


class CapabilityInfos(AttributeDict):
    """What the capability mapping says about one id on one device."""

    modelId: int
    capabilityId: int
    # Set by the hub on every capability it hands to a platform.
    deviceId: int

    # What the entity is: its translation key, the platform that builds it,
    # and how it lands in the registry.
    name: str
    type: CapabilityType
    category: CapabilityCategory
    icon: str
    timestamps: tuple[TimestampInfos, ...]
    value_type: CozytouchCapabilityVariableType
    displayed_unit_of_measurement: str
    enabled_by_default: bool
    modelList: str

    # How its raw string reads: encodings and inline bounds.
    value_off: str
    value_on: str
    value_pending: str
    lowest_value: float
    highest_value: float
    step: float
    temperatureMin: float
    temperatureMax: float

    # The other capability ids the entity is wired to.
    targetCapabilityId: int
    targetCoolCapabilityId: int
    currentValueCapabilityId: int | None
    currentAvailableCapabilityId: int
    lowestValueCapabilityId: int
    highestValueCapabilityId: int
    lowestCoolValueCapabilityId: int
    highestCoolValueCapabilityId: int
    stepCapabilityId: int
    hvacActionCapabilityId: int
    heatingActiveCapabilityId: int
    airCirculationCapabilityId: int
    systemServiceCapabilityId: int
    progCapabilityId: int
    progOverrideCapabilityId: int
    progOverrideTotalTimeCapabilityId: int
    progOverrideTimeCapabilityId: int
    activityCapabilityId: int
    ecoCapabilityId: int
    boostCapabilityId: int
    fanModeCapabilityId: int
    quietModeCapabilityId: int
    swingModeCapabilityId: int
    swingOnCapabilityId: int
    timestampsCapabilityId: int
    timezoneCapabilityId: int
    capabilityDuplicate: int
