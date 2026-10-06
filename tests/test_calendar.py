"""The weekly program, as a week.

The program is what these devices are actually scheduled by -- it keeps running
when Home Assistant is off, which is why the two schedule services exist -- and
what it looked like from Home Assistant was seven strings, one per day,
formatted for a dashboard. `get_schedule` made it machine-readable;
`calendar.py` makes it a week you can look at, and something `calendar`
triggers can fire on : an event start *is* the moment the program moves to its
next setpoint.

Turning seven stored days into dated events is where this can go wrong, so that
is what these pin: which day of the week a capability belongs to, that a slot
runs until the next one rather than for some fixed length, that the last of the
day runs to midnight, and that a slot which began before the window asked for
is still the one in charge at its start.

The platform is driven directly with a hub stand-in, the way
tests/test_sensor_metadata.py does. `dt_util.DEFAULT_TIME_ZONE` is UTC in a
test process, which is what makes the expected datetimes below readable.
"""

import asyncio
import datetime
import json
from types import SimpleNamespace

from _harness import SUBENTRY_ID, entry_over, set_up
import pytest

from custom_components.cozytouch import calendar as calendar_platform
from custom_components.cozytouch.calendar import (
    PROGRAM_BLOCKS,
    CozytouchProgramCalendar,
)
from custom_components.cozytouch.const import DOMAIN
from custom_components.cozytouch.infos import ModelInfos
from homeassistant.exceptions import HomeAssistantError
from homeassistant.util import dt as dt_util

# Monday, so that a range starting here lines up with the first capability of
# a block; the fixtures below rely on it.
MONDAY = datetime.date(2026, 8, 24)
TUESDAY = datetime.date(2026, 8, 25)
NEXT_MONDAY = datetime.date(2026, 8, 31)

HEATING_MONDAY = 196
COOLING_MONDAY = 203
HOT_WATER_MONDAY = 237

PADDING = ",[0,0]" * 8


def stored(*slots):
    """A day as the device stores it: ten slots, the unused ones [0,0].

    json.dumps rather than str(), which would quote a string setpoint the
    Python way and make the whole matrix unparsable -- hiding the case a test
    below is about behind an earlier failure.
    """
    entries = [[minute, temperature] for minute, temperature in slots]
    entries += [[0, 0]] * (10 - len(entries))

    return json.dumps(entries, separators=(",", ":"))


def at(day, hour, minute=0):
    return datetime.datetime(
        day.year, day.month, day.day, hour, minute, tzinfo=dt_util.DEFAULT_TIME_ZONE
    )


def make_hub(values):
    """A hub answering with these capability values and nothing else."""
    return SimpleNamespace(
        get_capability_value=lambda capabilityId, default="0": values.get(
            capabilityId, default
        ),
        get_model_infos=lambda: ModelInfos(name="Air Conditioner (Salon)"),
        get_serial_number=lambda: "1234-5678-0000",
        get_software_version=lambda: "1.2.3",
        get_via_device=lambda: None,
    )


def week(first_capability, day_program):
    """The same program every day of one block, so a weekday can be told apart."""
    return {first_capability + day: day_program for day in range(7)}


def build(values):
    """Run the calendar platform and return the entities it built."""
    return set_up(calendar_platform, entry_over(make_hub(values)))


def calendar_over(day_programs, program="heating", first=None):
    """One calendar, over a block whose days are given by weekday index."""
    first = PROGRAM_BLOCKS[program][0] if first is None else first
    values = {first + day: value for day, value in day_programs.items()}

    return CozytouchProgramCalendar(
        coordinator=make_hub(values),
        config_uniq_id=SUBENTRY_ID,
        program=program,
        first=first,
    )


def events(calendar, start, end):
    return asyncio.run(calendar.async_get_events(None, start, end))


# ------------------------------------------------------------ which entities


def test_a_device_reporting_two_blocks_gets_two():
    built = build(
        week(HEATING_MONDAY, stored((0, 17))) | week(COOLING_MONDAY, stored((0, 26)))
    )

    assert sorted(entity.translation_key for entity in built) == [
        "cooling_program",
        "heating_program",
    ]


def test_a_device_reporting_one_block_gets_one():
    built = build(week(HEATING_MONDAY, stored((0, 17))))

    assert [entity.translation_key for entity in built] == ["heating_program"]


def test_a_water_heater_gets_its_hot_water_program():
    """237-243, which the prog sensors already render and the services refuse
    to write: reading a block is not the same risk as writing one.
    """
    built = build(week(HOT_WATER_MONDAY, stored((0, 55))))

    assert [entity.translation_key for entity in built] == ["hot_water_program"]


def test_a_device_holding_all_three_programs_gets_three():
    built = build(
        week(HEATING_MONDAY, stored((0, 17)))
        | week(COOLING_MONDAY, stored((0, 26)))
        | week(HOT_WATER_MONDAY, stored((0, 55)))
    )

    assert sorted(entity.translation_key for entity in built) == [
        "cooling_program",
        "heating_program",
        "hot_water_program",
    ]


def test_a_device_reporting_no_program_gets_no_calendar():
    assert build({}) == []


def test_half_a_block_is_not_a_calendar():
    """A gap would read as "nothing scheduled that day" rather than missing data."""
    partial = week(HEATING_MONDAY, stored((0, 17)))
    del partial[HEATING_MONDAY + 3]

    assert build(partial) == []


# ------------------------------------------------------------------ the week


def test_a_slot_runs_until_the_next_one():
    """Not for some fixed length: the next slot is what ends a setpoint."""
    calendar = calendar_over({0: stored((0, 17), (390, 21), (1320, 17))})

    day = events(calendar, at(MONDAY, 0), at(TUESDAY, 0))

    assert [(event.start, event.end) for event in day] == [
        (at(MONDAY, 0), at(MONDAY, 6, 30)),
        (at(MONDAY, 6, 30), at(MONDAY, 22)),
        (at(MONDAY, 22), at(TUESDAY, 0)),
    ]


def test_the_last_slot_of_the_day_runs_to_midnight():
    """Where the next day's first slot takes over -- set_schedule refuses a day
    that does not start at 00:00, so nothing is left uncovered.
    """
    calendar = calendar_over({0: stored((0, 17), (1320, 21))})

    day = events(calendar, at(MONDAY, 0), at(TUESDAY, 0))

    assert day[-1].end == at(TUESDAY, 0)


def test_the_setpoint_is_the_summary():
    calendar = calendar_over({0: stored((0, 17), (390, 20.5))})

    day = events(calendar, at(MONDAY, 0), at(TUESDAY, 0))

    assert [event.summary for event in day] == ["17 °C", "20.5 °C"]


def test_each_day_reads_its_own_capability():
    """Monday is the first of the block, and nothing else is."""
    calendar = calendar_over({0: stored((0, 17)), 1: stored((0, 21))})

    both = events(calendar, at(MONDAY, 0), at(TUESDAY, 23))

    assert [(event.start.date(), event.summary) for event in both] == [
        (MONDAY, "17 °C"),
        (TUESDAY, "21 °C"),
    ]


def test_the_week_repeats():
    """A program is a week, not a list of dated events."""
    calendar = calendar_over({0: stored((0, 17))})

    fortnight = events(calendar, at(MONDAY, 0), at(NEXT_MONDAY, 23))

    assert [event.start.date() for event in fortnight] == [MONDAY, NEXT_MONDAY]


def test_a_slot_that_began_before_the_window_is_still_returned():
    """It is the one running at the start of the range: dropping it would leave
    the range looking unscheduled until the next setpoint.
    """
    calendar = calendar_over({0: stored((0, 17), (390, 21))})

    from_noon = events(calendar, at(MONDAY, 12), at(MONDAY, 13))

    assert [event.summary for event in from_noon] == ["21 °C"]
    assert from_noon[0].start == at(MONDAY, 6, 30)


def test_padding_ends_the_day():
    """[0,0] is padding; one real slot is one event, not one plus nine at midnight."""
    calendar = calendar_over({0: stored((0, 17))})

    day = events(calendar, at(MONDAY, 0), at(TUESDAY, 0))

    assert len(day) == 1
    assert (day[0].start, day[0].end) == (at(MONDAY, 0), at(TUESDAY, 0))


def test_a_real_midnight_slot_is_not_padding():
    """Both members zero is padding; a genuine 00:00 slot carries a setpoint."""
    calendar = calendar_over({0: "[[0,17]" + PADDING + ",[0,0]]"})

    day = events(calendar, at(MONDAY, 0), at(TUESDAY, 0))

    assert [event.summary for event in day] == ["17 °C"]


def test_slots_stored_out_of_order_are_put_back_in_order():
    """Or an evening setpoint would end up in charge of the morning."""
    calendar = calendar_over({0: stored((390, 21), (0, 17))})

    day = events(calendar, at(MONDAY, 0), at(TUESDAY, 0))

    assert [event.summary for event in day] == ["17 °C", "21 °C"]


@pytest.mark.parametrize("unreadable", ["", "null", "not json", "[[0]]", None])
def test_a_day_that_says_nothing_readable_has_no_events(unreadable):
    calendar = calendar_over({0: unreadable})

    assert events(calendar, at(MONDAY, 0), at(TUESDAY, 0)) == []


@pytest.mark.parametrize(
    "slot",
    [
        # A minute count past the end of the day, which time() refuses.
        (2000, 21),
        # A setpoint that is not a number, which the %g summary refuses.
        (390, "warm"),
    ],
)
def test_one_unusable_slot_does_not_take_the_day_with_it(slot):
    """Neither has been captured; both would otherwise raise through the
    platform and leave the week with no events at all.
    """
    calendar = calendar_over({0: stored((0, 17), slot)})

    day = events(calendar, at(MONDAY, 0), at(TUESDAY, 0))

    assert [event.summary for event in day] == ["17 °C"]


# --------------------------------------------------------- what is running now


def test_the_current_event_is_the_slot_covering_now(monkeypatch):
    calendar = calendar_over({0: stored((0, 17), (390, 21), (1320, 17))})
    monkeypatch.setattr(calendar_platform.dt_util, "now", lambda: at(MONDAY, 12))

    assert calendar.event.summary == "21 °C"
    assert calendar.event.start == at(MONDAY, 6, 30)


def test_the_current_event_can_have_started_yesterday(monkeypatch):
    """Sunday's last slot is what holds until monday's first one."""
    calendar = calendar_over({6: stored((0, 17), (1320, 15)), 0: stored((0, 21))})
    monkeypatch.setattr(
        calendar_platform.dt_util, "now", lambda: at(datetime.date(2026, 8, 30), 23, 30)
    )

    assert calendar.event.summary == "15 °C"


def test_a_slot_starting_exactly_now_is_the_current_event(monkeypatch):
    """The window reaches past now for this: the overlap test is half-open, so
    a window ending at now would drop the slot that starts on the boundary and
    report nothing running at the one moment the program changed.
    """
    calendar = calendar_over({0: stored((0, 17), (390, 21))})
    monkeypatch.setattr(calendar_platform.dt_util, "now", lambda: at(MONDAY, 6, 30))

    assert calendar.event.summary == "21 °C"


def test_no_program_means_nothing_running(monkeypatch):
    calendar = calendar_over({0: stored()})
    monkeypatch.setattr(calendar_platform.dt_util, "now", lambda: at(MONDAY, 12))

    assert calendar.event is None


# --------------------------------------------------------------- the identity


@pytest.mark.parametrize("program", list(PROGRAM_BLOCKS))
def test_the_calendars_are_keyed_on_the_entry_and_the_block(program):
    calendar = calendar_over({0: stored((0, 17))}, program=program)

    assert calendar.unique_id == f"{DOMAIN}_{SUBENTRY_ID}_{program}_program"


@pytest.mark.parametrize(
    ("program", "first"),
    [
        (program, first)
        for program, firsts in PROGRAM_BLOCKS.items()
        for first in firsts
    ],
)
def test_monday_is_the_first_capability_of_every_block(program, first):
    """Every run is seven consecutive ids, monday first, wherever it starts."""
    hub = make_hub({first + day: stored((0, 17)) for day in range(7)})
    entities = set_up(calendar_platform, entry_over(hub))

    assert [entity.translation_key for entity in entities] == [f"{program}_program"]


def test_a_calendar_lands_on_the_same_device_as_the_entities():
    calendar = calendar_over({0: stored((0, 17))})

    assert calendar.device_info["identifiers"] == {(DOMAIN, SUBENTRY_ID)}


# ------------------------------------------------------------------- writing
#
# An event is a slot, and every edit lands on that weekday for good, since the
# week repeats. These pin what an edit does to the matrix that gets written --
# including the second slot a drawn block needs to put back what ran after it.


def writable(day_programs, program="heating", extra=None):
    """A calendar whose hub records what the edit wrote."""
    first = PROGRAM_BLOCKS[program][0]
    values = {first + day: value for day, value in day_programs.items()}
    values.update(extra or {})
    written = {}

    hub = make_hub(values)

    async def set_capability_value(capabilityId, value):
        written[capabilityId] = value
        values[capabilityId] = value

    hub.set_capability_value = set_capability_value
    hub.async_request_refresh = _noop

    calendar = CozytouchProgramCalendar(
        coordinator=hub, config_uniq_id=SUBENTRY_ID, program=program, first=first
    )

    return calendar, written


async def _noop():
    return None


def test_a_created_event_adds_its_slot_and_restores_what_followed():
    calendar, written = writable({0: stored((0, 17), (480, 20))})

    asyncio.run(
        calendar.async_create_event(
            dtstart=at(MONDAY, 10), dtend=at(MONDAY, 12), summary="22 °C"
        )
    )

    assert json.loads(written[HEATING_MONDAY])[:4] == [
        [0, 17],
        [480, 20],
        [600, 22],
        [720, 20],
    ]


def test_an_event_running_to_midnight_leaves_the_day_ending_on_it():
    calendar, written = writable({0: stored((0, 17))})

    asyncio.run(
        calendar.async_create_event(
            dtstart=at(MONDAY, 22), dtend=at(TUESDAY, 0), summary="16"
        )
    )

    assert json.loads(written[HEATING_MONDAY])[:3] == [[0, 17], [1320, 16], [0, 0]]


def test_creating_over_an_existing_slot_replaces_it():
    calendar, written = writable({1: stored((0, 17), (600, 21))})

    asyncio.run(
        calendar.async_create_event(
            dtstart=at(TUESDAY, 10), dtend=at(TUESDAY, 0), summary="19 °C"
        )
    )

    assert json.loads(written[HEATING_MONDAY + 1])[:3] == [[0, 17], [600, 19], [0, 0]]


def test_an_edit_lands_on_the_weekday_of_the_event():
    calendar, written = writable({0: stored((0, 17)), 1: stored((0, 17))})

    asyncio.run(
        calendar.async_create_event(
            dtstart=at(TUESDAY, 7), dtend=at(TUESDAY, 0), summary="21"
        )
    )

    assert list(written) == [HEATING_MONDAY + 1]


def test_a_deleted_event_drops_its_slot():
    calendar, written = writable({0: stored((0, 17), (420, 21), (1320, 18))})
    uid = events(calendar, at(MONDAY, 0), at(TUESDAY, 0))[1].uid

    asyncio.run(calendar.async_delete_event(uid))

    assert json.loads(written[HEATING_MONDAY])[:3] == [[0, 17], [1320, 18], [0, 0]]


def test_the_midnight_slot_cannot_be_deleted():
    """It is what gives the beginning of the day a setpoint."""
    calendar, written = writable({0: stored((0, 17), (420, 21))})
    uid = events(calendar, at(MONDAY, 0), at(TUESDAY, 0))[0].uid

    with pytest.raises(HomeAssistantError):
        asyncio.run(calendar.async_delete_event(uid))

    assert written == {}


def test_a_moved_event_leaves_its_old_day_and_lands_on_the_new_one():
    calendar, written = writable({0: stored((0, 17), (420, 21)), 1: stored((0, 17))})
    uid = events(calendar, at(MONDAY, 0), at(TUESDAY, 0))[1].uid

    asyncio.run(
        calendar.async_update_event(
            uid,
            {"dtstart": at(TUESDAY, 9), "dtend": at(TUESDAY, 0), "summary": "21 °C"},
        )
    )

    assert json.loads(written[HEATING_MONDAY])[:2] == [[0, 17], [0, 0]]
    assert json.loads(written[HEATING_MONDAY + 1])[:3] == [
        [0, 17],
        [540, 21],
        [0, 0],
    ]


def test_retitling_the_midnight_slot_changes_its_setpoint():
    """Which the delete path refuses, so the update must not take it."""
    calendar, written = writable({0: stored((0, 17))})
    uid = events(calendar, at(MONDAY, 0), at(TUESDAY, 0))[0].uid

    asyncio.run(
        calendar.async_update_event(
            uid, {"dtstart": at(MONDAY, 0), "dtend": at(TUESDAY, 0), "summary": "19 °C"}
        )
    )

    assert json.loads(written[HEATING_MONDAY])[:2] == [[0, 19], [0, 0]]


def test_an_event_with_no_temperature_in_its_title_is_refused():
    calendar, written = writable({0: stored((0, 17))})

    with pytest.raises(HomeAssistantError):
        asyncio.run(
            calendar.async_create_event(
                dtstart=at(MONDAY, 10), dtend=at(TUESDAY, 0), summary="Morning"
            )
        )

    assert written == {}


def test_a_day_is_refused_past_the_slots_the_device_holds():
    day = stored(*((hour * 60, 20) for hour in range(5)))
    calendar, written = writable({0: day}, extra={306: "5"})

    with pytest.raises(HomeAssistantError):
        asyncio.run(
            calendar.async_create_event(
                dtstart=at(MONDAY, 12), dtend=at(TUESDAY, 0), summary="21"
            )
        )

    assert written == {}


def test_only_a_writable_block_offers_editing():
    """Writing the hot-water block waits on a capture, as set_schedule does."""
    assert calendar_over({0: stored((0, 17))}).supported_features
    assert not calendar_over(
        {0: stored((0, 50))}, program="hot_water"
    ).supported_features


def test_a_day_that_would_not_begin_at_midnight_is_refused():
    """build_matrix's rule, reached from the card rather than from the service."""
    calendar, written = writable({0: stored()})

    with pytest.raises(HomeAssistantError):
        asyncio.run(
            calendar.async_create_event(
                dtstart=at(MONDAY, 10), dtend=at(TUESDAY, 0), summary="21"
            )
        )

    assert written == {}


def test_the_midnight_slot_cannot_be_moved_to_another_day():
    """Moving is a delete on the old day, and that day still has to start."""
    calendar, written = writable({0: stored((0, 17)), 1: stored((0, 17))})
    uid = events(calendar, at(MONDAY, 0), at(TUESDAY, 0))[0].uid

    with pytest.raises(HomeAssistantError):
        asyncio.run(
            calendar.async_update_event(
                uid,
                {"dtstart": at(TUESDAY, 6), "dtend": at(TUESDAY, 0), "summary": "17"},
            )
        )

    assert written == {}
