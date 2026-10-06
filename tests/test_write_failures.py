"""A write that does not land raises, and says why.

It used to return quietly : a press on a device the cloud marks offline left
every entity as it was, with nothing on screen and an INFO line in the log at
best, so a gateway that had dropped off its wifi read as an integration that
did nothing (HUB Cozytouch 1457 with five Fujitsu rooms, 2026-10-04 report,
every device `isAvailable: false` and 218 at 4). Home Assistant shows a
`HomeAssistantError` to whoever pressed, so the message is the diagnosis.

`set_capability_value` is called unbound against a stand-in, the way
tests/test_availability.py calls `get_is_available`.
"""

import asyncio
from functools import partial
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from custom_components.cozytouch.const import DOMAIN
from custom_components.cozytouch.hub import Hub
from homeassistant.exceptions import HomeAssistantError

DEVICE_ID = 27431459
COMPONENT = Path(__file__).parent.parent / "custom_components/cozytouch"
LANGUAGES = [COMPONENT / "strings.json", *sorted(COMPONENT.glob("translations/*.json"))]
REASONS = ["cloud_unreachable", "device_offline", "write_not_completed"]


def make_hub(written, online=True, isAvailable=True):
    """A stand-in whose account answers every write with `written`."""
    device = {
        "deviceId": DEVICE_ID,
        "capabilities": [{"capabilityId": 40, "value": "20"}],
    }
    if isAvailable is not None:
        device["isAvailable"] = isAvailable

    async def write_capability(deviceId, capabilityId, value):
        return written

    hub = SimpleNamespace(
        online=online,
        _deviceId=DEVICE_ID,
        _account=SimpleNamespace(devices=[device], write_capability=write_capability),
    )
    hub.get_is_available = partial(Hub.get_is_available, hub)
    return hub, device


def write(hub, value="22"):
    asyncio.run(Hub.set_capability_value(hub, 40, value))


def refusal(hub) -> str:
    with pytest.raises(HomeAssistantError) as raised:
        write(hub)
    assert raised.value.translation_domain == DOMAIN
    return raised.value.translation_key


def test_a_completed_write_updates_the_value():
    hub, device = make_hub(written=True)

    write(hub)

    assert device["capabilities"][0]["value"] == "22"


def test_a_device_the_cloud_marks_offline_is_named_as_the_reason():
    hub, device = make_hub(written=False, isAvailable=False)

    assert refusal(hub) == "device_offline"
    assert device["capabilities"][0]["value"] == "20"


@pytest.mark.parametrize("isAvailable", [True, None])
def test_a_write_that_fails_on_a_reachable_device_is_not_blamed_on_it(isAvailable):
    """Absent reads as unknown, never as offline -- as the sensor reads it."""
    hub, device = make_hub(written=False, isAvailable=isAvailable)

    assert refusal(hub) == "write_not_completed"
    assert device["capabilities"][0]["value"] == "20"


def test_a_write_without_a_session_says_the_cloud_is_unreachable():
    hub, _ = make_hub(written=True, online=False)

    assert refusal(hub) == "cloud_unreachable"


@pytest.mark.parametrize("path", LANGUAGES, ids=lambda path: path.name)
def test_every_reason_has_a_message_in_every_language(path):
    """Without one, the person who pressed reads the raw key."""
    exceptions = json.loads(path.read_text(encoding="utf-8"))["exceptions"]

    assert sorted(exceptions) == REASONS
    assert all(exceptions[key]["message"] for key in REASONS)
