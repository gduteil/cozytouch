"""What a device says about itself, when the table says nothing.

The table is keyed on `modelId`, which Atlantic's own app never reads : it
classifies on `productId`, the parent's `productId`, and `modelFamily`, all
three of which the setup view sends and `account.py` already stores. The
fall-through asks those instead of giving up, so hardware nobody has mapped
still arrives typed.

These pin the seam, not the ranges -- `test_model.py` owns what the table
answers, and the ranges themselves are copied from `ProductType.java` and
recorded in docs/decisions.md. What matters here is the order of authority :
the table first, the device second, and never the other way round.
"""

from custom_components.cozytouch.model import (
    CozytouchDeviceType,
    get_device_model_infos,
    get_model_infos,
)


def device(deviceId, modelId, productId, masterDeviceId=None, modelFamily=None):
    """A device as the setup view sends it, trimmed to what the model reads."""
    return {
        "deviceId": deviceId,
        "modelId": modelId,
        "productId": productId,
        "masterDeviceId": masterDeviceId,
        "modelFamily": modelFamily,
        "longName": None,
        "customName": None,
        "name": "",
    }


def test_an_override_wins_over_what_the_device_declares():
    """The overrides are the whole safety of this : the device answers first,
    and the twenty-seven ids measured to need a correction get it last.

    556 is the case. Atlantic's catalogue calls the Naviclim box an air
    conditioner -- productId 25 -- which is what makes a room behind it a
    clim. The box drives one rather than being one.
    """
    infos = get_model_infos(556)

    assert infos["type"] is CozytouchDeviceType.HUB
    assert infos["HVACModes"] == {0: "off"}
    assert "fanModes" not in infos


def test_an_unmapped_model_is_typed_by_its_product_id():
    """A `productId` of 53 is TD1, a towel rack, on 360 unnamed ids."""
    infos = get_model_infos(2222, productId=53)

    assert infos["type"] is CozytouchDeviceType.TOWEL_RACK
    assert infos["HVACModes"] == {0: "off", 4: "heat"}


def test_only_a_heat_pump_interface_makes_a_room_something_else():
    """A room's own id is an index. Its parent is asked once, and only an
    Alfea's connected interface answers differently : its slots are heating
    circuits. Every other gateway leaves a room a room, because nothing the
    slot reports separates a radiator from an air conditioner.
    """
    behind_a_clim_hub = [
        device(1, 4242, productId=26, masterDeviceId=2),
        device(2, 1758, productId=96),
    ]
    behind_a_heat_pump = [
        device(1, 4242, productId=26, masterDeviceId=2),
        device(2, 1691, productId=54),
    ]

    assert (
        get_device_model_infos(behind_a_clim_hub, behind_a_clim_hub[0])["type"]
        is CozytouchDeviceType.ROOM
    )
    assert (
        get_device_model_infos(behind_a_heat_pump, behind_a_heat_pump[0])["type"]
        is CozytouchDeviceType.THERMOSTAT
    )


def test_a_room_with_no_parent_is_still_a_room():
    """A gateway that is not on the account leaves the room unattributed.

    It is answered as a room like any other, since the gateway would not have
    changed the answer anyway. Refusing to answer would drop the entities of
    anybody whose gateway was never added. See docs/decisions.md.
    """
    orphan = [device(1, 4242, productId=26, masterDeviceId=99)]

    assert get_device_model_infos(orphan, orphan[0])["type"] is CozytouchDeviceType.ROOM


def test_model_family_answers_where_no_product_id_is_assigned():
    """Atlantic leaves productId 0 on 528 catalogue ids, products included."""
    infos = get_model_infos(4242, productId=0, modelFamily="Water_Heater")

    assert infos["type"] is CozytouchDeviceType.WATER_HEATER


def test_a_device_that_declares_nothing_reads_as_it_always_did():
    """The fall-through keeps its old answer, so nothing regresses."""
    infos = get_model_infos(424242)

    assert infos["type"] is CozytouchDeviceType.UNKNOWN
    assert infos["name"] == "Unknown product (424242)"
    assert infos["HVACModes"] == {0: "off", 4: "heat"}


def test_a_gateway_is_not_typed_by_the_installation_it_fronts():
    """Order of the two signals, and the case that makes it matter.

    The Navizone sends `modelFamily` `Air_Conditioning` -- the installation
    it drives -- while its own `productId` says it is a hub. Reading the
    family first would turn every gateway into a climate entity.
    """
    infos = get_model_infos(4242, productId=96, modelFamily="Air_Conditioning")

    assert infos["type"] is CozytouchDeviceType.HUB


def test_a_derived_gateway_gets_no_absence_setpoint():
    """The gateway reports the away mode; it cannot hold a temperature for it.

    A flag left off is taken as held, so this is silent when wrong: the entity
    appears, and writing to it goes nowhere.
    """
    infos = get_model_infos(4242, productId=96)

    assert infos["type"] is CozytouchDeviceType.HUB
    assert infos["awayModeTemperatureAvailable"] is False


def test_a_derived_room_inherits_its_gateway_flags():
    """A room behind a clim gateway has no absence setpoint either."""
    behind = [
        device(1, 4242, productId=26, masterDeviceId=2),
        device(2, 4243, productId=96),
    ]

    assert (
        get_device_model_infos(behind, behind[0])["awayModeTemperatureAvailable"]
        is False
    )


def test_a_derived_room_is_named_after_its_room():
    """Named the way the mapped rooms are, since that is what a user sees.

    The index counts from one inside its own block, which is what the branches
    did and what an existing install already shows : productId 97 is the first
    room of the second block, not the sixth of one long run.
    """
    behind = [
        device(1, 9999, productId=101, masterDeviceId=2),
        device(2, 9998, productId=96),
    ]

    assert get_device_model_infos(behind, behind[0], "Chambre")["name"] == (
        "Room (Chambre)"
    )
    assert get_device_model_infos(behind, behind[0])["name"] == "Room (#5)"


def test_a_device_the_catalogue_does_not_name_reads_as_the_api_calls_it():
    """"Unknown product (9997)" was the name a user saw for working hardware.

    The setup view says what the device is called, and `longName` is checked
    before `customName` because the vendor sends `---` in it for some slots.
    """
    dev = device(1, 9997, productId=0, modelFamily="Water_Heater")
    dev["longName"] = "Aquastyle 300L"

    infos = get_device_model_infos([dev], dev)

    assert infos["name"] == "Aquastyle 300L"
    assert infos["type"] is CozytouchDeviceType.WATER_HEATER


def circuit(deviceId, modelId, driven_by_room):
    """A TESC heating circuit slot, as issue #110's account reports one."""
    return {
        "deviceId": deviceId,
        "modelId": modelId,
        "productId": modelId - 1333,
        "name": "",
        "capabilities": [
            {"capabilityId": 19, "value": "0.0" if driven_by_room else "20.0"},
            {"capabilityId": 109, "value": "22.28"},
            {"capabilityId": 106000, "value": "1" if driven_by_room else "0"},
        ],
    }


def test_a_circuit_that_holds_its_own_setpoint_is_a_device():
    """Issue #110 : two circuits on one appliance, and only one of them has a
    room slot beside it. The other was typed ZONE, which the config flow
    filters, so it was invisible everywhere -- and it is the only control that
    circuit has.

    The device says which it is. 106000 reads 1 on the five circuits in the
    corpus that have a room slot and 0 on the two that do not, and the
    setpoint agrees: 0 where a room holds it, a real temperature where the
    circuit does. See docs/decisions.md.
    """
    alone = circuit(1, 1389, driven_by_room=False)

    assert get_device_model_infos([alone], alone, "Pièces de vie") == {
        **get_device_model_infos([alone], alone, "Pièces de vie"),
        "type": CozytouchDeviceType.THERMOSTAT,
        "name": "Heating circuit (Pièces de vie)",
    }


def test_a_circuit_a_room_drives_stays_out_of_the_way():
    """Offering it would put the same circuit on the account twice."""
    doubled = circuit(1, 1388, driven_by_room=True)

    assert (
        get_device_model_infos([doubled], doubled, "Chambres")["type"]
        is CozytouchDeviceType.ZONE
    )


def test_a_circuit_with_no_capabilities_yet_stays_out_of_the_way():
    """Between setup and the first poll nothing is known, and a device offered
    on nothing is worse than one offered a poll later.
    """
    infos = get_model_infos(1389)

    assert infos["type"] is CozytouchDeviceType.ZONE
