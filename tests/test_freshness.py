"""What the device says about the age of its own values.

Every capability item the API returns carries three fields, and the
integration read two of them: `{"capabilityId": 93, "modificationDate":
1786182322, "value": "1"}`. docs/api-surface.md recorded the third as
"available and unused", which is what these tests are about.

It answers the one question a frozen reading raises and nothing else here
could : the value has not moved, but is the hardware still reporting? A cloud
integration that serves the last thing it heard, forever, with no way to tell,
is the failure people report as "the temperature is wrong" -- and the entity
built here is what tells those two apart.

The poll sensor at the bottom is the question's other half : when did the
integration last *ask*. The device's date can sit still because nothing
changed or because nothing was fetched, and only the pair separates the two.

What it deliberately does *not* do is decide when a device is stale. A stable
water heater can leave every capability untouched for hours, so a guessed
threshold would mark working hardware unavailable; the date is surfaced and
the judgement is left to whoever reads it. The dump carries the same dates per
capability, which is what makes a threshold decidable from reports later.

The readers are called unbound against a stand-in, the way
tests/test_diagnostics.py does: they touch `_devices` and `_deviceId` and
nothing a real coordinator would bring.
"""

import datetime
from types import SimpleNamespace

from _harness import SUBENTRY_ID, entry_over, set_up
import pytest

from custom_components.cozytouch import sensor as sensor_platform
from custom_components.cozytouch.const import DOMAIN
from custom_components.cozytouch.hub import Hub, as_epoch
from custom_components.cozytouch.infos import ModelInfos
from custom_components.cozytouch.sensor import (
    CozytouchLastPollSensor,
    CozytouchLastUpdateSensor,
)
from homeassistant.components.sensor.const import SensorDeviceClass

DEVICE_ID = 1001
OTHER_DEVICE_ID = 1002

# A date from a real capture, so the test reads like the payload does.
CAPTURED = 1786182322


def capability(capabilityId, value="1", modificationDate=CAPTURED):
    item = {"capabilityId": capabilityId, "value": value}
    if modificationDate is not None:
        item["modificationDate"] = modificationDate

    return item


def make_hub(capabilities, deviceId=DEVICE_ID):
    """A stand-in exposing only what the two readers touch."""
    return SimpleNamespace(
        _deviceId=deviceId,
        _account=SimpleNamespace(devices=[
            {"deviceId": DEVICE_ID, "capabilities": capabilities},
            # A sibling on the same account, whose dates must not leak into
            # this device's answer: one hub drives one device.
            {
                "deviceId": OTHER_DEVICE_ID,
                "capabilities": [capability(1, modificationDate=CAPTURED + 9999)],
            },
        ]),
    )


# ------------------------------------------------------------------ as_epoch


def test_a_date_the_api_sent_reads_as_itself():
    assert as_epoch(CAPTURED) == CAPTURED


def test_a_date_that_arrives_as_a_string_still_reads():
    """`value` comes from this API as a string, so a date might too."""
    assert as_epoch(str(CAPTURED)) == CAPTURED
    assert as_epoch(f"{CAPTURED}.0") == CAPTURED


@pytest.mark.parametrize("said_nothing", [None, "", "unknown", 0, "0", -1])
def test_nothing_useful_reads_as_nothing(said_nothing):
    """Not as 1970. The field has no catalogue, so a zero is not a date."""
    assert as_epoch(said_nothing) is None


# ------------------------------------------------------------- the two readers


def test_one_capability_reports_its_own_date():
    hub = make_hub([capability(93), capability(40, modificationDate=CAPTURED - 60)])

    assert Hub.get_capability_modification_date(hub, 93) == CAPTURED
    assert Hub.get_capability_modification_date(hub, 40) == CAPTURED - 60


def test_a_capability_the_device_does_not_report_has_no_date():
    hub = make_hub([capability(93)])

    assert Hub.get_capability_modification_date(hub, 172) is None


def test_a_capability_without_a_date_has_none():
    hub = make_hub([capability(93, modificationDate=None)])

    assert Hub.get_capability_modification_date(hub, 93) is None


def test_the_device_date_is_the_newest_of_its_capabilities():
    """The newest, because that is what "still reporting" means.

    Any single capability can sit unchanged for hours while the device keeps
    talking, so the oldest -- or any one of them -- would read as a silence
    that is not there.
    """
    hub = make_hub(
        [
            capability(93, modificationDate=CAPTURED - 3600),
            capability(40, modificationDate=CAPTURED),
            capability(117, modificationDate=CAPTURED - 60),
        ]
    )

    assert Hub.get_last_modification_date(hub) == CAPTURED


def test_a_device_reporting_no_dates_at_all_has_none():
    """Which is what keeps the sensor from being created for that device."""
    hub = make_hub([capability(93, modificationDate=None)])

    assert Hub.get_last_modification_date(hub) is None


def test_a_device_reporting_nothing_has_none():
    hub = make_hub([])

    assert Hub.get_last_modification_date(hub) is None


def test_a_siblings_dates_do_not_answer_for_this_device():
    """make_hub's second device is newer, and belongs to another hub."""
    hub = make_hub([capability(93, modificationDate=CAPTURED)])

    assert Hub.get_last_modification_date(hub) == CAPTURED


# ------------------------------------------------------------------ the sensor



def build(last_modification_date, capabilities=(), last_poll=None):
    """Run the sensor platform and return the entities it built."""
    hub = SimpleNamespace(
        get_capabilities_for_device=lambda deviceId=None: list(capabilities),
        get_last_modification_date=lambda: last_modification_date,
        get_last_poll=lambda: last_poll,
        get_model_infos=lambda: ModelInfos(name="Air Conditioner (Salon)"),
        get_serial_number=lambda: "1234-5678-0000",
        get_software_version=lambda: "1.2.3",
        get_via_device=lambda: None,
    )
    return set_up(sensor_platform, entry_over(hub))


def test_the_sensor_exists_when_the_device_reports_a_date():
    built = build(CAPTURED)

    assert [type(entity).__name__ for entity in built] == [
        "CozytouchLastUpdateSensor"
    ]


def test_no_sensor_when_the_device_reports_no_date():
    """The rule the capability flags follow: only declare what the hardware backs."""
    assert build(None) == []


def test_the_sensor_reads_the_epoch_as_an_aware_utc_datetime():
    """An epoch is absolute, so UTC is the only correct reading of it.

    The away-mode timestamp sensor applies the device's offset twice
    (docs/architecture.md records it); this one has no offset to apply and
    says so by passing tz explicitly.
    """
    sensor = build(CAPTURED)[0]

    assert sensor.native_value == datetime.datetime.fromtimestamp(
        CAPTURED, tz=datetime.UTC
    )
    assert sensor.native_value.tzinfo is not None


def test_the_sensor_follows_the_device_between_polls():
    """native_value is read on demand, so a fresh poll shows without a rebuild."""
    dates = [CAPTURED]
    hub = SimpleNamespace(get_last_modification_date=lambda: dates[-1])
    sensor = CozytouchLastUpdateSensor(coordinator=hub, config_uniq_id="entry123")

    dates.append(CAPTURED + 30)

    assert sensor.native_value == datetime.datetime.fromtimestamp(
        CAPTURED + 30, tz=datetime.UTC
    )


def test_the_sensor_is_a_timestamp_with_no_state_class():
    """The pair Home Assistant accepts: it refuses a state class on a timestamp."""
    sensor = build(CAPTURED)[0]

    assert sensor.device_class == SensorDeviceClass.TIMESTAMP
    assert sensor.state_class is None


def test_the_sensor_is_a_diagnostic_and_keyed_on_the_entry():
    """Not on a capability id, since it answers for all of them."""
    sensor = build(CAPTURED)[0]

    assert sensor.unique_id == f"{DOMAIN}_{SUBENTRY_ID}_last_device_update"
    assert sensor.entity_category == "diagnostic"
    assert sensor.translation_key == "last_device_update"


def test_the_sensor_lands_on_the_same_device_as_the_others():
    """Same identifiers as a capability sensor, or it appears as a second device."""
    sensor = build(CAPTURED)[0]

    info = sensor.device_info

    assert info["identifiers"] == {(DOMAIN, SUBENTRY_ID)}
    assert info["serial_number"] == "1234-5678-0000"
    assert info["sw_version"] == "1.2.3"


# ---------------------------------------------------------- the poll sensor

# The other half of the freshness question : `modificationDate` says when the
# hardware last changed a value, the poll date says when the integration last
# asked. It is the account's date -- one setup-view request refreshes every
# device -- surfaced per device so it sits next to the values it dates.

POLLED = datetime.datetime.fromtimestamp(CAPTURED + 12, tz=datetime.UTC)


def test_the_poll_sensor_exists_once_the_account_has_polled():
    built = build(None, last_poll=POLLED)

    assert [type(entity).__name__ for entity in built] == ["CozytouchLastPollSensor"]


def test_the_two_freshness_sensors_stand_side_by_side():
    built = build(CAPTURED, last_poll=POLLED)

    assert [type(entity).__name__ for entity in built] == [
        "CozytouchLastUpdateSensor",
        "CozytouchLastPollSensor",
    ]


def test_the_poll_sensor_reads_the_accounts_date_unchanged():
    """The account stamps an aware datetime, so there is nothing to convert."""
    sensor = build(None, last_poll=POLLED)[0]

    assert sensor.native_value == POLLED
    assert sensor.native_value.tzinfo is not None


def test_the_poll_sensor_follows_the_account_between_polls():
    """native_value is read on demand, so a fresh poll shows without a rebuild."""
    dates = [POLLED]
    hub = SimpleNamespace(get_last_poll=lambda: dates[-1])
    sensor = CozytouchLastPollSensor(coordinator=hub, config_uniq_id="entry123")

    dates.append(POLLED + datetime.timedelta(seconds=30))

    assert sensor.native_value == POLLED + datetime.timedelta(seconds=30)


def test_the_poll_sensor_survives_the_failure_it_dates():
    """Available on the last success, not on the last attempt.

    A CoordinatorEntity goes unavailable when its coordinator's poll fails,
    which is exactly when "how old is what the entities show" is being asked.
    docs/decisions.md carries the argument.
    """
    hub = SimpleNamespace(get_last_poll=lambda: POLLED, last_update_success=False)
    sensor = CozytouchLastPollSensor(coordinator=hub, config_uniq_id="entry123")

    assert sensor.available is True


def test_the_poll_sensor_is_a_timestamp_with_no_state_class():
    """The pair Home Assistant accepts: it refuses a state class on a timestamp."""
    sensor = build(None, last_poll=POLLED)[0]

    assert sensor.device_class == SensorDeviceClass.TIMESTAMP
    assert sensor.state_class is None


def test_the_poll_sensor_is_a_diagnostic_and_keyed_on_the_entry():
    """Not on a capability id, since it answers for the whole account."""
    sensor = build(None, last_poll=POLLED)[0]

    assert sensor.unique_id == f"{DOMAIN}_{SUBENTRY_ID}_last_poll"
    assert sensor.entity_category == "diagnostic"
    assert sensor.translation_key == "last_poll"


def test_the_poll_sensor_lands_on_the_same_device_as_the_others():
    """Same identifiers as a capability sensor, or it appears as a second device."""
    sensor = build(None, last_poll=POLLED)[0]

    info = sensor.device_info

    assert info["identifiers"] == {(DOMAIN, SUBENTRY_ID)}


# -------------------------------------------------------------------- the dump


def diagnostics(capabilities):
    """The dump for an account whose second device is not this entry's."""
    account = SimpleNamespace(
        devices=[
            {
                "deviceId": DEVICE_ID,
                "name": "ROOM_0",
                "modelId": 557,
                "productId": 26,
                "zoneId": 991904,
                "tags": [],
                "capabilities": capabilities,
            },
            {
                "deviceId": OTHER_DEVICE_ID,
                "name": "ROOM_1",
                "modelId": 557,
                "productId": 26,
                "zoneId": 991905,
                "tags": [],
                "capabilities": [],
            },
        ],
        setup={"id": 1532156, "name": "setup1"},
        zones=[],
    )
    hub = SimpleNamespace(
        _account=account,
        _deviceId=DEVICE_ID,
        _entry=SimpleNamespace(
            subentries={"sub-1": SimpleNamespace(data={"deviceId": DEVICE_ID})}
        ),
    )
    hub.get_zone_name = lambda zoneId=None: None
    hub.get_capability_names = lambda deviceId=None: Hub.get_capability_names(
        hub, deviceId
    )

    return Hub.get_diagnostics(hub)


def test_the_dump_carries_a_date_per_capability():
    """What tells a value that is wrong from an id the hardware never feeds."""
    reported = diagnostics([capability(93), capability(40, modificationDate=None)])

    assert reported["devices"][0]["capabilities"]["modificationDates"] == {
        93: CAPTURED,
        40: None,
    }


def test_the_dump_carries_the_dates_of_a_device_nobody_added():
    """The dump covers the whole account, so a device nobody added is reported
    with its capability list -- which is where unmapped hardware actually is.
    Its dates come along, empty here because the fixture gives it none.
    """
    reported = diagnostics([capability(93)])

    assert reported["devices"][1]["capabilities"]["modificationDates"] == {}
