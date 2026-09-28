"""What a fan, swing or away-date change from Home Assistant writes.

Fan and swing share one write path, and so do the away mode's two dates, so
a slip in either shows up on every device that has them. A date sends the
window only while the absence is on ; off, it waits for the switch. Nothing else in the
suite calls these writes. The entities are driven unbound against a stand-in,
the way test_hvac_action.py drives the update.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from functools import partial
from types import SimpleNamespace

from custom_components.cozytouch.climate import FAN_QUIET, CozytouchClimate
from custom_components.cozytouch.datetime import CozytouchAwayModeDateTime
from custom_components.cozytouch.hub import Hub
from custom_components.cozytouch.infos import CapabilityInfos, ModelInfos
from homeassistant.components.climate import SWING_ON
from homeassistant.util import dt as dt_util

FAN = {"quietModeCapabilityId": 30, "fanModeCapabilityId": 31}
SWING = {"swingOnCapabilityId": 40, "swingModeCapabilityId": 41}


def climate(**capabilityIds):
    capability = CapabilityInfos()
    for key, value in capabilityIds.items():
        capability[key] = value

    modelInfos = ModelInfos()
    modelInfos.fanModes = {1: "low", 3: "high"}
    modelInfos.swingModes = {2: "up", 4: "down"}

    writes = []

    async def set_capability_value(capabilityId, value):
        writes.append((capabilityId, value))

    async def async_request_refresh():
        writes.append("refresh")

    fake = SimpleNamespace(
        _capability=capability,
        _modelInfos=modelInfos,
        coordinator=SimpleNamespace(
            set_capability_value=set_capability_value,
            async_request_refresh=async_request_refresh,
        ),
    )
    fake._write_mode = partial(CozytouchClimate._write_mode, fake)
    return fake, writes


def run(coroutine):
    asyncio.run(coroutine)


def test_a_fan_speed_switches_quiet_off_then_writes_the_speed():
    fake, writes = climate(**FAN)

    run(CozytouchClimate.async_set_fan_mode(fake, "high"))

    assert writes == [(30, "0"), (31, "3"), "refresh"]


def test_quiet_is_written_to_its_own_capability_alone():
    fake, writes = climate(**FAN)

    run(CozytouchClimate.async_set_fan_mode(fake, FAN_QUIET))

    assert writes == [(30, "1"), "refresh"]


def test_a_fan_speed_without_a_quiet_capability_writes_only_the_speed():
    fake, writes = climate(fanModeCapabilityId=31)

    run(CozytouchClimate.async_set_fan_mode(fake, "low"))

    assert writes == [(31, "1"), "refresh"]


def test_a_fan_speed_the_table_does_not_name_writes_no_speed():
    fake, writes = climate(**FAN)

    run(CozytouchClimate.async_set_fan_mode(fake, "turbo"))

    assert writes == [(30, "0"), "refresh"]


def test_a_swing_position_switches_swing_off_then_writes_the_position():
    fake, writes = climate(**SWING)

    run(CozytouchClimate.async_set_swing_mode(fake, "down"))

    assert writes == [(40, "0"), (41, "4"), "refresh"]


def test_swing_on_is_written_to_its_own_capability_alone():
    fake, writes = climate(**SWING)

    run(CozytouchClimate.async_set_swing_mode(fake, SWING_ON))

    assert writes == [(40, "1"), "refresh"]


def test_fan_and_swing_do_not_write_into_each_other():
    fake, writes = climate(**FAN, **SWING)

    run(CozytouchClimate.async_set_fan_mode(fake, "low"))
    run(CozytouchClimate.async_set_swing_mode(fake, "up"))

    assert writes == [(30, "0"), (31, "1"), "refresh", (40, "0"), (41, "2"), "refresh"]


def away_hub(reported=None):
    """A hub over real away-mode methods, recording what it sends."""
    hub = SimpleNamespace(
        _timestamp_away_mode_start=None,
        _timestamp_away_mode_end=None,
        reported={152: "0", 222: "[0,0]"} if reported is None else reported,
        sent=[],
    )
    hub.get_capability_value = lambda cid, default="0": hub.reported.get(cid, default)

    async def set_away_mode(start, end):
        hub.sent.append((start, end))
        return True

    hub.set_away_mode = set_away_mode
    for name in (
        "away_mode_switches",
        "is_away",
        "set_away_mode_bound",
        "get_away_mode_start",
        "get_away_mode_end",
        "away_mode_init",
    ):
        setattr(hub, name, partial(getattr(Hub, name), hub))
    return hub


def away_date(hub, index):
    capability = CapabilityInfos()
    capability.capabilityId = 222
    return SimpleNamespace(
        _capability=capability,
        _timestamp_index=index,
        coordinator=hub,
        async_write_ha_state=lambda: None,
    )


START = datetime(2099, 10, 1, 8, 0, tzinfo=UTC)
END = datetime(2099, 10, 8, 18, 0, tzinfo=UTC)


def set_both(hub):
    run(CozytouchAwayModeDateTime.async_set_value(away_date(hub, 0), START))
    run(CozytouchAwayModeDateTime.async_set_value(away_date(hub, 1), END))


def test_the_start_date_lands_on_the_start_and_the_end_on_the_end():
    hub = away_hub()

    set_both(hub)

    assert hub._timestamp_away_mode_start == int(START.timestamp())
    assert hub._timestamp_away_mode_end == int(END.timestamp())


def test_each_date_reads_back_what_was_set():
    hub = away_hub()
    start, end = away_date(hub, 0), away_date(hub, 1)

    run(CozytouchAwayModeDateTime.async_set_value(start, START))
    run(CozytouchAwayModeDateTime.async_set_value(end, END))

    assert CozytouchAwayModeDateTime.native_value.fget(start) == START
    assert CozytouchAwayModeDateTime.native_value.fget(end) == END


def read(hub, index):
    return CozytouchAwayModeDateTime.native_value.fget(away_date(hub, index))


def reads_as_now(value):
    """Now to the minute, allowing for the minute turning mid-test."""
    minute = dt_util.now().replace(second=0, microsecond=0)
    return value in (minute, minute - timedelta(minutes=1))


def test_with_no_window_the_start_reads_as_now_and_the_end_as_unknown():
    """What the switch would send : from now, to an end still to pick."""
    hub = away_hub()

    assert reads_as_now(read(hub, 0))
    assert read(hub, 1) is None


def test_a_window_already_over_reads_as_a_fresh_one_while_off():
    hub = away_hub()
    hub.away_mode_init(1000, 2000)

    assert reads_as_now(read(hub, 0))
    assert read(hub, 1) is None


def test_an_absence_under_way_reads_as_it_is():
    """On, the start is the day it began, however long ago."""
    hub = away_hub({152: "1", 222: "[1000,2000]"})
    hub.away_mode_init(1000, int(END.timestamp()))

    assert read(hub, 0) == datetime.fromtimestamp(1000, tz=dt_util.DEFAULT_TIME_ZONE)
    assert read(hub, 1) == END


def test_a_date_set_while_the_absence_is_off_sends_nothing():
    """The dates without the switch were the broken state.

    The setup read away and the device did not. Off, a date is kept for the
    switch to send.
    """
    hub = away_hub()

    set_both(hub)

    assert hub.sent == []


def test_a_date_set_while_the_absence_is_on_sends_the_whole_window():
    hub = away_hub({152: "1", 222: "[1,2]"})

    set_both(hub)

    # The start alone is sent nothing : the old end is not after it.
    assert hub.sent == [(int(START.timestamp()), int(END.timestamp()))]


def test_a_programmed_absence_counts_as_on():
    hub = away_hub({152: "2", 222: "[1,2]"})

    set_both(hub)

    assert hub.sent == [(int(START.timestamp()), int(END.timestamp()))]


def test_an_index_past_the_two_dates_writes_nothing():
    hub = away_hub()

    run(CozytouchAwayModeDateTime.async_set_value(away_date(hub, 2), START))

    assert hub._timestamp_away_mode_start is None
    assert hub._timestamp_away_mode_end is None
    assert hub.sent == []
