"""Constants for the Atlantic Cozytouch integration."""

from enum import IntEnum

DOMAIN = "cozytouch"

COZYTOUCH_ATLANTIC_API = "https://apis.groupe-atlantic.com"
COZYTOUCH_CLIENT_ID = (
    "Q3RfMUpWeVRtSUxYOEllZkE3YVVOQmpGblpVYToyRWNORHpfZHkzNDJVSnFvMlo3cFNKTnZVdjBh"
)

CONF_DUMPJSON = "dumpJSON"


class CozytouchCapabilityVariableType(IntEnum):
    """Capabilities types."""

    STRING = 0
    BOOL = 1
    FLOAT = 2
    INT = 3
    ARRAY = 4


SWING_MODE_UP = "up"
SWING_MODE_MIDDLE_UP = "middle_up"
SWING_MODE_MIDDLE_DOWN = "middle_down"
SWING_MODE_DOWN = "down"

HEATING_MODE_OFF = "off"
HEATING_MODE_MANUAL = "manual"
HEATING_MODE_ECO_PLUS = "eco_plus"
HEATING_MODE_PROG = "prog"

AIR_CIRCULATION_SPEED_LOW = "low"
AIR_CIRCULATION_SPEED_MEDIUM = "medium"
AIR_CIRCULATION_SPEED_HIGH = "high"


# The three weekly programs these devices hold, by the first capability of
# each seven-day run. Read by the calendar, by the per-day sensors it disables
# and by the migration that disables them. A program has more than one
# candidate run because two firmware families store the same week in different
# places and no device reports both. See docs/decisions.md.
PROGRAM_BLOCKS = {
    "heating": (196, 100320),
    "cooling": (203, 100327),
    "hot_water": (237,),
}

# A block is seven consecutive capabilities, one per day, monday first, so an
# index into this tuple is an offset from the block's first id.
PROGRAM_DAYS = (
    "monday",
    "tuesday",
    "wednesday",
    "thursday",
    "friday",
    "saturday",
    "sunday",
)

# Writing is narrower than reading, deliberately : set_schedule refuses the
# hot-water block until a capture confirms it. See docs/decisions.md.
WRITABLE_PROGRAM_BLOCKS = {
    program: firsts
    for program, firsts in PROGRAM_BLOCKS.items()
    if program != "hot_water"
}


def program_block(first: int) -> range:
    """The seven consecutive capability ids one weekly program is stored in."""
    return range(first, first + len(PROGRAM_DAYS))


def program_days(program: str) -> frozenset[int]:
    """Every id any firmware stores this program's days in."""
    return frozenset(
        capabilityId
        for first in PROGRAM_BLOCKS[program]
        for capabilityId in program_block(first)
    )


def stored_in(program: str, reports) -> int | None:
    """Where a device holds a program, all seven days of it or nowhere.

    `reports` answers whether one capability id is one the device sends. The
    runs are tried in order, since no device reports two of them. See
    docs/decisions.md.
    """
    for first in PROGRAM_BLOCKS[program]:
        if all(reports(day) for day in program_block(first)):
            return first

    return None


SERVICE_VALUES = {
    "0": "off",
    "1": "auto",
    "3": "cool",
    "4": "heat",
    "5": "emergency_heat",
    "6": "pre_cooling",
    "7": "fan",
    "8": "dry",
    "9": "sleep",
}

# The value a service capability carries when a room is switched off, which
# is the one service value that is the room's own. See docs/decisions.md.
SERVICE_OFF = "0"

HVAC_MODE_BITS = (
    (1, "off"),
    (6, "auto"),
    (8, "cool"),
    (16, "heat"),
    (128, "fan"),
    (256, "dry"),
)

# The same masks, keyed by the mode value 7 and 8 carry, so the modes a device
# offers can be read off capability 100022 rather than written per model.
# Derived rather than written out, so the two cannot drift apart ; a mode the
# bit table does not name is absent here and narrows nothing.
HVAC_MODE_MASKS = {
    int(value): mask
    for value, name in SERVICE_VALUES.items()
    for mask, bitName in HVAC_MODE_BITS
    if bitName == name
}


def narrowed_modes[T](modes: dict[int, T], supported: str | None) -> dict[int, T]:
    """The model's modes, minus those capability 100022 says the unit lacks.

    See docs/decisions.md.
    """
    if supported is None:
        return modes

    mask = int(float(supported))
    narrowed = {
        value: mode
        for value, mode in modes.items()
        if value not in HVAC_MODE_MASKS or HVAC_MODE_MASKS[value] & mask
    }
    return narrowed or modes
