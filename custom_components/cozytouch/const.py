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
