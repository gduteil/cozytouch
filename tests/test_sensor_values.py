"""What the sensor value builders return, character for character.

`sensor.py` is where a capability value becomes the string somebody reads on a
dashboard, and it had no tests at all. These pin the formatting as it stands,
so that changing one has to be a decision rather than a side effect.

They exist because a lint pass rewrote six `%`-format expressions in this file
into f-strings. That is exactly the kind of edit that looks free and silently
turns 21 into 21.0 on somebody's dashboard, and nothing here would have caught
it.

Each `get_value` is called unbound against a stand-in exposing only the
attributes it reads, because building a real entity needs a `hass`. That is the
same trick `tests/test_diagnostics.py` uses on the `Hub`.
"""

import datetime
import json
import zoneinfo

from _harness import TRANSLATIONS
import pytest

from custom_components.cozytouch.capability_table import CAPABILITIES
from custom_components.cozytouch.const import CozytouchCapabilityVariableType
from custom_components.cozytouch.infos import CapabilityInfos
from custom_components.cozytouch.sensor import (
    CozytouchAwayModeSensor,
    CozytouchAwayModeTimestampSensor,
    CozytouchErrorCodeSensor,
    CozytouchProgSensor,
    CozytouchProgTimeSensor,
    CozytouchTimezoneSensor,
    CozytouchUnitSensor,
    decode_error_code,
)
from homeassistant.util import dt as dt_util

CAPABILITY_ID = 42


class FakeCoordinator:
    """A hub stand-in that answers one capability id, and records the rest."""

    def __init__(self, values, away_start=0, away_end=0):
        self._values = values
        self.away_start = away_start
        self.away_end = away_end
        self.initialised_with = None

    def get_capability_value(self, capabilityId, defaultIfNotExist="0"):
        return self._values.get(capabilityId)

    def get_away_mode_start(self):
        return self.away_start

    def get_away_mode_end(self):
        return self.away_end

    def away_mode_init(self, start, end):
        self.initialised_with = (start, end)


def sensor(cls, value, capability=None, **attrs):
    """A stand-in for an entity of cls, holding only what get_value reads."""
    stub = object.__new__(cls)
    stub._capability = CapabilityInfos(capabilityId=CAPABILITY_ID, **(capability or {}))
    stub.coordinator = FakeCoordinator({CAPABILITY_ID: value})
    for name, attr in attrs.items():
        setattr(stub, name, attr)
    return stub


# ----------------------------------------------------------------- timezone


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        ("0", "GMT"),
        ("3600", "GMT+1"),
        ("7200", "GMT+2"),
        ("-3600", "GMT-1"),
        ("-18000", "GMT-5"),
        # A half-hour zone truncates towards zero rather than rounding, on
        # both signs. India reports GMT+5, not GMT+5:30 and not GMT+6.
        ("19800", "GMT+5"),
        ("-19800", "GMT-5"),
        # Under an hour there is no hour to show.
        ("1800", "GMT+0"),
        ("-1800", "GMT-0"),
    ],
)
def test_an_offset_reads_as_whole_hours_truncated(seconds, expected):
    """`%d` over a true division truncated; the f-string uses floor division,
    which is the same thing only because both branches are positive. These pin
    that it stayed the same thing.
    """
    got = CozytouchTimezoneSensor.get_value(sensor(CozytouchTimezoneSensor, seconds))
    assert got == expected


# ------------------------------------------------------- heating programmes


@pytest.mark.parametrize(
    ("program", "expected"),
    [
        ("[[420,21]]", "07:00  21°C"),
        ("[[420,21],[1290,17]]", "07:00  21°C / 21:30  17°C"),
        # A [0,0] slot is an unused one and is left out entirely.
        ("[[420,21],[0,0]]", "07:00  21°C"),
        ("[[0,0]]", ""),
        # Midnight is a real slot: only [0, 0] means "unused".
        ("[[0,19]]", "00:00  19°C"),
    ],
)
def test_a_programme_reads_as_slots_joined_by_a_slash(program, expected):
    """The double space before the temperature is not a typo, it is what the
    two concatenations have always produced. Somebody's dashboard has it.
    """
    got = CozytouchProgSensor.get_value(sensor(CozytouchProgSensor, program))
    assert got == expected


@pytest.mark.parametrize(
    ("program", "expected"),
    [
        ("[[420,21.0]]", "07:00  21°C"),
        ("[[420,21.5]]", "07:00  21°C"),
        ("[[420,21.9]]", "07:00  21°C"),
        ("[[420,-3.7]]", "07:00  -3°C"),
    ],
)
def test_a_setpoint_that_arrives_as_a_float_is_still_shown_whole(program, expected):
    """This is the case the format rewrite could have broken and no other test
    would have noticed: the value comes out of json.loads, so it can be a
    float, and `%d` truncated it. 21.5 has to keep reading as 21°C, not 21.5.
    """
    got = CozytouchProgSensor.get_value(sensor(CozytouchProgSensor, program))
    assert got == expected


@pytest.mark.parametrize(
    ("program", "expected"),
    [
        ("[[420,1290]]", "07:00-21:30"),
        ("[[420,1290],[60,120]]", "07:00-21:30 / 01:00-02:00"),
        ("[[0,0]]", ""),
    ],
)
def test_a_time_programme_reads_as_from_dash_to(program, expected):
    got = CozytouchProgTimeSensor.get_value(sensor(CozytouchProgTimeSensor, program))
    assert got == expected


# ------------------------------------------------------------ away mode text


# As the rows declare them, on 152 and 227.
AWAY_VALUES = {"value_off": "0", "value_on": "1", "value_pending": "2"}


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("0", "off"),
        ("1", "on"),
        ("2", "pending"),
        # A value none of the three claim is unknown rather than a word of
        # our own, like every other state Home Assistant cannot name.
        ("9", None),
    ],
)
def test_away_mode_reads_as_a_translatable_state(value, expected):
    """Keys, not words : the translations name them, "pending" as scheduled."""
    stub = sensor(CozytouchAwayModeSensor, value, capability=AWAY_VALUES)
    assert CozytouchAwayModeSensor.get_value(stub) == expected


def test_every_away_state_is_translated():
    """The gateway's sensor and a room's 100261 share the key "away_mode"."""
    states = {"off", "on", "pending"}
    assert set(CAPABILITIES[100261].reads_as.values()) == states
    for path in TRANSLATIONS:
        with open(path, encoding="utf-8") as handle:
            content = json.load(handle)
        assert set(content["entity"]["sensor"]["away_mode"]["state"]) == states, path


def test_away_mode_not_reported_is_none_rather_than_unknown():
    """The `return None` this now says out loud used to be an implicit fall off
    the end of the function. Same value, and now it is on purpose.
    """
    stub = sensor(CozytouchAwayModeSensor, None, capability=AWAY_VALUES)
    assert CozytouchAwayModeSensor.get_value(stub) is None


# ------------------------------------------------------------- unit scaling


def test_a_display_factor_scales_the_reported_value():
    stub = sensor(
        CozytouchUnitSensor,
        "1500",
        _value_type=CozytouchCapabilityVariableType.FLOAT,
        _display_factor=0.001,
    )
    assert CozytouchUnitSensor.get_value(stub) == 1.5


def test_a_display_factor_of_one_hands_the_value_back_untouched():
    stub = sensor(
        CozytouchUnitSensor,
        "1500",
        _value_type=CozytouchCapabilityVariableType.FLOAT,
        _display_factor=1.0,
    )
    assert CozytouchUnitSensor.get_value(stub) == 1500.0


@pytest.mark.parametrize(("last", "expected"), [(None, None), ("", None)])
def test_a_unit_sensor_with_nothing_behind_it_has_no_native_value(last, expected):
    """The other implicit return that is now explicit."""
    stub = object.__new__(CozytouchUnitSensor)
    stub._last_value = last
    assert CozytouchUnitSensor.native_value.fget(stub) is expected


@pytest.mark.parametrize("last", [0, 0.0, "0", "0.00000000000000000000"])
def test_a_reading_of_zero_is_a_reading(last):
    """It used to read as unknown: the test was `if self._last_value`, and
    every way a device says zero is falsy. An outside temperature at 0 C, an
    idle power at 0 W and a thermostat with no probe all came out the same.
    """
    stub = object.__new__(CozytouchUnitSensor)
    stub._last_value = last
    assert CozytouchUnitSensor.native_value.fget(stub) == 0.0


def test_a_scaled_sensor_that_reports_nothing_does_not_raise():
    """float(None) is a TypeError, and the scaling ran before anything looked
    at whether there was a value to scale.
    """
    stub = sensor(
        CozytouchUnitSensor,
        None,
        _value_type=CozytouchCapabilityVariableType.FLOAT,
        _display_factor=0.001,
    )
    assert CozytouchUnitSensor.get_value(stub) is None


def test_a_unit_sensor_that_cannot_parse_its_value_reads_as_zero():
    """Not None: an unparseable value is reported as 0.0, which is inherited
    behaviour and load-bearing for the statistics HA derives from it.
    """
    stub = object.__new__(CozytouchUnitSensor)
    stub._last_value = "not a number"
    assert CozytouchUnitSensor.native_value.fget(stub) == 0.0


# --------------------------------------------------- away mode timestamps


def timestamp_sensor(value, index=0, offset="7200", away=(0, 0)):
    """A timestamp sensor reading `value`, with the device reporting `offset`."""
    stub = object.__new__(CozytouchAwayModeTimestampSensor)
    stub._capability = CapabilityInfos(
        capabilityId=CAPABILITY_ID, timezoneCapabilityId=99
    )
    stub.coordinator = FakeCoordinator(
        {CAPABILITY_ID: value, 99: offset}, away_start=away[0], away_end=away[1]
    )
    stub._separator = ","
    stub._timestamp_index = index
    return stub


@pytest.fixture
def in_timezone():
    """Run a test under a fixed Home Assistant zone, since the sensor reads it.

    A test that renders a timestamp is otherwise a test of whatever zone the
    last one left behind, so it goes back to UTC afterwards.
    """

    def switch(name):
        dt_util.set_default_time_zone(zoneinfo.ZoneInfo(name))

    yield switch
    dt_util.set_default_time_zone(datetime.UTC)


def test_an_unset_window_reads_as_unknown(in_timezone):
    """None, so Home Assistant says it in the reader's language."""
    in_timezone("UTC")
    assert CozytouchAwayModeTimestampSensor.get_value(timestamp_sensor("[0,0]")) is None


def test_a_window_that_is_not_reported_is_none(in_timezone):
    in_timezone("UTC")
    assert CozytouchAwayModeTimestampSensor.get_value(timestamp_sensor(None)) is None


@pytest.mark.parametrize(
    ("index", "expected"), [(0, "22:13 14/11/2023"), (1, "23:13 14/11/2023")]
)
def test_each_end_of_the_window_reads_from_its_own_index(in_timezone, index, expected):
    in_timezone("UTC")
    stub = timestamp_sensor("[1700000000,1700003600]", index=index)
    assert CozytouchAwayModeTimestampSensor.get_value(stub) == expected


def test_the_window_reads_as_the_vendor_app_set_it(in_timezone):
    """Measured on a HUB Navizone (1758), 2026-09-24.

    An absence was set that morning. The setup's own
    `absence.startDate` and the gateway's 222 both hold 1790238529 --
    10:28:49 in Paris -- and the gateway reports 315 at 7200. The sensor
    used to add that offset to the timestamp and read the sum in the local
    zone, so the gateway showed 12:28 while the room beside it, which reports
    no 315, showed 10:28.
    """
    in_timezone("Europe/Paris")
    stub = timestamp_sensor("[1790238529,1790584129]", offset="7200")

    assert CozytouchAwayModeTimestampSensor.get_value(stub) == "10:28 24/09/2026"


def test_the_offset_the_device_reports_moves_nothing(in_timezone):
    """The timestamp is an instant already ; the offset is not added to it."""
    in_timezone("Europe/Paris")
    readings = {
        CozytouchAwayModeTimestampSensor.get_value(
            timestamp_sensor("[1790238529,1790584129]", offset=offset)
        )
        for offset in ("0", "3600", "7200", "-18000")
    }

    assert readings == {"10:28 24/09/2026"}


# ---------------------------------------------------------------- error codes


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Healthy: every row all-zero, in both the four- and five-column
        # shapes different firmwares report. This is what all but one capture
        # shows, and it stops reading as a ten-row matrix.
        ("[[0,0,0,0],[0,0,0,0],[0,0,0,0]]", "OK"),
        ("[[0,0,0,0,0],[0,0,0,0,0]]", "OK"),
        # The empty-slot sentinel: 0xFF fills a field of a slot holding no
        # fault. Whole accounts report the same row ten times over, which is
        # an empty list, not ten identical faults.
        ("[[0,255,0,4],[0,255,0,4],[0,255,0,4]]", "OK"),
        ("[[255,255,0,255,0],[255,255,0,255,130]]", "OK"),
        # An active row -- none has ever been captured, so this pins the
        # format the join is derived from, not a decoded example.
        ("[[50,10,0,1],[0,0,0,0]]", "50_10_0_1"),
        ("[[50,10,0,1],[74,50,1,1]]", "50_10_0_1, 74_50_1_1"),
        # The same fault repeated across slots is reported once.
        ("[[50,10,0,1],[50,10,0,1]]", "50_10_0_1"),
        # A fifth field, when present, rides along in the code.
        ("[[50,10,0,1,3]]", "50_10_0_1_3"),
        # Empty matrix is healthy, not an error state.
        ("[]", "OK"),
    ],
)
def test_the_fault_matrix_decodes_to_the_codes_that_are_active(raw, expected):
    assert decode_error_code(raw) == expected


def test_an_unparseable_value_is_surfaced_rather_than_swallowed():
    """An encoding this does not expect is worth seeing raw, not hiding as
    "OK": the point of the sensor is to show a fault, never to mask one.
    """
    assert decode_error_code("not json") == "not json"


def test_a_missing_value_stays_missing():
    assert decode_error_code(None) is None


def test_the_sensor_reads_the_capability_through_the_decoder():
    """The class is a thin wrapper: it fetches the id and decodes it, so one
    case end to end guards the wiring the parametrized tests do not touch.
    """
    stub = sensor(CozytouchErrorCodeSensor, "[[0,0,0,0],[0,0,0,0]]")
    assert CozytouchErrorCodeSensor.get_value(stub) == "OK"
