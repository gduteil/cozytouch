"""Tests for the diagnostics dump.

The dump exists so someone with unmapped hardware can hand over what the API
says about it without editing a JSON by hand. Two things have to hold for that
to be worth anything: an unmapped model has to be visible as unmapped, and the
capability ids nothing names have to be listed rather than silently dropped.
Those are what a maintainer reads first, and they are what these tests pin.

Hub.get_diagnostics is called unbound, against a stand-in carrying only the
attributes it touches -- an account holding the devices, and the id of the one
this entry drives. Building a real Hub means a DataUpdateCoordinator and a
running HomeAssistant, none of which the method uses.
"""

from types import SimpleNamespace

import pytest

from custom_components.cozytouch import diagnostics
from custom_components.cozytouch.account import CozytouchAccount
from custom_components.cozytouch.diagnostics import describe
from custom_components.cozytouch.hub import Hub


def make_hub(devices, deviceId, zones=None):
    """A stand-in exposing only what get_diagnostics reads."""
    account = SimpleNamespace(
        devices=devices,
        setup={"id": 1532156, "name": "setup1"},
        zones=zones if zones is not None else [],
    )
    hub = SimpleNamespace(
        _account=account,
        _deviceId=deviceId,
        # the devices somebody added, which is what isConfiguredHere reports
        _entry=SimpleNamespace(
            subentries={
                f"sub-{deviceId}": SimpleNamespace(data={"deviceId": deviceId})
            }
        ),
    )
    hub.get_zone_name = lambda zoneId=None: next(
        (z["name"] for z in account.zones if z.get("id") == zoneId), str(zoneId)
    )
    # get_diagnostics reads the named/unnamed split off the hub rather than
    # working it out again, so the stand-in has to carry the real one.
    hub.get_capability_names = lambda deviceId=None: Hub.get_capability_names(
        hub, deviceId
    )
    return hub


def test_the_dump_carries_every_device_the_account_has():
    """Including the ones the config flow does not offer.

    A zone used to be left out of both, on the grounds that a dump is read to
    find hardware that has to be mapped and a zone is not hardware. That held
    for a zone of a ducted heat pump, which reports two ids resolving to
    nothing. It did not hold for everything typed the same way, and the cost
    was paid by somebody whose heating circuit was invisible in the dump, in
    the device list and in the report they were asked to send -- so there was
    no way to find out what it even was. A dump says what the account has;
    what to *offer* is the config flow's question, and it still asks it.
    """
    hub = make_hub(
        [
            device(1, 557, name="ROOM_0"),
            device(2, 1505, name="THZONE_0"),
        ],
        deviceId=1,
    )

    reported = Hub.get_diagnostics(hub)

    assert [dev["name"] for dev in reported["devices"]] == ["ROOM_0", "THZONE_0"]


def test_a_zone_is_not_offered_when_adding_the_integration():
    """Adding it would create a device with an empty page behind it. The list
    the config flow reads is the account's, which is where the filter lives.
    """
    account = SimpleNamespace(
        devices=[
            device(1, 557, name="ROOM_0"),
            device(2, 1505, name="THZONE_0"),
        ]
    )

    summaries = CozytouchAccount.device_summaries(account)

    assert [dev["name"] for dev in summaries] == ["ROOM_0"]


def device(
    deviceId, modelId, capabilities=None, name="ROOM_0", zoneId=991904, productId=0
):
    """A device the API could send. `productId` 0 is the value Atlantic leaves
    on a model it assigns no product type, so the default classifies nothing
    and a case that wants the derivation to fire passes its own.
    """
    return {
        "deviceId": deviceId,
        "name": name,
        "modelId": modelId,
        "productId": productId,
        "zoneId": zoneId,
        "gatewaySerialNumber": "1234-5678-0000",
        "tags": [],
        "capabilities": capabilities or [],
    }


def test_a_device_nothing_can_type_reads_as_unknown():
    """What a dump is read for. There used to be an `isMapped` beside this,
    from when a hand-written table was the only thing that could answer; the
    type says it now, and says it for a device the table never named.
    """
    hub = make_hub([device(1, 9999)], deviceId=1)

    reported = Hub.get_diagnostics(hub)["devices"][0]

    assert reported["modelId"] == 9999
    assert reported["model"]["type"] == "unknown"
    assert reported["model"]["name"] == "Unknown product (9999)"


def test_a_mapped_model_carries_its_name_and_type():
    hub = make_hub([device(1, 557)], deviceId=1)

    reported = Hub.get_diagnostics(hub)["devices"][0]

    assert reported["model"]["name"] == "Room (#1)"
    assert reported["model"]["type"] == "room"


def test_capabilities_split_into_what_is_named_and_what_is_not():
    """303 is mapped, 999 is nothing at all; a report needs to show both.

    The unmapped one is an id no device reports and the vendor's catalogue
    does not declare, rather than one the mapping has not got to yet: the
    naming pass keeps taking those, and this case is about the split and not
    about which ids happen to be missing this week.
    """
    hub = make_hub(
        [
            device(
                1,
                557,
                capabilities=[
                    {"capabilityId": 303, "value": "0"},
                    {"capabilityId": 999, "value": "[72,88]"},
                ],
            )
        ],
        deviceId=1,
    )

    caps = Hub.get_diagnostics(hub)["devices"][0]["capabilities"]

    assert caps["mapped"][303] == "error_code"
    assert caps["unmapped"] == [999]
    assert caps["values"][999] == "[72,88]"


def test_devices_this_entry_does_not_drive_are_still_described():
    """The account holds every device the setup view returned, capabilities
    included, so a dump covers hardware nobody has added yet.

    That is the point of the dump: the capability ids of an unmapped model are
    what a mapping gets written from, and asking somebody to add the device as
    an entry first only to read them was a step that lost reports. What
    `isConfiguredHere` still says is which one this entry drives, and so which
    list came from a live poll rather than from the last setup view.
    """
    hub = make_hub(
        [
            device(1, 557, capabilities=[{"capabilityId": 303, "value": "0"}]),
            device(
                2, 1457, name="HUB",
                capabilities=[{"capabilityId": 100, "value": "1"}],
            ),
        ],
        deviceId=1,
    )

    driven, other = Hub.get_diagnostics(hub)["devices"]

    assert driven["isConfiguredHere"] is True
    assert driven["capabilities"]["values"] == {303: "0"}
    assert other["isConfiguredHere"] is False
    assert other["capabilities"]["values"] == {100: "1"}


def test_the_zone_name_is_resolved_rather_than_left_as_an_id():
    hub = make_hub(
        [device(1, 557, zoneId=991904)],
        deviceId=1,
        zones=[{"id": 991904, "name": "Chambre 2"}],
    )

    assert Hub.get_diagnostics(hub)["devices"][0]["zoneName"] == "Chambre 2"


def test_model_flags_are_reported_so_a_report_shows_what_was_wired():
    """Which optional features a model declares decides its entity list."""
    hub = make_hub([device(1, 557)], deviceId=1)

    infos = Hub.get_diagnostics(hub)["devices"][0]["model"]["infos"]

    assert infos["ecoModeAvailable"] == "False"
    assert infos["quietModeAvailable"] == "True"
    assert "name" not in infos
    assert "type" not in infos


def test_what_the_api_itself_calls_the_device_is_carried_through():
    """A dump is what an unmapped model gets mapped from, so the vendor's own
    name and family for it are worth more than the ones our table invented --
    and customName is the one name a reporter recognises, since it is the one
    they typed in the vendor app.
    """
    hub = make_hub(
        [
            device(1, 9999)
            | {
                "customName": "Living room hub",
                "longName": "HUB Navizone",
                "modelFamily": "Air_Conditioning",
                "productRange": None,
                "masterDeviceId": None,
                "isAvailable": True,
            }
        ],
        deviceId=1,
    )

    reported = Hub.get_diagnostics(hub)["devices"][0]

    assert reported["customName"] == "Living room hub"
    assert reported["longName"] == "HUB Navizone"
    assert reported["modelFamily"] == "Air_Conditioning"
    assert reported["isAvailable"] is True


def test_fields_the_api_leaves_out_read_as_none_rather_than_failing():
    """Only the gateway carried a modelFamily on the account these were read
    from; a room unit reports null, and a dump has to survive that.
    """
    hub = make_hub([device(1, 557)], deviceId=1)

    reported = Hub.get_diagnostics(hub)["devices"][0]

    assert reported["modelFamily"] is None
    assert reported["masterDeviceId"] is None


@pytest.mark.parametrize("key", ["setup", "zones", "devices"])
def test_the_dump_carries_the_sections_a_report_is_built_from(key):
    hub = make_hub([device(1, 557)], deviceId=1)

    assert key in Hub.get_diagnostics(hub)


def catalogue_row(**overrides):
    """One row shaped as `/magellan/productmodels/capabilities` sends it."""
    return {
        "id": 117,
        "name": "ROOM1_AmbientRoom",
        "description": "Ambient temperature in the Room 1",
        "type": 2,
        "accessType": 3,
        "unit": "°C",
        "min": -273.15,
        "max": 327.67,
        "resolution": 0.01,
        "enum": None,
        "structId": None,
    } | overrides


def test_a_described_id_carries_the_identifier_and_the_prose():
    """Atlantic's name is what a report can be searched for; its description
    is what says what the thing is. Both, not one.
    """
    described = describe(catalogue_row())

    assert described["name"] == "ROOM1_AmbientRoom"
    assert described["description"] == "Ambient temperature in the Room 1"
    assert described["type"] == "float"
    assert described["unit"] == "°C"


def test_writability_is_read_off_the_access_bitmask():
    """Bit 4, and it is the first question asked about an unmapped id:
    guessing it wrong is how a control that writes into the void ships.
    """
    assert describe(catalogue_row(accessType=3))["writable"] is False
    assert describe(catalogue_row(accessType=7))["writable"] is True


def test_an_enum_arrives_as_its_members():
    described = describe(
        catalogue_row(
            type=5,
            enum={"values": [{"Key": 0, "Value": "Off"}, {"Key": 1, "Value": "On"}]},
        )
    )

    assert described["values"] == {"0": "Off", "1": "On"}


def test_the_dump_describes_every_id_reported_and_only_those():
    """Two halves of one rule. An id named *wrongly* makes an entity that
    looks fine and reads the wrong thing, so the mapped ones are described
    too. And the catalogue covers Atlantic's whole range, so the ids nothing
    on this account reports are left out rather than shipped in every report.
    """
    dump = {
        "devices": [
            {
                "capabilities": {
                    "mapped": {117: "thermostat_temperature_z1"},
                    "unmapped": [999],
                    "values": {117: "19.5", 999: "3"},
                }
            }
        ]
    }
    catalogue = {
        117: catalogue_row(),
        999: catalogue_row(id=999),
        # A boiler's, on an account that has no boiler.
        44: catalogue_row(id=44),
    }

    described = diagnostics._with_what_atlantic_says(dump, catalogue)

    assert set(described["atlanticSays"]) == {117, 999}


def test_a_row_states_only_what_the_catalogue_states():
    """Most ids carry no unit and no enum. A key present and empty reads as
    "Atlantic says there is none", which is not what a null field means.
    """
    described = describe(
        {"id": 305, "name": "X", "description": "", "type": 1, "accessType": 1}
    )

    assert "unit" not in described
    assert "values" not in described
    assert described["writable"] is False


def test_a_suppressed_id_is_not_reported_as_unnamed():
    """`get_capability_infos` answers None for an id nothing knows and an
    empty `CapabilityInfos` for one it knows and deliberately does not turn
    into an entity here. Both are falsy, and reading them the same way filed a
    decision as a gap.
    """
    reported = [
        # A room behind an air conditioner gateway: 40 is its setpoint, 172
        # has a row gated on a flag this product does not have, and 999 is
        # nothing at all.
        {"capabilityId": 40, "value": "19"},
        {"capabilityId": 172, "value": "26.5"},
        {"capabilityId": 999, "value": "1"},
    ]
    hub = make_hub(
        [device(1, 557, capabilities=reported, productId=26)], deviceId=1
    )

    mapped, suppressed, unmapped = hub.get_capability_names(1)

    assert 40 in mapped
    assert suppressed == [172]
    assert unmapped == [999]
