"""Guards for bugs that were live and silent.

None of them showed up in a test run, because none is reachable from the model
or capability tables that the rest of the suite walks: one needed two config
entries to be visible at all, another needed a zone renamed in the Cozytouch
app. All of them are cheap to pin now that they are known.
"""

import asyncio
import inspect
from types import SimpleNamespace

import pytest

from custom_components.cozytouch import account as account_module
from custom_components.cozytouch.account import CozytouchAccount
from custom_components.cozytouch.hub import Hub


def setup_payload(zones, devices=()):
    """The shape of the setupviewv2 response, cut down to what is read here."""
    return [{"zones": list(zones), "devices": list(devices)}]


def stub_account(zones=(), devices=()):
    """A stand-in exposing only what update_devices_from_json_data writes."""
    stub = SimpleNamespace(
        _dump_json=False,
        zones=list(zones),
        devices=list(devices),
        _pending_writes={},
    )
    stub._apply_pending_writes = lambda: CozytouchAccount._apply_pending_writes(stub)
    return stub


def make_account(monkeypatch, username="someone@example.com"):
    """A real account, with Home Assistant's session helper stubbed out."""
    monkeypatch.setattr(
        account_module, "async_get_clientsession", lambda hass: object()
    )

    return CozytouchAccount(SimpleNamespace(), username, "hunter2")


@pytest.mark.parametrize("attribute", ["setup", "zones", "devices"])
def test_the_account_state_is_not_shared_by_every_account(attribute):
    """This lived on the Hub class, so one dict served every config entry.

    An account is set up one entry per device -- a gateway, then a unit per
    zone -- and each built its own Hub. While this state sat on the class,
    `self._setup[key] = ...` mutated the one dict they all saw, so the last hub
    to connect overwrote what the others had stored. Reading it back gave
    another device's setup.

    It now belongs to one account object that the hubs share on purpose, which
    is the same data reaching them by a route that can be reasoned about. The
    trap it replaces is the same one either way: on the class, every *account*
    would share it too.
    """
    assert not hasattr(CozytouchAccount, attribute)


@pytest.mark.parametrize(
    "attribute",
    [
        "_timestamp_away_mode_start",
        "_timestamp_away_mode_end",
    ],
)
def test_the_away_mode_staging_is_not_shared_by_every_hub(attribute):
    """Staged per device, and it used to sit on the class as well.

    The pickers hold a window until the switch sends it, so two devices
    holding one each at the same time is an ordinary thing to do -- and on the
    class it was one pair of timestamps for all of them.
    """
    assert not hasattr(Hub, attribute)


def test_two_accounts_hold_their_own_setup(monkeypatch):
    """Sharing is per account, not global. Two households, two answers."""
    first = make_account(monkeypatch, "one@example.com")
    second = make_account(monkeypatch, "two@example.com")

    first.setup["name"] = "chez nous"

    assert second.setup == {}
    assert first.zones is not second.zones
    assert first.devices is not second.devices


def test_the_hubs_of_one_account_read_the_same_devices(monkeypatch):
    """The point of the account object, stated as a test.

    Two entries on one account used to mean two logins and two copies of the
    same setup view, drifting apart between polls. They now read one list.
    """
    account = make_account(monkeypatch)
    first = Hub.__new__(Hub)
    second = Hub.__new__(Hub)
    first._account = second._account = account

    account.devices.append({"deviceId": 1})

    assert first._account.devices is second._account.devices
    assert second._account.devices == [{"deviceId": 1}]


def test_ten_hubs_dropping_offline_together_cost_one_login(monkeypatch):
    """Every hub flips `online` and calls connect(); only one may log in.

    `online` is the whole reconnect mechanism -- every failure path sets it to
    False and the next poll reconnects -- so an account with five devices has
    five coordinators reaching for the same login on the same beat. Repeated
    failed logins are the one thing that could lock a Cozytouch account out,
    which makes the lock worth pinning rather than assuming.
    """
    account = make_account(monkeypatch)
    logins, setups = [], []

    async def authenticate():
        logins.append(1)
        # yield, so a lock that is not held lets the others straight in
        await asyncio.sleep(0)

    async def read_setup():
        setups.append(1)
        await asyncio.sleep(0)

    account._authenticate = authenticate
    account._read_setup = read_setup

    async def everyone():
        return await asyncio.gather(*(account.connect() for _ in range(10)))

    assert all(asyncio.run(everyone()))
    assert logins == [1]
    assert setups == [1]


def test_a_failed_login_leaves_the_account_offline(monkeypatch):
    """CannotConnect is caught, not raised: setup retries on `online`."""
    account = make_account(monkeypatch)

    async def authenticate():
        raise account_module.CannotConnect

    account._authenticate = authenticate

    assert asyncio.run(account.connect()) is False
    assert account.online is False


def test_zones_are_refreshed_and_not_only_read_once():
    """A rename in the Cozytouch app has to reach Home Assistant.

    Zones were loaded under `if len(self._zones) == 0`, so the first setup view
    won and every later one was discarded. The setup view is re-fetched on each
    reconnect -- which happens whenever the token expires -- so the data was
    there, and thrown away. Zone names feed entity names, so a room renamed in
    the app kept its old name here indefinitely.
    """
    account = stub_account(zones=[{"id": 991904, "name": "Mezzanine"}])

    CozytouchAccount.update_devices_from_json_data(
        account, setup_payload([{"id": 991904, "name": "Chambre 2"}])
    )

    assert account.zones == [{"id": 991904, "name": "Chambre 2"}]


def test_a_setup_view_without_zones_leaves_the_known_ones_alone():
    """Absent is not the same as empty; a partial payload must not wipe them."""
    account = stub_account(zones=[{"id": 991904, "name": "Mezzanine"}])

    CozytouchAccount.update_devices_from_json_data(account, [{"devices": []}])

    assert account.zones == [{"id": 991904, "name": "Mezzanine"}]


def test_the_stored_zones_are_a_copy_of_the_payload():
    """The payload is reused by the caller; storing a reference would alias it."""
    payload = setup_payload([{"id": 991904, "name": "Mezzanine"}])
    account = stub_account()

    CozytouchAccount.update_devices_from_json_data(account, payload)
    payload[0]["zones"][0]["name"] = "muté après coup"

    assert account.zones[0]["name"] == "Mezzanine"


def test_the_setup_view_fills_in_every_device_not_only_one():
    """The payload carries a capability list per device, and all of them are
    kept.

    This used to store capabilities only for the device the hub was built for,
    which is what made a diagnostics dump describe unmapped hardware without
    the capability ids the mapping is written from -- and what made an entry's
    entities wait for a poll of their own before they could be built.
    """
    account = stub_account()

    CozytouchAccount.update_devices_from_json_data(
        account,
        setup_payload(
            [],
            [
                remote_device(1, capabilities=[{"capabilityId": 100, "value": "1"}]),
                remote_device(2, capabilities=[{"capabilityId": 303, "value": "0"}]),
            ],
        ),
    )

    assert [dev["capabilities"] for dev in account.devices] == [
        [{"capabilityId": 100, "value": "1"}],
        [{"capabilityId": 303, "value": "0"}],
    ]


def test_a_device_the_setup_view_stops_listing_is_dropped():
    """Somebody removes a unit in the app; it must not linger here."""
    account = stub_account()

    CozytouchAccount.update_devices_from_json_data(
        account, setup_payload([], [remote_device(1), remote_device(2)])
    )
    CozytouchAccount.update_devices_from_json_data(
        account, setup_payload([], [remote_device(2)])
    )

    assert [dev["deviceId"] for dev in account.devices] == [2]


def remote_device(deviceId, capabilities=None):
    """A device as the setup view reports it, cut down to what is read."""
    return {
        "deviceId": deviceId,
        "name": f"ROOM_{deviceId}",
        "gatewaySerialNumber": "3022-6760-8541",
        "modelId": 557,
        "productId": 65,
        "zoneId": 991904,
        "capabilities": capabilities or [],
    }


def test_the_dev_only_json_loader_is_gone():
    """It read a hardcoded capture from the user's config directory."""
    source = inspect.getsource(CozytouchAccount) + inspect.getsource(Hub)

    assert "_test_load" not in source
    assert "cozytouch_eoras2" not in source
