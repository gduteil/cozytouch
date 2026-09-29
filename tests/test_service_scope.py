"""Which capability the system's select writes, and which one a room's climate.

An air-conditioning system runs one service at a time : the outdoor unit
cannot cool one room and dry the next. So the mode is the system's, carried
on 102020, and every room follows when it is written. What is a room's own is
whether it is running at all, which is its own service capability at 0.

Captured from the iOS app on a three-room account, 2026-09-21, three writes :

    mode   -> {"capabilityId": 102020, "deviceId": <room>, "value": "8"}
    off    -> {"capabilityId": 7,      "deviceId": <room>, "value": "0"}
    on     -> {"capabilityId": 7,      "deviceId": <room>, "value": "3"}

The last is the service the house is already running. The app's general stop
was not in that capture, but a diagnostics dump taken right after it
(2026-09-28) was : 102020 at 0 on all three rooms within the same second, then
each room's 7 at 0 five seconds later.

So the select is the app's dropdown, general stop included, and the room's
climate is the app's toggle : off, or on into whatever the house runs.
"""

import asyncio
from types import SimpleNamespace

import pytest

from custom_components.cozytouch.capability import get_capability_infos
from custom_components.cozytouch.climate import CozytouchClimate
from custom_components.cozytouch.const import SERVICE_OFF
from custom_components.cozytouch.infos import CapabilityInfos
from custom_components.cozytouch.model import get_model_infos
from custom_components.cozytouch.select import CozytouchSystemServiceSelect
from homeassistant.components.climate import HVACMode
from homeassistant.exceptions import HomeAssistantError

ROOM_SERVICE = 7
SYSTEM_SERVICE = 102020
SUPPORTED = 100022
COOL = 3
DRY = 8

# An air-conditioning room, model 557, as the account reports one.
AC_ROOM = 557

MODES = {0: HVACMode.OFF, COOL: HVACMode.COOL, DRY: HVACMode.DRY}


def stand_in(reported):
    """A hub stand-in that records what it is asked to write."""
    written = []

    async def set_capability_value(capabilityId, value):
        written.append((capabilityId, value))
        reported[capabilityId] = value

    coordinator = SimpleNamespace(
        set_capability_value=set_capability_value,
        get_capability_value=lambda cid, default="0": reported.get(cid, default),
        get_model_infos=lambda: get_model_infos(AC_ROOM),
        async_request_refresh=_noop,
    )
    return coordinator, written


def build(reported, system=SYSTEM_SERVICE):
    """A climate entity over a hub stand-in that records what it writes.

    Only what the mode code reads is set : the entity is not the subject
    here, the two capability ids it chooses between are.
    """
    entity = CozytouchClimate.__new__(CozytouchClimate)
    entity._modelInfos = SimpleNamespace(HVACModes=MODES)
    entity._modes = MODES
    entity._capability = CapabilityInfos(
        capabilityId=ROOM_SERVICE,
        **({"systemServiceCapabilityId": system} if system else {}),
    )
    entity.coordinator, written = stand_in(reported)
    return entity, written


def build_select(reported):
    """The system's service select, as the platform builds it."""
    coordinator, written = stand_in(reported)
    select = CozytouchSystemServiceSelect(
        coordinator=coordinator,
        capability=CapabilityInfos(capabilityId=SYSTEM_SERVICE, name="system_service"),
        config_title="Room",
        config_uniq_id="room",
    )
    return select, written


async def _noop():
    """What the entity calls once it has written."""


def test_a_room_offers_off_and_what_the_house_runs():
    """On or off : the mode itself is the select's."""
    entity, _ = build({ROOM_SERVICE: str(COOL), SYSTEM_SERVICE: str(COOL)})

    assert entity._offered_modes() == [HVACMode.OFF, HVACMode.COOL]


def test_a_stopped_house_leaves_a_room_only_off():
    """166 permits only off then, and the list says so."""
    entity, _ = build({ROOM_SERVICE: SERVICE_OFF, SYSTEM_SERVICE: SERVICE_OFF})

    assert entity._offered_modes() == [HVACMode.OFF]


def test_a_device_without_a_system_offers_its_whole_table():
    """A boiler has no select beside it, so its climate keeps every mode."""
    entity, _ = build({ROOM_SERVICE: str(COOL)}, system=None)

    assert entity._offered_modes() == list(MODES.values())


def test_off_switches_the_room_alone():
    """The app's toggle : 7 at 0, and the house left running."""
    entity, written = build({ROOM_SERVICE: str(DRY), SYSTEM_SERVICE: str(DRY)})

    asyncio.run(entity.async_set_hvac_mode(HVACMode.OFF))

    assert written == [(ROOM_SERVICE, SERVICE_OFF)]


def test_on_joins_the_service_the_house_runs():
    """On writes the house's service into the room, as the capture shows."""
    entity, written = build({ROOM_SERVICE: SERVICE_OFF, SYSTEM_SERVICE: str(DRY)})

    asyncio.run(entity.async_set_hvac_mode(HVACMode.DRY))

    assert written == [(ROOM_SERVICE, str(DRY))]


def test_a_room_cannot_start_a_stopped_house():
    """The way back is the select ; say so, write nothing."""
    entity, written = build({ROOM_SERVICE: SERVICE_OFF, SYSTEM_SERVICE: SERVICE_OFF})

    with pytest.raises(HomeAssistantError):
        asyncio.run(entity.async_set_hvac_mode(HVACMode.COOL))

    assert written == []


def test_a_device_without_the_system_capability_writes_its_own():
    """A boiler has no system beside it, and keeps the write it always had."""
    entity, written = build({ROOM_SERVICE: str(COOL)}, system=None)

    asyncio.run(entity.async_set_hvac_mode(HVACMode.DRY))

    assert written == [(ROOM_SERVICE, str(DRY))]


def test_the_room_climate_is_wired_to_the_system_service():
    """The id is derived from what the device reports, not written per model."""
    capability = get_capability_infos(
        get_model_infos(AC_ROOM),
        ROOM_SERVICE,
        "0",
        {ROOM_SERVICE, SYSTEM_SERVICE, 40, 117},
    )

    assert capability.systemServiceCapabilityId == SYSTEM_SERVICE


def test_the_select_offers_what_the_app_offers():
    """Five entries, in the app's order, fan removed by 100022 as the app does."""
    select, _ = build_select({SYSTEM_SERVICE: str(COOL), SUPPORTED: "285"})

    assert select.options == ["off", "heat", "cool", "auto", "dry"]
    assert select.current_option == "cool"


def test_the_general_stop_is_the_select_at_off():
    """One write, on the system's service ; every room follows it off."""
    select, written = build_select({SYSTEM_SERVICE: str(COOL), SUPPORTED: "285"})

    asyncio.run(select.async_select_option("off"))

    assert written == [(SYSTEM_SERVICE, SERVICE_OFF)]


def test_starting_again_is_a_service_picked_in_the_same_list():
    """The app has no memory to restore either : a service is chosen."""
    select, written = build_select({SYSTEM_SERVICE: SERVICE_OFF, SUPPORTED: "285"})

    asyncio.run(select.async_select_option("dry"))

    assert written == [(SYSTEM_SERVICE, str(DRY))]
