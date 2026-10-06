"""Atlantic Cozytouch device model mapping.

Mandatory :
    * modelId : modelId of the device
    * name : commercial name of the device.
    * type : device type from CozytouchDeviceType enum.
    * HVACModes : list of available HVAC value/mode pairs

Optional :
    * currentTemperatureAvailable : enable current temperature availability
      (default : True)
    * currentTemperatureAvailableZ1 : enable current temperature availability
      for Z1 (used for HEAT_PUMP, default : True)
    * currentTemperatureAvailableZ2 : enable current temperature availability
      for Z2 (used for HEAT_PUMP, default : True)
    * exhaustTemperatureAvailable : enable exhaust temperature availability
      (default : True)
    * fanModes : list of value/mode pairs
    * swingModes : list of value/mode pairs
    * quietModeAvailable : enable quiet mode availability (default : False)
    * awayModeTemperatureAvailable : enable the absence setpoint (default : True)
    * ecoModeAvailable : enable eco mode availability (default : True)

"""

from enum import StrEnum

from homeassistant.components.climate.const import (
    FAN_AUTO,
    FAN_HIGH,
    FAN_LOW,
    FAN_MEDIUM,
    HVACMode,
)

from .const import (
    AIR_CIRCULATION_SPEED_HIGH,
    AIR_CIRCULATION_SPEED_LOW,
    AIR_CIRCULATION_SPEED_MEDIUM,
    HEATING_MODE_ECO_PLUS,
    HEATING_MODE_MANUAL,
    HEATING_MODE_PROG,
    SWING_MODE_DOWN,
    SWING_MODE_MIDDLE_DOWN,
    SWING_MODE_MIDDLE_UP,
    SWING_MODE_UP,
    narrowed_modes,
)
from .infos import ModelInfos
from .model_catalogue import MODEL_CATALOGUE
from .model_product_ids import PRODUCT_IDS


class CozytouchDeviceType(StrEnum):
    """Device types enum."""

    UNKNOWN = "unknown"
    THERMOSTAT = "thermostat"
    GAZ_BOILER = "gaz_boiler"
    HEAT_PUMP = "heat_pump"
    WATER_HEATER = "water_heater"
    TOWEL_RACK = "towel_rack"
    RADIATOR = "radiator"
    # A slot behind a gateway. The vendor builds one class for all of them and
    # lets the capabilities decide what the screen offers, because nothing a
    # slot reports says whether the room holds a radiator or an air
    # conditioner. See docs/decisions.md.
    ROOM = "room"
    AC = "ac"
    AC_CONTROLLER = "ac_controller"
    HUB = "hub"
    ZONE = "zone"


# What the API calls a zone of a ducted heat pump. The name is the signal
# rather than the model id, and it is the API's `name` and not `customName`
# -- see docs/decisions.md.
ZONE_NAME_PREFIX = "THZONE"

# The mode tables the branches below share. A branch that declares a literal
# instead is one whose hardware differs. Shared objects, never mutated.
OFF_HEAT = {
    0: HVACMode.OFF,
    4: HVACMode.HEAT,
}

# The hubs and the Naviclim box, which report a mode and cannot heat.
OFF_ONLY = {
    0: HVACMode.OFF,
}

MANUAL_ECO_PROG = {
    0: HEATING_MODE_MANUAL,
    3: HEATING_MODE_ECO_PLUS,
    4: HEATING_MODE_PROG,
}

MANUAL_ONLY = {
    0: HEATING_MODE_MANUAL,
}

# What Atlantic's own app classifies on. `ProductType.java` in the decompiled
# client holds these ranges ; the setup view sends the `productId` they index,
# and `account.py` already stores it per device. See docs/decisions.md.
PRODUCT_TYPES: dict[str, frozenset[int]] = {
    "ROOM": frozenset((*range(26, 31), *range(97, 112))),
    "AIR_CONDITIONER_UI": frozenset(range(31, 41)),
    "TH_ZONE": frozenset(range(65, 95)),
    "CESA_V2_MAIN_COMPONENT": frozenset({54}),
    "CESA_V2_GENERATOR": frozenset(range(58, 62)),
    "DHW": frozenset({47, 62}),
    "AIR_CONDITIONER": frozenset({25}),
    "NAVI_HUB": frozenset({63}),
    "ZONI_CLIM_HUB": frozenset({96}),
    "SPLIT_3S_HUB": frozenset({95}),
    "DISCOVER_MASTER": frozenset({6, 44, 112, 113}),
    "HDG2": frozenset({7}),
    "DARWIN_BOILER": frozenset({4}),
    "TD1": frozenset({53}),
    "BD0": frozenset({41}),
    "HE3Z": frozenset({64}),
    "PASS_APC_BOILER": frozenset({1}),
    "PASS_APC_HEAT_PUMP": frozenset({2}),
    "PASS_APC_HYBRID": frozenset({3}),
    "UNDERFLOOR_HEATER": frozenset({121}),
    "CONSOLE": frozenset({122}),
    "WALL_AIR_CONDITIONER": frozenset({123}),
    "REMOTE_CONTROL": frozenset({124}),
    # Not a ProductType of the vendor's : `fromProductId` answers UNKNOWN for
    # 55-57 and its app builds an unknown device. The heating circuits of an
    # Alfea are mapped here, so they need a name of their own.
    "TESC": frozenset(range(55, 58)),
}

# The modes a room air conditioner offers, shared by the mapped branch and the
# derivation below.
AC_HVAC_MODES = {
    0: HVACMode.OFF,
    1: HVACMode.AUTO,
    3: HVACMode.COOL,
    4: HVACMode.HEAT,
    7: HVACMode.FAN_ONLY,
    8: HVACMode.DRY,
}

# The room control of a heating circuit : the app's OFF / ON / AUTO.
CIRCUIT_HVAC_MODES = {
    0: HVACMode.OFF,
    1: HVACMode.AUTO,
    4: HVACMode.HEAT,
}

# What each ProductType is, and the modes that go with it. Five tables cover
# every mapped model, which is why this is a lookup and not a branch.
DERIVED_TYPES: dict[str, tuple[CozytouchDeviceType, dict]] = {
    "AIR_CONDITIONER_UI": (CozytouchDeviceType.AC_CONTROLLER, OFF_ONLY),
    "TESC": (CozytouchDeviceType.ZONE, {}),
    "TH_ZONE": (CozytouchDeviceType.ZONE, {}),
    "CESA_V2_MAIN_COMPONENT": (CozytouchDeviceType.HEAT_PUMP, {}),
    "CESA_V2_GENERATOR": (CozytouchDeviceType.HEAT_PUMP, {}),
    "DHW": (CozytouchDeviceType.WATER_HEATER, OFF_HEAT),
    "AIR_CONDITIONER": (CozytouchDeviceType.AC, AC_HVAC_MODES),
    "NAVI_HUB": (CozytouchDeviceType.HUB, OFF_ONLY),
    "ZONI_CLIM_HUB": (CozytouchDeviceType.HUB, OFF_ONLY),
    "SPLIT_3S_HUB": (CozytouchDeviceType.HUB, OFF_ONLY),
    "DISCOVER_MASTER": (CozytouchDeviceType.HUB, OFF_ONLY),
    "HDG2": (CozytouchDeviceType.WATER_HEATER, OFF_HEAT),
    "DARWIN_BOILER": (CozytouchDeviceType.THERMOSTAT, OFF_HEAT),
    "TD1": (CozytouchDeviceType.TOWEL_RACK, OFF_HEAT),
    "BD0": (CozytouchDeviceType.RADIATOR, OFF_HEAT),
    "HE3Z": (CozytouchDeviceType.THERMOSTAT, OFF_HEAT),
    "PASS_APC_BOILER": (CozytouchDeviceType.GAZ_BOILER, OFF_HEAT),
    "PASS_APC_HEAT_PUMP": (CozytouchDeviceType.HEAT_PUMP, OFF_HEAT),
    "PASS_APC_HYBRID": (CozytouchDeviceType.HEAT_PUMP, OFF_HEAT),
    "UNDERFLOOR_HEATER": (CozytouchDeviceType.RADIATOR, OFF_HEAT),
    "CONSOLE": (CozytouchDeviceType.AC, AC_HVAC_MODES),
    "WALL_AIR_CONDITIONER": (CozytouchDeviceType.AC, AC_HVAC_MODES),
}


# The other half of the vendor's classification : `productId` says which part
# of an appliance a device is, `modelFamily` says what it heats or cools. Both
# are enums of Atlantic's own -- this is `ModelFamily.java`, every member of
# it. It is read only after `productId`, which is what keeps a gateway from
# being typed by the installation it fronts : the Navizone sends
# `Air_Conditioning` and is a hub. See docs/decisions.md.
#
# `Heat_Interface_Unit` and `Double_Flow_Ventilation` are the two members left
# out : nothing here is either, and guessing a type for hardware nobody has
# reported is how a device ends up with entities it cannot drive.
MODEL_FAMILIES: dict[str | None, CozytouchDeviceType] = {
    "Air_Conditioning": CozytouchDeviceType.AC,
    "Boiler": CozytouchDeviceType.GAZ_BOILER,
    "Connectivity_Box": CozytouchDeviceType.HUB,
    "Heat_Pump": CozytouchDeviceType.HEAT_PUMP,
    "Hybrid_Heat_Pump": CozytouchDeviceType.HEAT_PUMP,
    "Radiator": CozytouchDeviceType.RADIATOR,
    "Thermodynamic_Water_Heater": CozytouchDeviceType.WATER_HEATER,
    "Thermostat": CozytouchDeviceType.THERMOSTAT,
    "Towel_Dryer": CozytouchDeviceType.TOWEL_RACK,
    "Underfloor_Heater": CozytouchDeviceType.RADIATOR,
    "Water_Heater": CozytouchDeviceType.WATER_HEATER,
}


# The flags a derived device needs beyond its type. A gateway fronting an air
# conditioning installation reports the away mode itself -- capability 152 sits
# on it and on nothing else -- but has no absence *setpoint*, which is what the
# mapped gateway branches say too. Left off means `capability.py` takes the
# flag as held, so a gateway missing from here grows a setpoint it cannot
# drive. See docs/decisions.md.
# A room inherits these from its gateway, so the eco suppression the mapped
# rooms carry reaches a derived one too. On the gateway itself it says the same
# thing and costs nothing : a box reports neither capability.
_AC_GATEWAY = {"awayModeTemperatureAvailable": False}

# Everything a room air conditioner carries beyond its type and its modes.
_AC_ROOM = {
    **_AC_GATEWAY,
    "ecoModeAvailable": False,
    "quietModeAvailable": True,
    "AirCirculationSpeeds": {
        1: AIR_CIRCULATION_SPEED_LOW,
        2: AIR_CIRCULATION_SPEED_MEDIUM,
        3: AIR_CIRCULATION_SPEED_HIGH,
    },
    "fanModes": {1: FAN_LOW, 2: FAN_MEDIUM, 3: FAN_HIGH, 5: FAN_AUTO},
    "swingModes": {
        1: SWING_MODE_UP,
        2: SWING_MODE_MIDDLE_UP,
        3: SWING_MODE_MIDDLE_DOWN,
        4: SWING_MODE_DOWN,
    },
}

# A water heater's modes, which every one of them reads the same way.
_PROG = {"HeatingModes": MANUAL_ECO_PROG}

# The half of an appliance that reports readings and drives nothing : it has no
# mode capability at all, where everything else answers on 7 or 8.
_NO_CLIMATE = {"HVACModesCapabilityId": set()}

DERIVED_FLAGS: dict[str | None, dict] = {
    "NAVI_HUB": _AC_GATEWAY,
    "ZONI_CLIM_HUB": _AC_GATEWAY,
    "SPLIT_3S_HUB": _AC_GATEWAY,
    "AIR_CONDITIONER": _AC_ROOM,
    "ROOM": _AC_ROOM,
    "DHW": _PROG,
    "HDG2": _PROG,
    "CESA_V2_MAIN_COMPONENT": _NO_CLIMATE,
    "CESA_V2_GENERATOR": _NO_CLIMATE,
}

# What a room is, given the interface it hangs off. Only the heating circuit
# of an Alfea is told apart : behind every gateway a room is a room, which is
# what the vendor's own client does -- one class for the lot, and the
# capabilities decide what it offers. Nothing a slot reports says whether the
# room holds a radiator or an air conditioner. See docs/decisions.md.
ROOM_BEHIND: dict[str | None, tuple[CozytouchDeviceType, dict, str, dict]] = {
    "CESA_V2_MAIN_COMPONENT": (
        CozytouchDeviceType.THERMOSTAT,
        CIRCUIT_HVAC_MODES,
        "Heating circuit",
        {},
    ),
}

# Every other interface answers the same : a room.
ROOM_ANYWHERE = (CozytouchDeviceType.ROOM, AC_HVAC_MODES, "Room", _AC_ROOM)


def product_type(productId: int | None) -> str | None:
    """The vendor's name for what a productId is, or None for one it skips."""
    if productId is None:
        return None
    return next(
        (name for name, ids in PRODUCT_TYPES.items() if productId in ids), None
    )


# The slots named after their position rather than after a product : the word
# they are called by, and the productId their numbering counts from. Rooms are
# not here because the interface they hang off decides their word too.
SLOT_LABELS: dict[str, tuple[str, int]] = {
    "AIR_CONDITIONER_UI": ("Air Conditioner User Interface", 30),
    "TESC": ("Heating circuit", 54),
}


def room_index(productId: int) -> int:
    """The number a room is called by, counted inside its own block.

    Atlantic numbers rooms `ROOM_0` to `ROOM_19` over two blocks, 26-30 and
    97-111. The names here count from one inside each block, which is what the
    branches did and what an existing install already shows.
    """
    return productId - 25 if productId <= 30 else productId - 96


# Whether the vendor's own app offers this product the identify button. It is
# not a capability the device reports : `GacomaDeviceFactory` picks a class
# from the pair (own productId, parent's) and each class carries the answer as
# a constant. See docs/decisions.md.
WINKABLE_KINDS = frozenset({"BD0", "TD1", "AIR_CONDITIONER_UI"})
WINKABLE_HUBS = frozenset({"NAVI_HUB", "ZONI_CLIM_HUB", "SPLIT_3S_HUB"})


def winkable(kind: str | None, masterKind: str | None) -> bool:
    """Whether capability 100078 is a control here rather than a reading."""
    if kind == "TH_ZONE":
        # Behind one of those hubs it is a TransverseUI, which winks ; behind
        # anything else the factory builds nothing at all.
        return masterKind in WINKABLE_HUBS
    return kind in WINKABLE_KINDS


def derive(
    modelInfos: ModelInfos,
    productId: int | None,
    modelFamily: str | None,
    masterKind: str | None,
    zoneName: str | None,
    fallbackName: str | None,
) -> None:
    """Fill in what a device says about itself, for an id no branch names.

    The table stays the override layer : this only answers where it said
    nothing. See docs/decisions.md.
    """
    kind = product_type(productId)
    if winkable(kind, masterKind):
        modelInfos.winkable = True
    label = None
    if kind == "ROOM" and productId is not None:
        parent = masterKind
        # No parent on the account : answered as an air conditioner, which is
        # what the branch this replaced did. A room is a clim far more often
        # than not, and refusing to answer would drop the entities of anyone
        # whose gateway is not set up. See docs/decisions.md.
        # A room carries its own flags, never its parent's : the interface of
        # an Alfea has no climate capability and its circuits do, and letting
        # one inherit the other emptied the circuit's modes. See
        # docs/decisions.md.
        deviceType, modes, label, flags = ROOM_BEHIND.get(parent, ROOM_ANYWHERE)
        if label:
            label += f" (#{room_index(productId)})"
        else:
            label = None
    elif kind in DERIVED_TYPES:
        deviceType, modes = DERIVED_TYPES[kind]
        flags = DERIVED_FLAGS.get(kind, {})
        if kind in SLOT_LABELS and productId is not None:
            word, base = SLOT_LABELS[kind]
            label = f"{word} (#{productId - base})"
    else:
        deviceType = MODEL_FAMILIES.get(modelFamily, CozytouchDeviceType.UNKNOWN)
        modes, flags = OFF_HEAT, {}

    modelInfos.type = deviceType
    modelInfos.HVACModes = modes
    for flag, held in flags.items():
        setattr(modelInfos, flag, held)

    if label is not None:
        # Named after its room the way the mapped ones are, with the vendor's
        # own index where the account names no zone.
        modelInfos.name = f"{label.split(' (#')[0]} ({zoneName})" if zoneName else label
    else:
        # The catalogue names the product ; where it does not, the device does.
        # Nobody should read "Unknown product" for hardware the API describes.
        modelInfos.name = (
            MODEL_CATALOGUE.get(modelInfos.modelId)
            or fallbackName
            or "Unknown product (" + str(modelInfos.modelId) + ")"
        )


OVERRIDES: dict[int, dict] = {
    76: {
        "HeatingModes": MANUAL_ONLY,
        "currentTemperatureAvailableZ1": False,
        "currentTemperatureAvailableZ2": True,
        "exhaustTemperatureAvailable": False,
    },
    211: {
        "HVACModesCapabilityId": {1, 2},
        "HVACModes": {0: HVACMode.OFF, 1: HVACMode.HEAT, 2: HVACMode.AUTO},
        "HeatingModes": MANUAL_ONLY,
        "currentTemperatureAvailableZ1": True,
        "currentTemperatureAvailableZ2": True,
        "exhaustTemperatureAvailable": False,
        "type": CozytouchDeviceType.HEAT_PUMP,
    },
    219: {
        "HVACModesCapabilityId": {1, 2},
        "HVACModes": {0: HVACMode.OFF, 1: HVACMode.HEAT, 2: HVACMode.AUTO},
        "HeatingModes": MANUAL_ONLY,
        "currentTemperatureAvailableZ1": True,
        "currentTemperatureAvailableZ2": True,
        "exhaustTemperatureAvailable": False,
    },
    227: {"HVACModes": OFF_HEAT, "type": CozytouchDeviceType.GAZ_BOILER},
    418: {
        "HVACModes": OFF_HEAT,
        "currentTemperatureAvailableZ1": True,
        "currentTemperatureAvailableZ2": False,
        "exhaustTemperatureAvailable": True,
        "overrideModeAvailable": True,
        "type": CozytouchDeviceType.THERMOSTAT,
    },
    # The catalogue calls the Naviclim box an air conditioner, and the app
    # agrees -- it is what makes a room behind it a clim. It drives one rather
    # than being one, so nothing of the room tables belongs on it.
    556: {
        "AirCirculationSpeeds": None,
        "HVACModes": OFF_ONLY,
        "ecoModeAvailable": None,
        "fanModes": None,
        "quietModeAvailable": None,
        "swingModes": None,
        "type": CozytouchDeviceType.HUB,
    },
    664: {
        "HVACModes": OFF_HEAT,
        "HeatingModes": MANUAL_ECO_PROG,
        "type": CozytouchDeviceType.WATER_HEATER,
    },
    754: {
        "HVACModes": OFF_HEAT,
        "HeatingModes": MANUAL_ECO_PROG,
        "type": CozytouchDeviceType.WATER_HEATER,
    },
    957: {
        "HVACModes": OFF_HEAT,
        "HeatingModes": MANUAL_ECO_PROG,
        "type": CozytouchDeviceType.WATER_HEATER,
    },
    1010: {
        "HVACModes": OFF_HEAT,
        "HeatingModes": MANUAL_ECO_PROG,
        "type": CozytouchDeviceType.WATER_HEATER,
    },
    1444: {"HVACModes": OFF_HEAT, "type": CozytouchDeviceType.GAZ_BOILER},
    1445: {"HVACModes": OFF_HEAT, "type": CozytouchDeviceType.GAZ_BOILER},
    1446: {"HVACModes": OFF_HEAT, "type": CozytouchDeviceType.GAZ_BOILER},
    1447: {"HVACModes": OFF_HEAT, "type": CozytouchDeviceType.GAZ_BOILER},
    1448: {"HVACModes": OFF_HEAT, "type": CozytouchDeviceType.GAZ_BOILER},
    1954: {"HeatingModes": {0: "manual", 3: "eco_plus"}},
    1955: {"HeatingModes": {0: "manual", 3: "eco_plus"}},
    1956: {"HeatingModes": {0: "manual", 3: "eco_plus"}},
    1957: {"HeatingModes": {0: "manual", 3: "eco_plus"}},
}

# The only names the vendor's catalogue does not carry. Everything else is
# named by it : the names this project used to spell itself were often less
# precise than the vendor's -- three Aeromax SPLIT 3 volumes shared one string
# where the catalogue names each. See docs/decisions.md.
MODEL_NAMES: dict[int, str] = {
    236: "Sauter Phazy",
    556: "Naviclim Hub",
    1353: "Calypso Split Interface",
    1376: "Domestic hot water",
    1391: "Generator",
    1763: "FLAT/S4 IOTHUB",
}


def apply_capabilities(
    modelInfos: ModelInfos, capabilities: dict[int, str]
) -> None:
    """Let the device have the last word about itself.

    Two readings, both of them the device's own. It reports capability 100022
    as a bitmask over the mode values, which is a complete answer and needs no
    table ; and if it reports none of the capabilities its modes would arrive
    on, it has no modes at all whatever any table says. See docs/decisions.md.
    """
    # An empty list is a device whose capabilities have not arrived yet --
    # `account.py` creates one that way and fills it on the first poll -- and
    # not a device that reports nothing. Reading it as the latter drops the
    # modes of every device between setup and the first poll.
    if not capabilities:
        return

    # A heating circuit whose setpoint is held by a room slot is that room's
    # business, and offering it as a device of its own would put the same
    # circuit on the account twice. One that holds its own is the only control
    # there is, and was invisible until now (issue #110). The device says
    # which it is on 106000. See docs/decisions.md.
    if modelInfos.type is CozytouchDeviceType.ZONE and modelInfos.name.startswith(
        "Heating circuit"
    ):
        if capabilities.get(106000) == "0":
            modelInfos.type = CozytouchDeviceType.THERMOSTAT
        return

    if not modelInfos.HVACModes:
        return

    if not modelInfos.HVACModesCapabilityId & capabilities.keys():
        # Nothing carries a mode here, so there is no climate entity to build.
        modelInfos.HVACModes = {}
        return

    modelInfos.HVACModes = narrowed_modes(
        modelInfos.HVACModes, capabilities.get(100022)
    )


def get_device_model_infos(
    devices: list[dict], dev: dict, zoneName: str | None = None
) -> ModelInfos:
    """The table's answer for one device, given every device on its account.

    The entry point every caller uses, because three of the inputs are
    properties of the account rather than of the device : the name a zone is
    recognised by, the interface a room hangs off -- which is what says whether
    a room is a radiator or an air conditioner -- and what the API calls the
    device.
    """
    masterDeviceId = dev.get("masterDeviceId")
    master = next(
        (found for found in devices if found["deviceId"] == masterDeviceId), None
    )

    return get_model_infos(
        dev["modelId"],
        zoneName,
        dev.get("name"),
        master["modelId"] if master else None,
        productId=dev.get("productId"),
        modelFamily=dev.get("modelFamily"),
        masterProductId=master.get("productId") if master else None,
        masterFamily=master.get("modelFamily") if master else None,
        capabilities={
            int(found["capabilityId"]): found["value"]
            for found in dev.get("capabilities") or ()
        },
        # What the API calls the device, for hardware the catalogue does not
        # name. "---" is what it sends for a zone rather than leaving the
        # field out, so it is read as nothing. See docs/decisions.md.
        fallbackName=next(
            (
                found
                for found in (dev.get("longName"), dev.get("customName"))
                if found and found != "---"
            ),
            None,
        ),
    )


def get_model_infos(
    modelId: int,
    zoneName: str | None = None,
    deviceName: str | None = None,
    masterModelId: int | None = None,
    *,
    productId: int | None = None,
    modelFamily: str | None = None,
    masterProductId: int | None = None,
    masterFamily: str | None = None,
    fallbackName: str | None = None,
    capabilities: dict[int, str] | None = None,
) -> ModelInfos:
    """What this integration knows about one device.

    The device answers first and the overrides correct it, which is the way
    round the vendor's own client works. `productId` comes from the device
    where there is one and from the catalogue otherwise, so an id with no
    device beside it -- a dump, a repair, a test -- still resolves.
    """
    modelInfos = ModelInfos(modelId=modelId, HVACModesCapabilityId={7, 8})

    if deviceName is not None and deviceName.startswith(ZONE_NAME_PREFIX):
        # A zone of a ducted heat pump, recognised by its name because the
        # model id it arrives under is its parent's. See docs/decisions.md.
        modelInfos.name = f"Zone ({zoneName})" if zoneName else deviceName
        modelInfos.type = CozytouchDeviceType.ZONE
        # Empty on purpose : off/heat made a zone read as a thermostat.
        modelInfos.HVACModes = {}
        return modelInfos

    # 0 is what the vendor leaves on a model it assigns no product type, so it
    # is read as nothing and the catalogue answers instead.
    if not productId:
        productId = PRODUCT_IDS.get(modelId)
    if not masterProductId and masterModelId is not None:
        masterProductId = PRODUCT_IDS.get(masterModelId)

    # The interface a room hangs off, by its productId where it has one and by
    # the family it declares where the vendor assigns none.
    masterKind = product_type(masterProductId) or masterFamily

    derive(modelInfos, productId, modelFamily, masterKind, zoneName, fallbackName)

    # What the device reports outranks what any table guessed for its model,
    # which is the whole direction of this. A caller with no device beside the
    # id passes nothing and keeps the table's answer.
    if capabilities is not None:
        apply_capabilities(modelInfos, capabilities)

    # What the device gets wrong about itself, and what it cannot say. Every
    # entry was measured against the branch it replaced ; `None` removes a
    # field the derivation set. See docs/decisions.md.
    for key, value in OVERRIDES.get(modelId, {}).items():
        if value is None:
            modelInfos.pop(key, None)
        else:
            setattr(modelInfos, key, value)

    # Names this project spells differently from the vendor's catalogue.
    # Renaming one renames somebody's device, which is why they are kept.
    if modelId in MODEL_NAMES:
        modelInfos.name = MODEL_NAMES[modelId]

    return modelInfos
