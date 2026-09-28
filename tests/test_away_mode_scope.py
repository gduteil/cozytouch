"""Who gets a writable away window, and who only gets to read one.

The gateway reports the pair of timestamps (222/226) *and* the switch that
commits them (152/227): setting a date there writes the setup's absence and
mirrors it back onto the capability. A room slot reports its own pair, 100260,
and no switch at all -- so a datetime entity built for it would stage a window
that nothing ever sends, and read as a control that silently does nothing.

These drive the datetime platform the way `tests/test_sensor_metadata.py`
drives the sensor one : a hub stand-in, a plain list for `async_add_entities`.
"""

from functools import partial
from types import SimpleNamespace

from _harness import entry_over, set_up

from custom_components.cozytouch import datetime as datetime_platform
from custom_components.cozytouch.capability_table import CAPABILITIES
from custom_components.cozytouch.hub import Hub
from custom_components.cozytouch.infos import CapabilityInfos, CapabilityType

ROOM_TIMESTAMPS = 100260
GATEWAY_TIMESTAMPS = 222
GATEWAY_SWITCH = 152


def build(capabilityId, reported):
    """Run the datetime platform over one timestamps capability.

    `reported` is what the device answers for any other id, which is how the
    platform tells a gateway from a room.
    """
    capability = CapabilityInfos(
        capabilityId=capabilityId,
        name="away_mode",
        type=CapabilityType.AWAY_MODE_TIMESTAMPS,
        timestamps=CAPABILITIES[capabilityId].extra["timestamps"],
        timezoneCapabilityId=315,
    )
    hub = SimpleNamespace(
        get_capabilities_for_device=lambda deviceId=None: [capability],
        get_capability_value=lambda cid, default="0": reported.get(cid, default),
    )
    hub.away_mode_switches = partial(Hub.away_mode_switches, hub)
    return set_up(datetime_platform, entry_over(hub, deviceId=1))


def test_the_room_pair_builds_no_datetime():
    """100260 without a switch beside it: readable, not settable."""
    assert build(ROOM_TIMESTAMPS, {}) == []


def test_the_gateway_pair_still_builds_both_ends():
    """The switch is there, so the two ends of the window stay writable."""
    built = build(GATEWAY_TIMESTAMPS, {GATEWAY_SWITCH: "0"})
    assert [entity._timestamp_index for entity in built] == [0, 1]


def test_the_room_pair_is_mapped_as_timestamps():
    """The row exists at all -- it used to fall through as an unknown id."""
    row = CAPABILITIES[ROOM_TIMESTAMPS]
    assert row.type is CapabilityType.AWAY_MODE_TIMESTAMPS
    assert row.name == "away_mode"
