"""Coverage and wiring around the capability mapping.

Two failures worth guarding. A capability that arrives switched on floods the
device page for every user who owns the hardware, so the ones that describe the
API to itself have to stay off until someone asks for them. And a capability
whose name has no translation shows up as its raw key -- `available_system_modes`
in the UI -- which is the mistake anyone adding a capability makes once.

A third failure is the wiring itself. A platform picks its entities out of the
capability list by type, and a type on one side of that match and not the other
is silent both ways: a mapping nothing consumes produces no entity, and a
platform waiting for a type nothing produces sets up nothing at all. Two lived
here -- `time_adjustment` in time.py and `power` in sensor.py -- and the
categories have the same shape, since sensor.py reads two spellings and gives
anything else no category.

The checks walk every id the mapping answers for, so a capability added later is
covered without anyone remembering to cover it.
"""

import ast
import itertools
import json
import pathlib
import re

from _harness import TRANSLATIONS
import pytest

from custom_components.cozytouch import capability, capability_table
from custom_components.cozytouch.capability import get_capability_infos
from custom_components.cozytouch.capability_table import CAPABILITIES
from custom_components.cozytouch.model import CozytouchDeviceType, get_model_infos
from scripts.dump_capability_map import (
    EVERY_ID,
    platforms_consuming as types_the_platforms_consume,
)

# Names that are deliberately raw: a capability whose meaning nobody has worked
# out yet is surfaced under its own number rather than under an invented label.
# They read as placeholders in the UI, which is the point, so they have no
# translation to find.
PLACEHOLDER = re.compile(r"^(Capability_|Temp_|Target )")

# A capability-id superset, so the walk below can reach every mapping branch
# rather than only the ids a single device happens to report.
EVERY_ID = frozenset(EVERY_ID)


# One per device class, so a branch that only a boiler or only an air
# conditioner reaches is still walked.
MODEL_IDS = (56, 76, 211, 235, 418, 557, 1457, 1641, 1734)

# What sensor.py turns into an EntityCategory, plus the "sensor" that means no
# category at all. Anything else it silently drops on the floor.
CATEGORIES = frozenset({"sensor", "diag", "config"})


def capabilities_the_mapping_produces():
    """Every capability dict reachable from the mapping, across device classes."""
    for modelId in MODEL_IDS:
        infos = get_model_infos(modelId)
        if infos["type"] is CozytouchDeviceType.UNKNOWN:
            continue
        for capabilityId in EVERY_ID:
            result = get_capability_infos(infos, capabilityId, "0", EVERY_ID)
            if result:
                yield result


def names_the_mapping_produces():
    """Every entity name reachable from the capability mapping."""
    found = set()
    for result in capabilities_the_mapping_produces():
        if result.get("name"):
            found.add(result["name"])
            for entity in result.get("timestamps", ()):
                found.add(entity.name)
    return found


def types_the_mapping_produces():
    """Each type the mapping puts on a capability for a platform to match."""
    return {
        result["type"]
        for result in capabilities_the_mapping_produces()
        if "type" in result
    }


def translated_keys(path):
    with open(path, encoding="utf-8") as handle:
        entity = json.load(handle)["entity"]
    keys = set()
    for platform in entity.values():
        keys |= set(platform)
    return keys


@pytest.mark.parametrize("path", TRANSLATIONS)
def test_every_named_capability_has_a_translation(path):
    """Without one, Home Assistant shows the raw key to the user."""
    missing = {
        name
        for name in names_the_mapping_produces() - translated_keys(path)
        if not PLACEHOLDER.match(name)
    }

    assert not missing, f"{path} has no name for {sorted(missing)}"


@pytest.mark.parametrize("path", TRANSLATIONS)
def test_every_name_is_translated_under_its_own_platform(path):
    """Home Assistant looks a name up under the platform that registered the
    entity, so a key sitting in another section reads as its raw id. The flat
    check above cannot see that, and it is where `override_total_time_z1`
    landed the day capability 158 stopped being a number and became a select.
    """
    with open(path, encoding="utf-8") as handle:
        entity = json.load(handle)["entity"]

    consumed = types_the_platforms_consume()
    missing = []
    for result in capabilities_the_mapping_produces():
        name = result.get("name")
        if not name or PLACEHOLDER.match(name):
            continue

        # Which sections could carry it: every platform that matches on its
        # type, since one capability can reach two -- a climate entity and the
        # raw sensor beside it.
        sections = {
            platform.removesuffix(".py")
            for platform in consumed.get(result.get("type"), ())
        }
        if sections and not any(name in entity.get(s, {}) for s in sections):
            missing.append((name, sorted(sections)))

    assert not missing, f"{path} translates {missing} outside its own section"


@pytest.mark.parametrize("path", TRANSLATIONS[1:])
def test_the_translation_files_cover_the_same_keys(path):
    """A key added to one language and not the other is a silent gap."""
    reference = translated_keys(TRANSLATIONS[0])

    assert translated_keys(path) == reference


@pytest.mark.parametrize("path", TRANSLATIONS)
def test_every_switch_key_is_also_a_sensor_key(path):
    """sensor.py builds a read-only twin for every SWITCH capability, and the
    twin is registered by the sensor platform, so Home Assistant looks its
    name up in the sensor section. A key living only under switch therefore
    translates the control and shows the raw key on the twin -- which the
    flat check above cannot see, and where air_circulation and
    domestic_hot_water_boost both lived.
    """
    with open(path, encoding="utf-8") as handle:
        entity = json.load(handle)["entity"]

    missing = set(entity["switch"]) - set(entity["sensor"])

    assert not missing, f"{path} sensor section has no name for {sorted(missing)}"


@pytest.mark.parametrize(
    "capabilityId",
    sorted(
        capabilityId
        for capabilityId, row in CAPABILITIES.items()
        if not row.enabled_by_default
    ),
)
def test_a_row_that_says_off_arrives_off(capabilityId):
    """A device reports dozens of descriptors; on by default they bury the rest."""
    infos = get_model_infos(557)

    result = get_capability_infos(infos, capabilityId, "0", {capabilityId})

    if not result:
        # The row exists but this product has no such entity -- absent_on or a
        # model flag. Nothing to be switched off.
        return

    assert result["enabled_by_default"] is False


@pytest.mark.parametrize(
    ("capabilityId", "expected"),
    [
        # Minutes, which the time sensor renders as 1d 00:00 rather than 1440.
        (331, "time"),
        (307, "time"),
        # A setpoint in degrees, beside the ones the climate entity already
        # reads as temperatures.
        (352, "temperature"),
        (103199, "temperature"),
        # A flag the corpus reads as 0 on every capture, so only the app says
        # it has a high state at all.
        (104051, "binary"),
        # 557 is a room, and a room only reads this one. Which products get
        # it as a control is test_identify_request.py.
        (100078, "binary"),
        # Still a raw string: the app reads these through a mask or a parser
        # nothing here mirrors.
        (224, "string"),
        (105122, "string"),
        (100300, "string"),
    ],
)
def test_a_descriptor_is_read_as_what_the_app_reads_it_as(capabilityId, expected):
    infos = get_model_infos(557)

    result = get_capability_infos(infos, capabilityId, "0", {capabilityId})

    assert result["type"] == expected


def test_a_capability_that_says_nothing_is_enabled():
    """The flag is opt-in: only a capability that asks for it arrives off."""
    infos = get_model_infos(557)

    result = get_capability_infos(infos, 303, "0", {303})

    assert "enabled_by_default" not in result


def test_no_row_decodes_its_value_two_ways():
    """Bits and values read the same number two incompatible ways.

    A sum of powers of two, or one thing named: nothing in the value says
    which, only the row does, and 4 is a legal answer to either. A row setting
    both would be read by whichever describe_capability_value tries first and
    would silently mean something else -- 217 read as a mode numbered 3083
    rather than as a mask is that mistake, already made once.
    """
    both = sorted(
        capabilityId
        for capabilityId, row in CAPABILITIES.items()
        if row.bits is not None and row.reads_as is not None
    )

    assert not both, f"{both} set both bits and reads_as"


def test_no_capability_id_is_written_twice():
    """Two rows for one id is the later one, silently: a dict literal says nothing.

    Reading CAPABILITIES back cannot see it -- the duplicate is already gone --
    so this counts the keys in the source instead. Two hundred rows in numeric
    order is exactly where a paste lands on a neighbour.
    """
    source = pathlib.Path(capability_table.__file__).read_text()
    table = next(
        node
        for node in ast.walk(ast.parse(source))
        if isinstance(node, ast.AnnAssign)
        and getattr(node.target, "id", None) == "CAPABILITIES"
    )
    keys = [key.value for key in table.value.keys if isinstance(key, ast.Constant)]

    assert len(keys) == len(set(keys)), (
        f"written twice: {sorted({key for key in keys if keys.count(key) > 1})}"
    )


def test_every_row_resolves_under_its_own_name():
    """What the table says an id is, is what the mapping answers for it."""
    infos = get_model_infos(557)

    for capabilityId, row in CAPABILITIES.items():
        result = get_capability_infos(infos, capabilityId, "0", {capabilityId})
        if not result:
            continue

        # A per_type row answers one of several names, which is the whole point
        # of the field; any of them is the row answering for itself.
        names = {row.name} | {
            str(override["name"])
            for override in (row.per_type or {}).values()
            if "name" in override
        }
        # The climate ids are named by `capability.py` from the device type,
        # not by the row : a room, an electric heater and an air conditioner
        # each get their own word for the same capability.
        if capabilityId in (1, 2, 7, 8):
            names |= {"room", "heat", "air_conditioner", "heat_pump_z1"}
        assert result["name"] in names, (
            f"{capabilityId} resolves to {result['name']!r}, not one of {sorted(names)}"
        )


@pytest.mark.parametrize("capabilityId", [162, 163])
def test_the_cooling_bounds_are_temperatures(capabilityId):
    infos = get_model_infos(557)

    result = get_capability_infos(infos, capabilityId, "18.0", {capabilityId})

    assert result["type"] == "temperature"
    assert result["enabled_by_default"] is False


def test_the_walk_finds_the_platforms_and_the_types_they_match_on():
    """A sanity floor: the dump's regex found the dispatch, not an empty file."""
    consumed = types_the_platforms_consume()

    assert consumed["climate"] == {"climate.py", "sensor.py"}
    assert len(consumed) > 15


def test_every_type_the_mapping_produces_reaches_a_platform():
    """A type nothing consumes is a capability mapped into no entity at all."""
    assert not types_the_mapping_produces() - set(types_the_platforms_consume())


def test_no_platform_waits_for_a_type_nothing_produces():
    """The other direction: a platform that sets up nothing, and says nothing.

    time.py was written around a `time_adjustment` the mapping never produced,
    so the time platform created no entity on any device and the durations
    stayed read-only. sensor.py held a `power` branch the same way, and that one
    would have raised on the first device to reach it: it passed a keyword
    CozytouchUnitSensor does not take.
    """
    assert not set(types_the_platforms_consume()) - types_the_mapping_produces()


def test_every_category_the_mapping_produces_is_one_the_entities_read():
    """sensor.py tests for "diag"; "diagnostic" reads as no category at all."""
    produced = {
        result["category"]
        for result in capabilities_the_mapping_produces()
        if "category" in result
    }

    assert not produced - CATEGORIES


def test_the_table_reads_in_ascending_id_order():
    """Ids were landing wherever the commit that added them happened to touch,
    so somebody looking one up had to grep rather than scroll. A new row goes
    where its number goes.
    """
    ids = list(capability_table.CAPABILITIES)

    assert ids == sorted(ids), (
        "capability_table.py rows out of order at "
        f"{[pair for pair in itertools.pairwise(ids) if pair[1] < pair[0]]}"
    )


def test_every_id_the_chain_wires_has_a_row():
    """A capability `capability.py` reads still needs a row of its own.

    The chain wires an id onto the climate entity -- a fan speed, a louver
    position, a zone's setpoint -- and the table is asked about that id
    separately, for the reading that sits beside the entity. With no row,
    `get_capability_infos` answers None, and a capability the integration
    understands well enough to steer on is filed as one nobody has ever named:
    it lands in a diagnostics dump's unmapped list and raises the notice that
    asks its owner to report it.
    """
    source = pathlib.Path(capability.__file__).read_text()
    wired = {
        int(capabilityId)
        for capabilityId in re.findall(r"\b(\d{2,6}) in availableCapabilityIds", source)
    } | {
        int(capabilityId)
        for capabilityId in re.findall(r"CapabilityId = (\d{2,6})", source)
    }

    assert wired, "the scrape found nothing, so it is measuring nothing"
    assert not wired - set(capability_table.CAPABILITIES)
