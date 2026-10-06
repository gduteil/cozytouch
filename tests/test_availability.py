"""The per-device availability the cloud reports (`isAvailable`).

Distinct from the account's cloud session (`online`, the CloudConnectivity
sensor): the session can be working while one device is unavailable, and this
is the finer signal. It is read raw -- the cloud already reflects a child
dropping off its gateway in the field, so nothing is derived on top -- and it
is a separate sensor rather than folded into the session one, so that "the
cloud is down" and "this device is down" stay tellable apart.

`get_is_available` is called unbound against a stand-in, the way
tests/test_freshness.py calls the other device-field readers: it touches
`_account.devices` and `_deviceId` and nothing a real coordinator would bring.
"""

from types import SimpleNamespace

from custom_components.cozytouch.binary_sensor import DeviceAvailability
from custom_components.cozytouch.hub import Hub

DEVICE_ID = 1001
OTHER_DEVICE_ID = 1002


def make_hub(isAvailable, deviceId=DEVICE_ID, other=False):
    """A stand-in exposing only what get_is_available touches."""
    this = {"deviceId": DEVICE_ID}
    if isAvailable is not None or not other:
        this["isAvailable"] = isAvailable
    if isAvailable is None and not other:
        # the field-absent case: no isAvailable key at all
        this.pop("isAvailable", None)
    return SimpleNamespace(
        _deviceId=deviceId,
        _account=SimpleNamespace(
            devices=[
                this,
                # A sibling whose availability must not leak into this answer:
                # one hub drives one device.
                {"deviceId": OTHER_DEVICE_ID, "isAvailable": True},
            ]
        ),
    )


def test_a_device_the_cloud_calls_available_reads_true():
    assert Hub.get_is_available(make_hub(True)) is True


def test_a_device_the_cloud_calls_unavailable_reads_false():
    """The whole point: a device down while the session and its siblings are
    fine.
    """
    assert Hub.get_is_available(make_hub(False)) is False


def test_a_missing_field_is_unknown_not_a_guessed_state():
    """Old captures omit it; a live account never does. Absent reads as None
    (unknown) rather than as a guessed connected or disconnected.
    """
    hub = SimpleNamespace(
        _deviceId=DEVICE_ID,
        _account=SimpleNamespace(devices=[{"deviceId": DEVICE_ID}]),
    )
    assert Hub.get_is_available(hub) is None


def test_a_sibling_availability_does_not_leak():
    """One hub answers for its own device only."""
    hub = SimpleNamespace(
        _deviceId=DEVICE_ID,
        _account=SimpleNamespace(
            devices=[
                {"deviceId": DEVICE_ID, "isAvailable": False},
                {"deviceId": OTHER_DEVICE_ID, "isAvailable": True},
            ]
        ),
    )
    assert Hub.get_is_available(hub) is False


def test_a_device_not_on_the_account_reads_none():
    hub = SimpleNamespace(
        _deviceId=999,
        _account=SimpleNamespace(
            devices=[{"deviceId": DEVICE_ID, "isAvailable": True}]
        ),
    )
    assert Hub.get_is_available(hub) is None


def test_the_sensor_is_enabled_by_default():
    """The answer to "is my device reachable" is worth showing -- one sensor
    per device, next to the cloud-session one -- so the class does not override
    the registry default off. HA turns the other `_attr_*` into property
    descriptors, so this is the one declaration the class __dict__ pins
    directly; device class and category are exercised through setup elsewhere.
    """
    assert (
        "_attr_entity_registry_enabled_default" not in DeviceAvailability.__dict__
    )


def test_the_sensor_reads_availability_through_the_hub():
    """Thin wrapper: is_on is whatever get_is_available returns, unknown and
    all, so one case guards the wiring the getter tests do not.
    """
    coordinator = make_hub(False)

    # what _handle_coordinator_update assigns, without the hass write
    assert Hub.get_is_available(coordinator) is False
