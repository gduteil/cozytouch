"""How a capability id becomes an entity.

The mechanism only : which row answers an id, how a descriptor's number
reads, and the handful of ids no row can decide. The rows themselves are in
`capability_table.py`, which is the file to open to add a device.
"""

from .capability_table import (
    CAPABILITIES,
    ELECTRIC_HEATERS,
    SUPPRESSED_CAPABILITIES,
    hidden_by_a_calendar,
)
from .const import program_days
from .infos import CapabilityCategory, CapabilityInfos, CapabilityType, ModelInfos
from .model import CozytouchDeviceType


# The API's own families split the electric heaters in two -- Radiator and
# Towel_Dryer -- and the mapping follows, because "seche-serviettes" in front
# of a radiator is what gduteil/cozytouch#172 was about. Same wiring on this
# side of it : both report the same ids and mean the same things by them. The
# one place they part is 100506, below.
def describe_capability_value(capabilityId: int, value) -> str | None:
    """Read a descriptor capability as what it says, or None if nothing does.

    The row says how: `reads_as` when the number is looked up whole, `bits`
    when it is a sum of them. A row that says neither is a number nobody has
    decoded, and it reaches the entity as it came.

    Bits nothing names are kept as a count rather than dropped: these entities
    exist to investigate hardware nobody here owns, and a bit the table does
    not cover is exactly what such a reader is after.
    """
    row = CAPABILITIES.get(capabilityId)
    if row is None:
        return None

    if row.reads_as is not None:
        return row.reads_as.get(str(value).strip())

    if row.bits is None:
        return None

    try:
        mask = int(str(value).strip())
    except (TypeError, ValueError):
        return None

    if mask == 0:
        return "none"

    named = [label for bit, label in row.bits if mask & bit]

    known = 0
    for bit, _ in row.bits:
        known |= bit
    leftover = mask & ~known
    if leftover:
        named.append(f"unknown ({leftover})")

    return ", ".join(named) if named else None


# The program blocks whose slots hold a room temperature. The hot-water block
# (237-243) is deliberately out: its slots really do carry 50-65 °C, so the
# hundredths rule below would read a 65 °C tank as 0.65 °C.
THERMOSTAT_PROG_IDS = program_days("heating") | program_days("cooling")


def read_setpoint(capabilityId: int | None, value):
    """Read a program slot's target temperature.

    Some firmwares store it in hundredths -- the vendor app divides anything
    above 40 by 100 and shows the result, so a slot reading 1950 is 19.5 °C
    and not a device asking for 1950 °C. No capture here has ever shown one,
    so this is the app's rule and nothing more; see docs/decisions.md.
    """
    if capabilityId not in THERMOSTAT_PROG_IDS:
        return value

    try:
        setpoint = float(value)
    except (TypeError, ValueError):
        return value

    return setpoint / 100 if setpoint > 40 else setpoint


def _wire_override(capability: CapabilityInfos) -> None:
    capability.progOverrideCapabilityId = 157
    capability.progOverrideTotalTimeCapabilityId = 158
    capability.progOverrideTimeCapabilityId = 159


def _wire_program(capability: CapabilityInfos) -> None:
    capability.progCapabilityId = 184
    _wire_override(capability)


def _wire_cooling(capability: CapabilityInfos) -> None:
    capability.targetCoolCapabilityId = 177
    capability.lowestCoolValueCapabilityId = 162
    capability.highestCoolValueCapabilityId = 163


def _wire_presets(
    capability: CapabilityInfos,
    modelInfos: ModelInfos,
    availableCapabilityIds: set[int],
) -> None:
    if 100506 in availableCapabilityIds:
        capability.activityCapabilityId = 100506
    if (
        modelInfos.get("ecoModeAvailable", True)
        and 100507 in availableCapabilityIds
    ):
        capability.ecoCapabilityId = 100507
    if 100505 in availableCapabilityIds:
        capability.boostCapabilityId = 100505


def _room_entity(
    capability: CapabilityInfos,
    modelInfos: ModelInfos,
    availableCapabilityIds: set[int],
) -> None:
    # One room, whatever is in it. The vendor's own client does the same :
    # a single class behind every gateway, and the capabilities decide
    # what it offers, because nothing the slot reports says whether the
    # room holds a radiator or an air conditioner. Every id below is asked
    # for rather than assumed. See docs/decisions.md.
    capability.name = "room"
    capability.icon = "mdi:home-thermometer"
    if 153 in availableCapabilityIds:
        capability.heatingActiveCapabilityId = 153
    if 184 in availableCapabilityIds:
        capability.progCapabilityId = 184
    if 157 in availableCapabilityIds:
        _wire_override(capability)
    if 177 in availableCapabilityIds:
        _wire_cooling(capability)
    _wire_presets(capability, modelInfos, availableCapabilityIds)


def _climate_entity(
    capability: CapabilityInfos,
    capabilityId: int,
    modelInfos: ModelInfos,
    availableCapabilityIds: set[int],
) -> CapabilityInfos:
    """The climate entity, and everything it is wired to.

    The only capability that is not one reading : it gathers the setpoint, the
    bounds, the mode and the program from half a dozen other ids, and which of
    them exist depends on the product and on what the device reports.
    """
    # Default Ids
    capability.targetCapabilityId = 40
    capability.lowestValueCapabilityId = 160
    capability.highestValueCapabilityId = 161

    if (
        modelInfos.get("currentTemperatureAvailable", True)
        and 117 in availableCapabilityIds
    ):
        capability.currentValueCapabilityId = 117
        # The device says, at each poll, whether that reading means anything.
        # See docs/decisions.md.
        if 103150 in availableCapabilityIds:
            capability.currentAvailableCapabilityId = 103150

    # 181 carries the mode the device is really running, which is not always
    # the one it was asked for
    if 181 in availableCapabilityIds:
        capability.hvacActionCapabilityId = 181

    # While air circulation runs it drives the unit, and the Cozytouch app
    # locks the mode and setpoint for the duration
    if 102024 in availableCapabilityIds:
        capability.airCirculationCapabilityId = 102024

    # The service the whole system runs, which is what a mode change writes.
    # See docs/decisions.md.
    if 102020 in availableCapabilityIds:
        capability.systemServiceCapabilityId = 102020

    # TEMPERATURE_UPDATE_STEP: the device states the setpoint granularity
    if 294 in availableCapabilityIds:
        capability.stepCapabilityId = 294

    if modelInfos.type == CozytouchDeviceType.GAZ_BOILER:
        capability.name = "central_heating"
        capability.icon = "mdi:radiator"
        _wire_program(capability)
    elif modelInfos.type in ELECTRIC_HEATERS:
        capability.name = "heat"
        capability.icon = "mdi:heating-coil"
        # 153 is the element itself. 181 above only says which mode is
        # running, so a radiator sitting above its setpoint read as
        # heating -- see docs/decisions.md
        if 153 in availableCapabilityIds:
            capability.heatingActiveCapabilityId = 153
        _wire_program(capability)
    elif modelInfos.type == CozytouchDeviceType.ROOM:
        _room_entity(capability, modelInfos, availableCapabilityIds)
    elif modelInfos.type == CozytouchDeviceType.AC:
        capability.name = "air_conditioner"
        capability.icon = "mdi:air-conditioner"
        _wire_cooling(capability)
        _wire_presets(capability, modelInfos, availableCapabilityIds)
    elif modelInfos.type == CozytouchDeviceType.HEAT_PUMP:
        if capabilityId in (1, 7):
            capability.name = "heat_pump_z1"
            capability.targetCapabilityId = 17
            if (
                modelInfos.get("currentTemperatureAvailableZ1", True)
                and 117 in availableCapabilityIds
            ):
                capability.currentValueCapabilityId = 117
            else:
                capability.currentValueCapabilityId = None
        else:
            capability.name = "heat_pump_z2"
            capability.targetCapabilityId = 18
            if (
                modelInfos.get("currentTemperatureAvailableZ2", True)
                and 118 in availableCapabilityIds
            ):
                capability.currentValueCapabilityId = 118
            else:
                capability.currentValueCapabilityId = None

        del capability.lowestValueCapabilityId
        del capability.highestValueCapabilityId
        capability.icon = "mdi:heat-pump"
    else:
        capability.name = "heat"

    capability.type = CapabilityType.CLIMATE
    capability.category = CapabilityCategory.SENSOR

    if "fanModes" in modelInfos and 100801 in availableCapabilityIds:
        capability.fanModeCapabilityId = 100801

    if (
        modelInfos.get("quietModeAvailable", False)
        and 100802 in availableCapabilityIds
    ):
        capability.quietModeCapabilityId = 100802

    if modelInfos.get("overrideModeAvailable", True):
        _wire_program(capability)

    if "swingModes" in modelInfos and 100803 in availableCapabilityIds:
        capability.swingModeCapabilityId = 100803

        if 100804 in availableCapabilityIds:
            capability.swingOnCapabilityId = 100804

    return capability


def get_capability_infos(
    modelInfos: ModelInfos,
    capabilityId: int,
    capabilityValue: str,
    availableCapabilityIds: set[int],
) -> CapabilityInfos | None:
    """What this device turns this capability into.

    Three answers, in order : the climate entity for an id carrying an HVAC
    mode, nothing at all for an id deliberately dropped, and a row of
    `CAPABILITIES` for everything else. None means the mapping does not know
    the id, which is what the diagnostics dump reports so somebody can name
    it.

    availableCapabilityIds is what the device actually reports. Optional
    features are declared per model, but the same model id is reused across
    hardware that does not always implement them, so they are only wired up
    when the device backs them.
    """
    capability = CapabilityInfos(
        modelId=modelInfos.modelId, capabilityId=capabilityId
    )

    if capabilityId in (1, 2, 7, 8):
        # The four ids that can carry an HVAC mode. A product steers on one or
        # two of them and still reports the others; those get no entity, and
        # their row below exists so the reading beside the climate one reads as
        # a word rather than a number.
        if capabilityId not in modelInfos.HVACModesCapabilityId:
            return CapabilityInfos()

        capability = _climate_entity(
            capability, capabilityId, modelInfos, availableCapabilityIds
        )

    elif capabilityId in SUPPRESSED_CAPABILITIES:
        return CapabilityInfos()

    elif capabilityId in CAPABILITIES:
        capability = CAPABILITIES[capabilityId].resolve(
            capability, modelInfos, capabilityValue
        )
        if capabilityId == 100078 and modelInfos.get("winkable", False):
            # Writable only where the vendor's app offers the button, which
            # its device classes decide rather than the device. See
            # docs/decisions.md.
            capability.type = CapabilityType.SWITCH
        if hidden_by_a_calendar(capabilityId, availableCapabilityIds):
            capability.enabled_by_default = False

    else:
        return None

    return capability
