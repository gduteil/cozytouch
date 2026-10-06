"""What the sensor platform declares about a value, rather than the value.

Two things reach Home Assistant besides the reading itself, and neither shows
up in `tests/test_sensor_values.py` because neither passes through a value
builder:

- the **state class**, which decides whether the recorder keeps long-term
  statistics. Without one a sensor has a state history and nothing else, so it
  disappears from the charts after the purge window and has no min/max/mean
  over a season. It is also validated against the device class: Home Assistant
  refuses `measurement` on `volume`, which is how the tank capacities ended up
  as `volume_storage`. The pairs are pinned here *and* checked against Home
  Assistant's own table, so the next type to gain a state class cannot quietly
  pick a combination that gets rejected at runtime.
- the **firmware version**, which the device reports as capability 121 and
  which is put on the device in the registry.

`async_setup_entry` is driven directly, with a hub stand-in and a plain list
for `async_add_entities`: the whole point is to test the platform's own table
rather than restate it, and building an entity needs no `hass`. The device_info
properties are called unbound, the way `tests/test_topology.py` does.
"""

from types import SimpleNamespace

from _harness import entry_over, set_up
import pytest

from custom_components.cozytouch import sensor as sensor_platform
from custom_components.cozytouch.binary_sensor import CloudConnectivity
from custom_components.cozytouch.const import DOMAIN
from custom_components.cozytouch.hub import SOFTWARE_VERSION_CAPABILITY_ID, Hub
from custom_components.cozytouch.infos import CapabilityInfos, ModelInfos
from custom_components.cozytouch.sensor import CozytouchSensor
from homeassistant.components.sensor.const import (
    DEVICE_CLASS_STATE_CLASSES,
    SensorDeviceClass,
    SensorStateClass,
)
from homeassistant.const import UnitOfTime

DEVICE_ID = 1001



def build(capabilities):
    """Run the sensor platform over these capabilities and return the entities.

    One account entry with one device under it, which is the shape the platform
    loops over: `entry.subentries` and a hub per subentry.
    """
    hub = SimpleNamespace(
        get_capabilities_for_device=lambda deviceId=None: capabilities,
        # The platform also builds two entities that are not capability-driven,
        # from the modificationDate the device reports and the account's last
        # successful poll. None here keeps these cases to the capability table
        # they are about; tests/test_freshness.py covers those two.
        get_last_modification_date=lambda: None,
        get_last_poll=lambda: None,
    )
    return set_up(sensor_platform, entry_over(hub))


def one(capability_type, **capability):
    """The single entity the sensor platform builds for one capability."""
    built = build(
        [
            CapabilityInfos(
                **{"capabilityId": 42, "name": "a_capability", "type": capability_type}
                | capability
            )
        ]
    )
    assert len(built) == 1, [type(entity).__name__ for entity in built]
    return built[0]


# ------------------------------------------------------------- state classes

# Every type that carries a state class today, with the device class it is
# paired with. A reading that moves is `measurement`; something the device
# counts up is `total_increasing`.
MEASURED = [
    ("temperature", SensorDeviceClass.TEMPERATURE),
    ("pressure", SensorDeviceClass.PRESSURE),
    ("signal", SensorDeviceClass.SIGNAL_STRENGTH),
    # The tank capacities and what is left in them: stored, not consumed.
    ("volume", SensorDeviceClass.VOLUME_STORAGE),
    # Percentage deliberately claims no device class -- BATTERY made
    # hot_water_available read as a battery level -- and a state class does
    # not need one.
    ("percentage", None),
    # Every "time" capability is a duration in minutes, never a time of day.
    ("time", SensorDeviceClass.DURATION),
]

COUNTED = [
    ("energy", SensorDeviceClass.ENERGY),
    ("water_consumption", SensorDeviceClass.WATER),
]


@pytest.mark.parametrize(("capability_type", "device_class"), MEASURED)
def test_a_reading_is_recorded_as_a_measurement(capability_type, device_class):
    entity = one(capability_type)

    assert entity.device_class == device_class
    assert entity.state_class == SensorStateClass.MEASUREMENT


@pytest.mark.parametrize(("capability_type", "device_class"), COUNTED)
def test_a_meter_is_recorded_as_a_total(capability_type, device_class):
    entity = one(capability_type)

    assert entity.device_class == device_class
    assert entity.state_class == SensorStateClass.TOTAL_INCREASING


@pytest.mark.parametrize(("capability_type", "device_class"), MEASURED + COUNTED)
def test_the_pair_is_one_home_assistant_accepts(capability_type, device_class):
    """The check that catches the mistake `volume` was: a device class only
    admits some state classes, and a rejected pair is logged as an error at
    runtime rather than caught anywhere in review.
    """
    entity = one(capability_type)
    if entity.device_class is None:
        # No device class, nothing to be incompatible with.
        return

    assert entity.state_class in DEVICE_CLASS_STATE_CLASSES[entity.device_class]


@pytest.mark.parametrize("capability_type", ["string", "int", "climate"])
def test_the_types_that_are_not_measurements_declare_no_state_class(capability_type):
    """A mode or a version string is not something to average, and a state
    class on one would only put nonsense in the statistics table.
    """
    assert one(capability_type).state_class is None


def test_a_duration_is_reported_in_minutes():
    """The unit is the whole point: the reading used to be formatted into a
    string, so 480 minutes of minimum heating per day read as "08:00" -- a
    clock, and eight o'clock is not eight hours. A number plus a unit lets
    Home Assistant render and convert it, and lets a template compute on it.
    """
    entity = one("time")

    assert entity.native_unit_of_measurement == UnitOfTime.MINUTES

    # Through the entity the platform actually built, since the formatting
    # lived in get_value: 480 has to come back as the number 480, not as the
    # string "08:00" the old class returned for it.
    entity.coordinator = SimpleNamespace(
        get_capability_value=lambda capabilityId, defaultIfNotExist="0": "480"
    )
    assert entity.get_value() == 480.0


# --------------------------------------------------------- firmware version


def hub_reporting(capabilities):
    """A hub stand-in holding one device, for the accessor to read.

    get_software_version goes through get_capability_value, so the real lookup
    is bound onto the stand-in rather than stubbed: what is being tested is
    which id is asked for and what happens when the answer is missing, and a
    fake lookup would answer both questions itself.
    """
    hub = SimpleNamespace(
        _deviceId=DEVICE_ID,
        _account=SimpleNamespace(
            devices=[{"deviceId": DEVICE_ID, "capabilities": capabilities}]
        ),
    )
    hub.get_capability_value = lambda capabilityId, defaultIfNotExist="0": (
        Hub.get_capability_value(hub, capabilityId, defaultIfNotExist)
    )
    return hub


def test_the_version_the_device_reports_is_the_one_on_the_device():
    hub = hub_reporting(
        [{"capabilityId": SOFTWARE_VERSION_CAPABILITY_ID, "value": "2.14.0"}]
    )

    assert Hub.get_software_version(hub) == "2.14.0"


def test_a_device_that_reports_no_version_gets_none_rather_than_a_default():
    """get_capability_value hands back "0" for a capability a device does not
    report, which as a firmware version would be a lie. The gateways are the
    ones this covers: they report no 121.
    """
    hub = hub_reporting([{"capabilityId": 40, "value": "21"}])

    assert Hub.get_software_version(hub) is None


def coordinator(version):
    """A hub stand-in exposing what the two device_info properties read."""
    return SimpleNamespace(
        get_model_infos=lambda: ModelInfos(name="Naema 2 Micro 25"),
        get_serial_number=lambda: "1234567890",
        get_software_version=lambda: version,
        get_via_device=lambda: None,
        online=True,
    )


def test_the_version_reaches_the_device_registry():
    entity = SimpleNamespace(
        coordinator=coordinator("2.14.0"), _device_uniq_id="entry123"
    )

    info = CozytouchSensor.device_info.fget(entity)

    assert info["sw_version"] == "2.14.0"
    # The rest of the identity is unchanged by carrying a version.
    assert info["identifiers"] == {(DOMAIN, "entry123")}
    assert info["serial_number"] == "1234567890"


def test_the_connectivity_sensor_reports_the_same_version():
    """It is an entity of the same device, so a version on one and not the
    other would make the registry pick whichever was added last.
    """
    entity = SimpleNamespace(
        coordinator=coordinator("2.14.0"),
        _device_uniq_id="entry123",
        _title="Salon",
    )

    assert CloudConnectivity.device_info.fget(entity)["sw_version"] == "2.14.0"


def test_no_version_leaves_the_registry_field_empty():
    entity = SimpleNamespace(coordinator=coordinator(None), _device_uniq_id="entry123")

    assert CozytouchSensor.device_info.fget(entity)["sw_version"] is None
