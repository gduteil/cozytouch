"""Switching the absence : one action, and never the window without the switch.

The window is the setup's, a PUT on the account ; whether the absence is on is
each device's own capability (152 or 227), with the pair mirrored beside it
(222 or 226). Sending the first without the second is what used to happen when
a date was edited with the absence off, and it left the setup away and the
device not -- a state the vendor app never produces.

So everything here pins one shape : the PUT once, then on every device of the
account that switches the absence, the pair and then the switch. The service,
the switch and a date moved while the absence is on all go through it.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from functools import partial
from types import SimpleNamespace

import pytest
from test_services import make_hass
import voluptuous as vol

from custom_components.cozytouch import services
from custom_components.cozytouch.hub import Hub, away_window_is_valid
from custom_components.cozytouch.switch import CozytouchAwayModeSwitch
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError

NOW = datetime(2026, 9, 24, 12, 0, tzinfo=UTC)
START = int(datetime(2099, 10, 1, 8, 0, tzinfo=UTC).timestamp())
END = int(datetime(2099, 10, 8, 18, 0, tzinfo=UTC).timestamp())


class FakeAccount:
    def __init__(self, accepts=True):
        self.accepts = accepts
        self.absences = []
        self.online = True

    async def set_absence(self, start, end):
        self.absences.append((start, end))
        return self.accepts


def hub_over(account, reported, siblings=None, log=None):
    """A hub stand-in running Hub's own away-mode methods."""
    hub = SimpleNamespace(
        _account=account,
        account=account,
        online=account.online,
        reported=reported,
        _timestamp_away_mode_start=None,
        _timestamp_away_mode_end=None,
        refreshed=0,
    )
    log = [] if log is None else log
    hub.log = log

    hub.get_capability_value = lambda cid, default="0": hub.reported.get(cid, default)

    async def set_capability_value(capabilityId, value):
        log.append((id(hub), capabilityId, value))

    async def async_request_refresh():
        hub.refreshed += 1

    hub.set_capability_value = set_capability_value
    hub.async_request_refresh = async_request_refresh
    hub._account_hubs = lambda: [hub, *(siblings or [])]
    for name in (
        "away_mode_init",
        "away_mode_switches",
        "reported_away_window",
        "_follow_reported_away_window",
        "absence_under_way",
        "is_away",
        "set_away_mode",
        "set_away_mode_bound",
        "get_away_mode_start",
        "get_away_mode_end",
    ):
        setattr(hub, name, partial(getattr(Hub, name), hub))
    return hub


# --- the hub ------------------------------------------------------------


def test_the_window_goes_first_then_the_pair_then_the_switch():
    account = FakeAccount()
    hub = hub_over(account, {152: "0", 222: "[0,0]"})

    assert asyncio.run(hub.set_away_mode(START, END)) is True

    assert account.absences == [(START, END)]
    assert hub.log == [
        (id(hub), 222, f"[{START},{END}]"),
        (id(hub), 152, "2"),
    ]
    assert hub.refreshed == 1


def test_a_start_to_come_is_programmed_and_one_reached_is_on():
    """What the vendor app writes, 2026-09-28 : 152 at 2 for a start two days
    away, on a HUB Navizone (1758), the rooms' 100261 following at 2.
    """
    hub = hub_over(FakeAccount(), {152: "0", 222: "[0,0]"})

    asyncio.run(hub.set_away_mode(START, END))
    asyncio.run(hub.set_away_mode(1000, END))

    assert [value for _, capabilityId, value in hub.log if capabilityId == 152] == [
        "2",
        "1",
    ]


def test_clearing_writes_the_empty_pair_and_the_switch_off():
    account = FakeAccount()
    hub = hub_over(account, {227: "1", 226: "[1,2]"})

    asyncio.run(hub.set_away_mode(None, None))

    assert account.absences == [(None, None)]
    assert hub.log == [(id(hub), 226, "[0,0]"), (id(hub), 227, "0")]


def test_every_device_of_the_account_is_switched_with_it():
    """The window is the account's.

    A boiler and a water heater on one account would otherwise disagree about
    whether the house is away.
    """
    account = FakeAccount()
    log = []
    heater = hub_over(account, {227: "0", 226: "[0,0]"}, log=log)
    room = hub_over(account, {100261: "0", 100260: "[0,0]"}, log=log)
    boiler = hub_over(account, {152: "0", 222: "[0,0]"}, [heater, room], log)

    asyncio.run(boiler.set_away_mode(START, END))

    assert account.absences == [(START, END)]
    assert log == [
        (id(boiler), 222, f"[{START},{END}]"),
        (id(boiler), 152, "2"),
        (id(heater), 226, f"[{START},{END}]"),
        (id(heater), 227, "2"),
    ]
    assert room.refreshed == 0
    assert heater.get_away_mode_start() == START


def test_a_device_that_refuses_to_mirror_the_window_is_not_an_error():
    """The setup took the window, and the cloud carries it to the devices.

    A HUB Navizone answers 403 on 152 and still turns programmed (2026-10-05),
    so the error said the opposite of what happened. Every device is still
    asked and refreshed.
    """
    account = FakeAccount()
    log = []
    heater = hub_over(account, {227: "0", 226: "[0,0]"}, log=log)
    boiler = hub_over(account, {152: "0", 222: "[0,0]"}, [heater], log)

    async def offline(capabilityId, value):
        raise HomeAssistantError("offline")

    boiler.set_capability_value = offline

    assert asyncio.run(boiler.set_away_mode(START, END)) is True

    assert account.absences == [(START, END)]
    assert log == [
        (id(heater), 226, f"[{START},{END}]"),
        (id(heater), 227, "2"),
    ]
    assert (boiler.refreshed, heater.refreshed) == (1, 1)


def test_a_refused_window_switches_nothing():
    account = FakeAccount(accepts=False)
    hub = hub_over(account, {152: "0", 222: "[0,0]"})

    assert asyncio.run(hub.set_away_mode(START, END)) is False

    assert hub.log == []


@pytest.mark.parametrize(
    ("start", "end", "valid"),
    [
        (START, END, True),
        (None, END, False),
        (START, None, False),
        (0, 0, False),
        (END, START, False),
        (1000, 2000, False),  # over
        (1000, END, True),  # under way
    ],
)
def test_which_windows_are_worth_sending(start, end, valid):
    assert away_window_is_valid(start, end) is valid


# --- the switch -------------------------------------------------------------


def switch_over(hub):
    return SimpleNamespace(coordinator=hub, _nb_ignore=0, _state=False)


def test_the_switch_sends_the_window_the_pickers_hold():
    hub = hub_over(FakeAccount(), {152: "0", 222: "[0,0]"})
    hub.away_mode_init(START, END)

    asyncio.run(CozytouchAwayModeSwitch.async_turn_on(switch_over(hub)))

    assert hub.account.absences == [(START, END)]


@pytest.mark.parametrize(
    ("turn", "reported"),
    [
        (CozytouchAwayModeSwitch.async_turn_on, "0"),
        (CozytouchAwayModeSwitch.async_turn_off, "1"),
    ],
)
def test_a_refused_switch_reads_the_device_again_at_once(turn, reported):
    """A refusal raises now, and used to skip what ends the switch's guess.

    It kept the state it had guessed for five reads, beside the error saying
    the opposite.
    """
    hub = hub_over(FakeAccount(), {152: reported, 222: "[0,0]"})

    async def refused(start, end):
        raise HomeAssistantError("offline")

    hub.set_away_mode = refused
    switch = switch_over(hub)
    switch._capability = SimpleNamespace(capabilityId=152)
    switch._value_off = "0"
    switch._value_pending = "2"

    with pytest.raises(HomeAssistantError):
        asyncio.run(turn(switch))

    assert CozytouchAwayModeSwitch.is_on.fget(switch) is (reported != "0")


def test_the_switch_replaces_a_window_already_over():
    """It used to send a past window as it was."""
    hub = hub_over(FakeAccount(), {152: "0", 222: "[0,0]"})
    hub.away_mode_init(1000, 2000)

    asyncio.run(CozytouchAwayModeSwitch.async_turn_on(switch_over(hub)))

    [(start, end)] = hub.account.absences
    assert end - start == 2 * 24 * 60 * 60
    assert start > 2000


def test_the_switch_starts_now_when_only_the_end_was_picked():
    """The start picker reads as now until somebody moves it."""
    hub = hub_over(FakeAccount(), {152: "0", 222: "[0,0]"})
    hub.away_mode_init(None, END)

    asyncio.run(CozytouchAwayModeSwitch.async_turn_on(switch_over(hub)))

    [(start, end)] = hub.account.absences
    assert end == END
    assert abs(start - (datetime.now(tz=UTC).timestamp() + 60)) < 5


def test_clearing_puts_the_pickers_back_to_empty():
    hub = hub_over(FakeAccount(), {152: "1", 222: f"[{START},{END}]"})
    hub.away_mode_init(START, END)

    asyncio.run(hub.set_away_mode(None, None))

    assert (hub.get_away_mode_start(), hub.get_away_mode_end()) == (None, None)


def test_the_switch_off_clears_the_window():
    hub = hub_over(FakeAccount(), {152: "1", 222: f"[{START},{END}]"})

    asyncio.run(CozytouchAwayModeSwitch.async_turn_off(switch_over(hub)))

    assert hub.account.absences == [(None, None)]


# --- the service --------------------------------------------------------


def window(**data):
    return services.away_window(
        services.SET_AWAY_MODE_SCHEMA({"entity_id": "switch.away", **data}), NOW
    )


def test_a_start_and_an_end():
    assert window(
        start="2099-10-01T08:00:00+00:00", end="2099-10-08T18:00:00+00:00"
    ) == (START, END)


def test_a_duration_counts_from_the_start():
    assert window(start="2099-10-01T08:00:00+00:00", duration={"days": 7}) == (
        START,
        START + 7 * 24 * 60 * 60,
    )


def test_no_start_means_in_a_minute():
    start, end = window(duration={"hours": 1})

    assert start == int((NOW + timedelta(minutes=1)).timestamp())
    assert end == start + 3600


def test_an_end_or_a_duration_is_required():
    with pytest.raises(vol.Invalid):
        services.SET_AWAY_MODE_SCHEMA({"entity_id": "switch.away"})


def test_not_both_an_end_and_a_duration():
    with pytest.raises(vol.Invalid):
        services.SET_AWAY_MODE_SCHEMA(
            {"entity_id": "switch.away", "end": "2099-10-08", "duration": {"days": 1}}
        )


def test_an_end_before_the_start_is_refused():
    with pytest.raises(ServiceValidationError):
        window(start="2099-10-08T18:00:00+00:00", end="2099-10-01T08:00:00+00:00")


def test_an_absence_already_over_is_refused():
    with pytest.raises(ServiceValidationError):
        window(start="2020-01-01T00:00:00+00:00", end="2020-01-02T00:00:00+00:00")


def registered(hass, name):
    services.async_register_services(hass)
    return hass.services.registered[("cozytouch", name)][0]


def test_the_service_switches_the_absence_on_in_one_call(monkeypatch):
    hub = hub_over(FakeAccount(), {152: "0", 222: "[0,0]"})
    hass = make_hass(monkeypatch, hub)
    call = SimpleNamespace(
        data=services.SET_AWAY_MODE_SCHEMA(
            {
                "entity_id": ["switch.away"],
                "start": "2099-10-01T08:00:00+00:00",
                "end": "2099-10-08T18:00:00+00:00",
            }
        )
    )

    asyncio.run(registered(hass, "set_away_mode")(call))

    assert hub.account.absences == [(START, END)]
    assert (id(hub), 152, "2") in hub.log


def test_two_targets_on_one_account_are_one_write(monkeypatch):
    hub = hub_over(FakeAccount(), {152: "0", 222: "[0,0]"})
    hass = make_hass(monkeypatch, hub)
    call = SimpleNamespace(data={"entity_id": ["switch.a", "switch.b"]})

    asyncio.run(registered(hass, "clear_away_mode")(call))

    assert hub.account.absences == [(None, None)]


def test_a_device_with_no_switch_is_refused(monkeypatch):
    """A room reads the absence ; it has nothing to write it with."""
    hub = hub_over(FakeAccount(), {100261: "0", 100260: "[0,0]"})
    hass = make_hass(monkeypatch, hub)
    call = SimpleNamespace(data={"entity_id": ["switch.room"]})

    with pytest.raises(ServiceValidationError):
        asyncio.run(registered(hass, "clear_away_mode")(call))

    assert hub.account.absences == []


def test_a_refusal_from_atlantic_is_an_error(monkeypatch):
    hub = hub_over(FakeAccount(accepts=False), {152: "1", 222: "[1,2]"})
    hass = make_hass(monkeypatch, hub)
    call = SimpleNamespace(data={"entity_id": ["switch.away"]})

    with pytest.raises(HomeAssistantError):
        asyncio.run(registered(hass, "clear_away_mode")(call))


# --- what the device reports --------------------------------------------


def test_an_absence_set_elsewhere_is_what_the_pickers_follow():
    """The vendor app set this one ; the pickers held something else."""
    hub = hub_over(FakeAccount(), {152: "1", 222: "[1790238529,1790584129]"})
    hub.away_mode_init(START, END)

    hub._follow_reported_away_window()

    assert hub.get_away_mode_start() == 1790238529
    assert hub.get_away_mode_end() == 1790584129


def test_while_off_the_pickers_keep_what_was_picked():
    hub = hub_over(FakeAccount(), {152: "0", 222: "[1000,2000]"})
    hub.away_mode_init(START, END)

    hub._follow_reported_away_window()

    assert (hub.get_away_mode_start(), hub.get_away_mode_end()) == (START, END)


@pytest.mark.parametrize(
    ("reported", "under_way"),
    [
        ({152: "1"}, True),
        ({152: "2"}, False),  # programmed, not started
        ({152: "0"}, False),
        ({100261: "1"}, True),  # a room, which has no switch
        ({100261: "0"}, False),
        ({}, False),
    ],
)
def test_when_an_absence_is_under_way(reported, under_way):
    hub = hub_over(FakeAccount(), reported)
    assert hub.absence_under_way() is under_way


def devices_hub(devices, deviceId):
    return SimpleNamespace(
        _deviceId=deviceId, _account=SimpleNamespace(devices=devices)
    )


def test_a_room_is_air_conditioning_through_its_gateway():
    """Measured : a Navizone room declares no family, its gateway does."""
    devices = [
        {"deviceId": 1, "modelFamily": "Air_Conditioning", "masterDeviceId": None},
        {"deviceId": 2, "modelFamily": None, "masterDeviceId": 1},
    ]
    assert Hub.is_air_conditioning(devices_hub(devices, 2)) is True


def test_a_device_of_another_family_is_not():
    devices = [{"deviceId": 1, "modelFamily": "Heating", "masterDeviceId": None}]
    assert Hub.is_air_conditioning(devices_hub(devices, 1)) is False
