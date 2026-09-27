"""What the consumption endpoint becomes : the parse, the sensors, the dump.

Nobody here owns a device that reports consumption. The fixture is the one
`mmnlfrrr/cozytouch` published from a Thermor Duralis ACI HYB (model 393),
sanitised there : two series, electricity split between two tariff periods
and water, three days each. So this pins how the integration reads *that*
answer ; what another appliance sends is still unmeasured, and the tests that
go beyond the fixture say which case they invent and why.

What a poll of the endpoint costs, and when it stops, is pinned beside the
rest of the polling in `tests/test_polling.py`.
"""

import asyncio
import copy
import datetime
import json
import pathlib
from types import SimpleNamespace

from _harness import set_up
import pytest

from custom_components.cozytouch import (
    consumption,
    diagnostics,
    sensor as sensor_platform,
)
from homeassistant.components.sensor.const import (
    DEVICE_CLASS_STATE_CLASSES,
    SensorDeviceClass,
    SensorStateClass,
)

FIXTURE = pathlib.Path(__file__).parent / "fixtures" / "consumptions_daily.json"

# 2026-09-10 00:00 UTC, the latest day in the fixture.
LATEST = 1788998400


def answer():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


# ------------------------------------------------------------------ the parse


def test_only_the_latest_day_is_read():
    days = consumption.latest_days(answer())

    assert {kind: day.date for kind, day in days.items()} == {
        consumption.ELECTRICITY: LATEST,
        consumption.WATER: LATEST,
    }


def test_electricity_is_split_by_tariff_and_adds_up():
    day = consumption.latest_days(answer())[consumption.ELECTRICITY]

    assert day.of_mode("quantity", consumption.OFFPEAK) == 3.87
    assert day.of_mode("quantity", consumption.PEAK) == 1.16
    assert day.total("quantity") == 5.03
    assert day.total("cost") == 0.81
    assert day.currency == "EUR"


def test_water_is_its_own_series():
    day = consumption.latest_days(answer())[consumption.WATER]

    assert day.total("quantity") == 109
    assert day.modes == {0}


def test_a_tariff_period_the_day_does_not_report_used_nothing():
    """The fixture's first two days are off-peak only ; on such a day the
    peak reading is zero, not unknown.
    """
    payload = answer()
    electricity = payload[0]
    electricity["consumptionPeriods"] = [
        period
        for period in electricity["consumptionPeriods"]
        if period["mode"] == consumption.OFFPEAK
    ]
    day = consumption.latest_days(payload)[consumption.ELECTRICITY]

    assert day.of_mode("quantity", consumption.PEAK) == 0


def test_an_empty_field_reads_as_zero():
    """Seen on the fork's device : a reported period with no quantity."""
    payload = answer()
    payload[0]["consumptionPeriods"][-1]["consumedQuantity"] = None
    day = consumption.latest_days(payload)[consumption.ELECTRICITY]

    assert day.of_mode("quantity", consumption.PEAK) == 0
    assert day.total("quantity") == 3.87


def test_two_series_of_one_kind_are_added_together():
    """Invented : a setup with two metered appliances. Adding them is the one
    reading that does not lose one of them, which a dict keyed on the kind
    alone did.
    """
    payload = answer()
    payload.append(copy.deepcopy(payload[0]))
    day = consumption.latest_days(payload)[consumption.ELECTRICITY]

    assert day.total("quantity") == 10.06


def test_a_series_in_a_unit_nobody_has_seen_is_left_out():
    payload = answer()
    payload[1]["unit"] = 3

    assert consumption.WATER not in consumption.latest_days(payload)


@pytest.mark.parametrize("payload", [None, {}, [], [None], [{"type": 1}]])
def test_an_answer_with_nothing_readable_reads_as_nothing(payload):
    assert consumption.latest_days(payload) == {}


# ---------------------------------------------------------------- the sensors


def entry_with(consumptions, setup=None):
    """An account entry whose setup answered the consumption endpoint so."""
    account = SimpleNamespace(
        consumptions=consumptions, setup=setup or {"id": 1, "name": "Maison"}
    )
    return SimpleNamespace(
        runtime_data=SimpleNamespace(
            hubs={},
            account=account,
            coordinator=SimpleNamespace(last_update_success=True),
        ),
        subentries={},
        title="cozytouch@example.com",
        entry_id="entry123",
    )


def sensors(consumptions, setup=None):
    return {
        entity.entity_description.key: entity
        for entity in set_up(sensor_platform, entry_with(consumptions, setup))
    }


def test_the_fixture_builds_five_sensors():
    assert sorted(sensors(answer())) == [
        "energy_cost_today",
        "energy_offpeak_today",
        "energy_peak_today",
        "energy_today",
        "water_today",
    ]


def test_they_read_the_latest_day():
    built = sensors(answer())

    assert {key: entity.native_value for key, entity in built.items()} == {
        "energy_today": 5.03,
        "energy_peak_today": 1.16,
        "energy_offpeak_today": 3.87,
        "energy_cost_today": 0.81,
        "water_today": 109,
    }


def test_each_resets_at_the_start_of_its_day():
    for entity in sensors(answer()).values():
        assert entity.last_reset == datetime.datetime(2026, 9, 10, tzinfo=datetime.UTC)


def test_their_units_and_classes_are_ones_home_assistant_accepts():
    """MONETARY admits TOTAL and nothing else, which is why every one of them
    is TOTAL with a `last_reset` rather than TOTAL_INCREASING.
    """
    built = sensors(answer())

    units = {key: entity.native_unit_of_measurement for key, entity in built.items()}
    assert units == {
        "energy_today": "kWh",
        "energy_peak_today": "kWh",
        "energy_offpeak_today": "kWh",
        "energy_cost_today": "EUR",
        "water_today": "L",
    }
    for entity in built.values():
        assert entity.state_class == SensorStateClass.TOTAL
        assert entity.state_class in DEVICE_CLASS_STATE_CLASSES[entity.device_class]

    assert built["energy_cost_today"].device_class == SensorDeviceClass.MONETARY


def test_they_belong_to_the_setup_not_to_a_device():
    entity = sensors(answer())["energy_today"]

    assert entity.unique_id == "cozytouch_entry123_consumption_energy_today"
    assert entity.device_info["identifiers"] == {("cozytouch", "entry123")}
    assert entity.device_info["name"] == "Maison"


def test_no_tariff_split_where_the_series_never_used_one():
    """Invented : a setup on a single-rate contract, reporting mode 0."""
    payload = answer()
    for period in payload[0]["consumptionPeriods"]:
        period["mode"] = 0

    assert "energy_peak_today" not in sensors(payload)
    assert "energy_offpeak_today" not in sensors(payload)
    assert sensors(payload)["energy_today"].native_value == 5.03


def test_no_cost_in_a_currency_nobody_has_seen():
    payload = answer()
    payload[0]["currency"] = 999

    assert "energy_cost_today" not in sensors(payload)


@pytest.mark.parametrize("consumptions", [None, []])
def test_a_setup_without_a_meter_gets_no_sensor(consumptions):
    assert sensors(consumptions) == {}


def test_a_series_that_stops_coming_makes_its_sensor_unavailable():
    """Built from the first answer ; a later one without the series leaves
    the sensor with nothing to read, which is not a zero.
    """
    entry = entry_with(answer())
    built = set_up(sensor_platform, entry)
    entry.runtime_data.account.consumptions = answer()[:1]

    water = next(e for e in built if e.entity_description.key == "water_today")
    assert water.available is False
    assert water.native_value is None


# ------------------------------------------------------------------- the dump


def test_the_dump_carries_the_answer_without_the_serial_numbers():
    account = SimpleNamespace(
        online=True,
        consumptions=answer(),
        consumptions_status=200,
        consumption_declared=lambda: True,
        fetch_capability_catalogue=lambda: asyncio.sleep(0, {}),
    )
    entry = SimpleNamespace(
        runtime_data=SimpleNamespace(account=account, hubs={}),
        options={},
        data={},
        subentries={},
    )

    dump = asyncio.run(diagnostics.async_get_config_entry_diagnostics(None, entry))

    assert dump["consumptions"]["declared"] is True
    assert dump["consumptions"]["status"] == 200
    series = dump["consumptions"]["answer"][0]
    assert series["serialNumber"] == "**REDACTED**"
    assert series["consumptionPeriods"] == answer()[0]["consumptionPeriods"]
