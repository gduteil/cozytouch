"""The schedule services : what gets written, and what is read back.

Nothing covered `services.py` before, and it is the one place in the
integration where the user hands us a value that has to be reshaped before it
reaches the device. The matrix it builds is positional -- ten pairs of
minutes-since-midnight and a temperature, padded with zeroes -- so a slot
sorted wrong or a pad written short is not a visible bug, it is a heating
program that quietly does something else.

The round-trip case is the one to keep : `get_schedule` only earns its place
if what it hands back can be written again unchanged.
"""

import asyncio
from datetime import time
import json
from types import SimpleNamespace

from _harness import TRANSLATIONS
import pytest
import voluptuous as vol

from custom_components.cozytouch import services
from custom_components.cozytouch.const import PROGRAM_DAYS
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import ServiceValidationError

SUBENTRY_ID = "sub-1"

PADDING = ",[0,0]" * 8


def days(first, value="[[0,17]" + PADDING + "]"):
    """The seven days of one block, so a hub reads as holding that program."""
    return {first + day: value for day in range(7)}


class FakeHub:
    """A hub that remembers what was written to it."""

    def __init__(self, values=None):
        self.values = values or {}
        self.written = []
        self.refreshed = 0

    def get_capability_value(self, capabilityId, defaultIfNotExist="0"):
        return self.values.get(capabilityId, defaultIfNotExist)

    async def set_capability_value(self, capabilityId, value):
        self.written.append((capabilityId, value))

    async def async_request_refresh(self):
        self.refreshed += 1


class FakeServices:
    """Records registrations instead of running a service bus."""

    def __init__(self):
        self.registered = {}

    def has_service(self, domain, service):
        return (domain, service) in self.registered

    def async_register(self, domain, service, func, schema=None, **kwargs):
        self.registered[(domain, service)] = (func, schema, kwargs)


def make_hass(monkeypatch, hub, platform="cozytouch", domain="cozytouch",
              state=ConfigEntryState.LOADED, registry_entry=...):
    """A stand-in exposing only what the services read.

    The entity registry is patched on our own module rather than seeded into
    hass.data : er.async_get is a singleton cached on the hass object, and a
    SimpleNamespace is unhashable, so the real lookup cannot be reached with a
    fake at all.
    """
    if registry_entry is ...:
        registry_entry = SimpleNamespace(
            config_entry_id="entry",
            config_subentry_id=SUBENTRY_ID,
            platform=platform,
        )

    monkeypatch.setattr(
        services,
        "er",
        SimpleNamespace(
            async_get=lambda hass: SimpleNamespace(
                async_get=lambda entity_id: registry_entry
            )
        ),
    )

    # A device is a subentry of its account, and the hub driving it is keyed
    # on that subentry -- which is what `_resolve_hub` looks up.
    entry = SimpleNamespace(
        domain=domain,
        state=state,
        runtime_data=SimpleNamespace(hubs={SUBENTRY_ID: hub}),
    )
    return SimpleNamespace(
        services=FakeServices(),
        config_entries=SimpleNamespace(async_get_entry=lambda entry_id: entry),
    )


def registered(hass, name):
    """The handler async_register_services put on the bus."""
    services.async_register_services(hass)
    return hass.services.registered[("cozytouch", name)][0]


def call_with(**data):
    """A ServiceCall stand-in whose data went through the real schema."""
    schema = (
        services.GET_SCHEDULE_SCHEMA
        if "slots" not in data
        else services.SET_SCHEDULE_SCHEMA
    )
    return SimpleNamespace(data=schema(data))


# --- writing -----------------------------------------------------------


def test_a_program_is_stored_as_minutes_since_midnight():
    """The device indexes the day in minutes, not in hours and minutes."""
    value = services.build_matrix(
        [
            {"time": time(0, 0), "temperature": 17},
            {"time": time(6, 30), "temperature": 21},
        ]
    )

    assert value == "[[0,17],[390,21]" + PADDING + "]"


def test_the_matrix_is_padded_to_the_ten_slots_the_device_stores():
    """A short matrix leaves the tail of the day at whatever was there."""
    value = services.build_matrix([{"time": time(0, 0), "temperature": 19}])

    assert len(json.loads(value)) == 10


def test_the_slots_are_sorted_before_they_are_written():
    """The list is positional : out of order it programs the wrong hours."""
    value = services.build_matrix(
        [
            {"time": time(22, 0), "temperature": 17},
            {"time": time(0, 0), "temperature": 19},
            {"time": time(7, 0), "temperature": 21},
        ]
    )

    assert json.loads(value)[:3] == [[0, 19], [420, 21], [1320, 17]]


def test_two_slots_at_the_same_time_are_refused():
    """One of them would win silently, and not always the same one."""
    with pytest.raises(ServiceValidationError):
        services.build_matrix(
            [
                {"time": time(0, 0), "temperature": 19},
                {"time": time(7, 0), "temperature": 21},
                {"time": time(7, 0), "temperature": 22},
            ]
        )


def test_a_day_that_does_not_start_at_midnight_is_refused():
    """The hours before the first slot would have no target temperature."""
    with pytest.raises(ServiceValidationError):
        services.build_matrix([{"time": time(7, 0), "temperature": 21}])


def test_a_whole_degree_is_written_as_an_integer():
    """21.0 in the payload is not what the app sends, 21 is."""
    value = services.build_matrix([{"time": time(0, 0), "temperature": 21.0}])

    assert value.startswith("[[0,21],")


def test_a_program_with_no_slots_is_refused_rather_than_raising():
    """The first-slot check indexes blind; the service is not the only caller."""
    with pytest.raises(ServiceValidationError):
        services.build_matrix([])


# --- what the form sends -----------------------------------------------


@pytest.mark.parametrize("written", ["07:00", "07:00:00"])
def test_the_time_the_selector_returns_is_accepted(written):
    """The schema'd object selector emits seconds, a YAML author does not."""
    data = services.SET_SCHEDULE_SCHEMA(
        {
            "entity_id": ["climate.salon"],
            "program": "heating",
            "days": ["monday"],
            "slots": [
                {"time": "00:00", "temperature": 19},
                {"time": written, "temperature": 21},
            ],
        }
    )

    assert json.loads(services.build_matrix(data["slots"]))[1] == [420, 21]


def test_a_single_slot_sent_as_a_mapping_is_still_a_list():
    """Without multiple:true a frontend sends the object on its own."""
    data = services.SET_SCHEDULE_SCHEMA(
        {
            "entity_id": ["climate.salon"],
            "program": "heating",
            "days": ["monday"],
            "slots": {"time": "00:00", "temperature": 19},
        }
    )

    assert data["slots"] == [{"time": time(0, 0), "temperature": 19.0}]


# --- day groups ---------------------------------------------------------


@pytest.mark.parametrize(
    ("group", "expected"),
    [
        ("all", list(PROGRAM_DAYS)),
        ("weekdays", list(PROGRAM_DAYS[:5])),
        ("weekend", ["saturday", "sunday"]),
    ],
)
def test_a_group_stands_for_the_days_it_covers(group, expected):
    """The shortcut is expanded here so a YAML automation gets it too."""
    assert services.expand_days([group]) == expected


def test_the_groups_and_the_literal_days_can_be_mixed():
    """Whatever the picker was clicked in, the write order is the week's."""
    assert services.expand_days(["weekend", "monday"]) == [
        "monday",
        "saturday",
        "sunday",
    ]


def test_a_day_named_twice_is_written_once():
    """Two writes to one capability is two calls to the cloud for nothing."""
    assert len(services.expand_days(["all", "monday"])) == 7


@pytest.mark.parametrize("days", [[], ["someday"]])
def test_a_day_list_that_names_nothing_real_is_refused(days):
    """An empty list used to pass the length check after expansion."""
    with pytest.raises(vol.Invalid):
        services.SET_SCHEDULE_SCHEMA(
            {
                "entity_id": ["climate.salon"],
                "program": "heating",
                "days": days,
                "slots": [{"time": "00:00", "temperature": 19}],
            }
        )


# --- the device's own slot limit ---------------------------------------


def test_a_device_that_advertises_fewer_slots_is_believed():
    """Capability 306 is the only thing that knows the real ceiling."""
    assert services.slot_limit(FakeHub({306: "5"})) == 5


@pytest.mark.parametrize("value", [None, "", "0", "1", "many", "[5]", "99"])
def test_an_unreadable_slot_count_leaves_the_ten_that_work(value):
    """306 is self-describing and unverified : it may only tighten the check,
    never widen it and never break a write that works today.
    """
    assert services.slot_limit(FakeHub({306: value})) == services.MAX_SLOTS


# --- reading back --------------------------------------------------------


def test_the_padding_is_not_read_back_as_a_midnight_slot():
    """Eight [0,0] pairs are an empty tail, not eight programmed midnights."""
    slots = services.parse_slots("[[0,17],[390,21]" + PADDING + "]")

    assert slots == [
        {"time": "00:00", "temperature": 17},
        {"time": "06:30", "temperature": 21},
    ]


def test_a_real_midnight_slot_survives_being_read_back():
    """It is the pair the padding rule has to be told apart from : a slot at
    midnight carries a setpoint, padding carries a zero.
    """
    assert services.parse_slots("[[0,17]" + PADDING + ",[0,0]]")[0] == {
        "time": "00:00",
        "temperature": 17,
    }


@pytest.mark.parametrize("value", [None, "", "0", "not json", "{}"])
def test_a_device_that_stores_nothing_reads_as_no_slots(value):
    """A missing program is an empty day, not a failed service call."""
    assert services.parse_slots(value) == []


def test_a_week_that_is_read_back_can_be_written_again_unchanged():
    """The whole promise of get_schedule : its answer is set_schedule's input."""
    stored = "[[0,17],[390,21],[1320,17]" + ",[0,0]" * 7 + "]"

    slots = services.parse_slots(stored)
    data = services.SET_SCHEDULE_SCHEMA(
        {
            "entity_id": ["climate.salon"],
            "program": "heating",
            "days": ["monday"],
            "slots": slots,
        }
    )

    assert services.build_matrix(data["slots"]) == stored


# --- resolving the hub ---------------------------------------------------


def test_an_entity_that_does_not_exist_is_named_in_the_error(monkeypatch):
    """Renaming an entity does not change its id, which is the usual cause."""
    hass = make_hass(monkeypatch, FakeHub(), registry_entry=None)

    with pytest.raises(ServiceValidationError, match=r"climate\.nope"):
        services._resolve_hub(hass, "climate.nope")


def test_an_entity_from_another_integration_says_whose_it_is(monkeypatch):
    """Otherwise it reads as our bug rather than as the wrong entity."""
    hass = make_hass(monkeypatch, FakeHub(), platform="overkiz", domain="overkiz")

    with pytest.raises(ServiceValidationError, match="overkiz"):
        services._resolve_hub(hass, "climate.salon")


def test_an_entry_that_is_not_loaded_says_so_rather_than_looking_missing(
    monkeypatch,
):
    """The old hass.data lookup conflated this with an unknown entity."""
    hass = make_hass(
        monkeypatch, FakeHub(), state=ConfigEntryState.SETUP_RETRY
    )

    with pytest.raises(ServiceValidationError, match="not loaded"):
        services._resolve_hub(hass, "climate.salon")


# --- the handlers --------------------------------------------------------


def test_writing_a_week_touches_one_capability_per_day(monkeypatch):
    """Monday is 196 and the block runs in calendar order from there."""
    hub = FakeHub(days(196))
    hass = make_hass(monkeypatch, hub)
    handler = registered(hass, "set_schedule")

    asyncio.run(
        handler(
            call_with(
                entity_id=["climate.salon"],
                program="heating",
                days=["weekdays"],
                slots=[{"time": "00:00", "temperature": 19}],
            )
        )
    )

    assert [capabilityId for capabilityId, _ in hub.written] == [
        196,
        197,
        198,
        199,
        200,
    ]
    assert len({value for _, value in hub.written}) == 1
    assert hub.refreshed == 1


def test_the_cooling_program_is_the_second_block_of_seven(monkeypatch):
    """203 is where the app writes "Refroidissement"."""
    hub = FakeHub(days(203))
    hass = make_hass(monkeypatch, hub)
    handler = registered(hass, "set_schedule")

    asyncio.run(
        handler(
            call_with(
                entity_id=["climate.salon"],
                program="cooling",
                days=["sunday"],
                slots=[{"time": "00:00", "temperature": 26}],
            )
        )
    )

    assert hub.written[0][0] == 209


def test_more_slots_than_the_device_holds_are_refused_by_name(monkeypatch):
    """Past its own limit the cloud truncates the day without saying so."""
    hass = make_hass(monkeypatch, FakeHub({306: "2", **days(196)}))
    handler = registered(hass, "set_schedule")

    call = call_with(
        entity_id=["climate.salon"],
        program="heating",
        days=["monday"],
        slots=[
            {"time": "00:00", "temperature": 19},
            {"time": "07:00", "temperature": 21},
            {"time": "22:00", "temperature": 17},
        ],
    )

    with pytest.raises(ServiceValidationError, match="2 slots"):
        asyncio.run(handler(call))


def test_reading_a_week_is_keyed_by_the_entity_it_came_from(monkeypatch):
    """A target can select several entities; the answer has to say which."""
    stored = "[[0,17],[390,21]" + PADDING + "]"
    hub = FakeHub({196 + index: stored for index in range(7)})
    hass = make_hass(monkeypatch, hub)
    handler = registered(hass, "get_schedule")

    response = asyncio.run(
        handler(call_with(entity_id=["climate.salon"], program="heating"))
    )

    assert list(response) == ["climate.salon"]
    assert response["climate.salon"]["program"] == "heating"
    assert list(response["climate.salon"]["days"]) == list(PROGRAM_DAYS)
    assert response["climate.salon"]["days"]["monday"][1]["time"] == "06:30"


def test_reading_a_program_the_device_does_not_have_says_so(monkeypatch):
    """An empty week reads as "no program set", which is a different thing."""
    hass = make_hass(monkeypatch, FakeHub())
    handler = registered(hass, "get_schedule")

    with pytest.raises(ServiceValidationError, match="203 or 100327"):
        asyncio.run(
            handler(call_with(entity_id=["climate.salon"], program="cooling"))
        )


def test_the_read_service_answers_rather_than_only_acting(monkeypatch):
    """Without SupportsResponse the caller gets None and no way to ask again."""
    hass = make_hass(monkeypatch, FakeHub())
    services.async_register_services(hass)

    kwargs = hass.services.registered[("cozytouch", "get_schedule")][2]

    assert kwargs["supports_response"] is SupportsResponse.ONLY


def test_the_services_are_registered_once_for_every_config_entry(monkeypatch):
    """Two Cozytouch accounts set up the same integration twice."""
    hass = make_hass(monkeypatch, FakeHub())

    services.async_register_services(hass)
    services.async_register_services(hass)

    assert sorted(name for _, name in hass.services.registered) == [
        "clear_away_mode",
        "get_schedule",
        "set_away_mode",
        "set_schedule",
    ]


# --- the strings behind the form ----------------------------------------


def service_keys(path):
    """Every key the UI looks up for the two services."""
    with open(path, encoding="utf-8") as handle:
        content = json.load(handle)

    keys = set()
    for name, service in content["services"].items():
        keys.add(name)
        keys |= {f"{name}.{field}" for field in service.get("fields", {})}
    for name, selector in content["selector"].items():
        for group in ("options", "fields"):
            keys |= {f"{name}.{group}.{key}" for key in selector.get(group, {})}
    return keys


@pytest.mark.parametrize("path", TRANSLATIONS[1:])
def test_the_service_strings_cover_the_same_keys(path):
    """Hassfest does not read fr.json, and skips these checks entirely for a
    custom integration : a missing key here shows the raw id to the user.
    """
    assert service_keys(path) == service_keys(TRANSLATIONS[0])


# --- a period laid over a day -------------------------------------------


DAY = [
    {"time": "00:00", "temperature": 26},
    {"time": "07:00", "temperature": 24},
    {"time": "22:00", "temperature": 26},
]


def clock(slots):
    """The slots as pairs, so a case reads like the program it describes."""
    return [(slot["time"].isoformat(timespec="minutes"), slot["temperature"])
            for slot in slots]


def test_a_period_puts_back_what_ran_after_it():
    assert clock(services.apply_period(DAY, "09:00", "17:00", 21)) == [
        ("00:00", 26),
        ("07:00", 24),
        ("09:00", 21),
        # 24 is what the day held at 17:00 before the period was laid over it.
        ("17:00", 24),
        ("22:00", 26),
    ]


def test_a_period_replaces_the_slots_it_covers():
    """Otherwise a slot inside the period would take charge in the middle."""
    assert clock(services.apply_period(DAY, "06:00", "23:00", 20)) == [
        ("00:00", 26),
        ("06:00", 20),
        ("23:00", 26),
    ]


def test_a_period_ending_at_midnight_ends_the_day():
    assert clock(services.apply_period(DAY, "22:00", "00:00", 18)) == [
        ("00:00", 26),
        ("07:00", 24),
        ("22:00", 18),
    ]


def test_a_period_starting_at_midnight_keeps_the_day_startable():
    """00:00 is the one slot build_matrix insists on, so it is replaced."""
    assert clock(services.apply_period(DAY, "00:00", "07:00", 20)) == [
        ("00:00", 20),
        ("07:00", 24),
        ("22:00", 26),
    ]


def test_a_period_ending_where_the_day_already_turns_writes_one_slot():
    """A second slot at 07:00 is what build_matrix refuses outright."""
    assert clock(services.apply_period(DAY, "05:00", "07:00", 21)) == [
        ("00:00", 26),
        ("05:00", 21),
        ("07:00", 24),
        ("22:00", 26),
    ]


def test_a_period_asking_for_what_already_runs_costs_no_slot():
    """A day holds ten, so a slot that changes nothing is one too few."""
    assert clock(services.apply_period(DAY, "09:00", "17:00", 24)) == [
        ("00:00", 26),
        ("07:00", 24),
        ("22:00", 26),
    ]


def test_what_a_period_produces_can_be_written():
    """The point of the helper : build_matrix has to accept its output."""
    slots = services.apply_period(DAY, "09:00", "17:00", 21)
    assert json.loads(services.build_matrix(slots))[:3] == [
        [0, 26],
        [420, 24],
        [540, 21],
    ]


def test_a_period_that_ends_before_it_starts_is_refused():
    with pytest.raises(ServiceValidationError):
        services.apply_period(DAY, "17:00", "09:00", 21)
