r"""Print what the capability mapping resolves to, per device type.

capability.py is a 900-line if/elif chain: reading it end to end is the only
way to answer "what does id 172 become, and on which products?", and that
question comes up on every report. This walks the chain instead -- every id,
against one model of each device type -- and prints what it answers.

Most ids answer the same thing whatever the device, so the output splits in
two: a flat table for those, and a second one for the handful that branch on
the device type or the model id. The split is computed, not curated, so an id
that gains a branch moves between the tables on its own.

Nothing is checked in: the output is read when the question comes up, so
there is no copy of the mapping to keep in step with the mapping. Home
Assistant is imported, so run it in the test venv (see CLAUDE.md):

    python3 scripts/dump_capability_map.py
    python3 scripts/dump_capability_map.py | grep -A4 '^### 172'
"""

import pathlib
import re
import signal
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from custom_components.cozytouch.capability import get_capability_infos
from custom_components.cozytouch.capability_table import CAPABILITIES
from custom_components.cozytouch.infos import CapabilityCategory, CapabilityType
from custom_components.cozytouch.model import CozytouchDeviceType, get_model_infos

ROOT = pathlib.Path(__file__).resolve().parent.parent

# One model per device type, so a branch that keys off the type is reached.
# The ids are picked from the table; a type gaining its first model would need
# adding here, which is the same edit as adding it to the table.
PROBES = {
    CozytouchDeviceType.GAZ_BOILER: 56,
    CozytouchDeviceType.HEAT_PUMP: 211,
    CozytouchDeviceType.THERMOSTAT: 418,
    CozytouchDeviceType.WATER_HEATER: 1641,
    CozytouchDeviceType.TOWEL_RACK: 1381,
    CozytouchDeviceType.AC: 557,
    CozytouchDeviceType.AC_CONTROLLER: 562,
    CozytouchDeviceType.HUB: 1457,
    # A zone reports almost nothing, which is the point of probing it: what a
    # THZONE resolves to should stay a short list. Keyed on the device name
    # rather than the id, so the probe carries one -- see ZONE_PROBE_NAME.
    CozytouchDeviceType.ZONE: 1505,
    CozytouchDeviceType.UNKNOWN: 999999,
}

# Model ids whose branch differs from the type's probe. 76 is the heat pump
# that still reads its mode off 7/8 where 211 moved to 1/2, so probing only 211
# would report 7 as unmapped for every heat pump. 1734 is an air conditioner
# without the eco gate, and 2374 rebinds the setpoint bounds.
EXTRA_MODELS = (76, 1734, 2374)

# Every id the walk offers the mapping. The two ranges are where the vendor
# puts them: a low block below 400 and a high block from 100000.
EVERY_ID = sorted(set(range(1, 400)) | set(range(100000, 106000)))

# The platforms that pick their entities out of the capability list by type.
# binary_sensor.py is not one of them: it owns the single cloud-connectivity
# entity and never looks at a capability.
PLATFORM_FILES = (
    "climate.py",
    "datetime.py",
    "fan.py",
    "number.py",
    "select.py",
    "sensor.py",
    "switch.py",
)

# A key of a platform's builder table -- `CapabilityType.X: SomeEntity` -- which
# is how a platform states which type it was written for. The member is
# resolved to its value, so a name the enum does not declare fails here rather
# than matching nothing at runtime.
TYPE_TEST = re.compile(r"CapabilityType\.(\w+):")


def platforms_consuming():
    """Each type a platform matches on, and which platform files match on it.

    Read off the source rather than kept by hand, so it cannot drift from the
    platforms. One type can reach several, which is why a switch capability
    also shows up as a sensor.
    """
    consumed: dict[str, set[str]] = {}
    for platform in PLATFORM_FILES:
        source = (ROOT / "custom_components" / "cozytouch" / platform).read_text(
            encoding="utf-8"
        )
        for member in TYPE_TEST.findall(source):
            consumed.setdefault(CapabilityType[member].value, set()).add(platform)
    return consumed


# A couple of ids answer on their own value -- 119 rejects the sentinel the
# device sends for "no outside probe" -- so feed a plausible one.
VALUES = {119: "12.0", 172: "20.0"}

DECLINED = "declined"


# A zone is the one device the table recognises by name instead of by id, so a
# probe of it has to hand one over or it resolves as an unknown product.
ZONE_PROBE_NAME = "THZONE_0"
ZONE_PROBE_MODEL = PROBES[CozytouchDeviceType.ZONE]


def probe(modelId, capabilityId):
    """What the mapping answers for one id on one model."""
    deviceName = ZONE_PROBE_NAME if modelId == ZONE_PROBE_MODEL else None
    result = get_capability_infos(
        get_model_infos(modelId, None, deviceName),
        capabilityId,
        VALUES.get(capabilityId, "0"),
        set(EVERY_ID),
    )
    if result is None:
        # Nothing in the chain claims this id, on any device.
        return None
    if not result:
        # {} is the chain claiming the id and refusing it for this device.
        return DECLINED
    return result


def signature(result):
    """The part of an answer this reference reports, as a comparable tuple."""
    if result in (None, DECLINED):
        return result
    names = tuple(
        name
        for name in (
            result.get("name"),
            *(entity.name for entity in result.get("timestamps", ())),
        )
        if name
    )
    return (
        names,
        result.get("type"),
        result.get("category"),
        result.get("enabled_by_default", True),
    )


def cell(sig):
    """One answer, rendered."""
    if sig is None:
        return "—"
    if sig == DECLINED:
        return "declined"
    names, kind, category, enabled = sig
    text = f"`{' / '.join(names)}` · {kind}"
    if category in ("diag", "diagnostic"):
        text += " · diag"
    if not enabled:
        text += " · off"
    return text


def main():
    types = list(PROBES)
    models = list(PROBES.values()) + list(EXTRA_MODELS)
    labels = [str(t) for t in types] + [f"model {m}" for m in EXTRA_MODELS]

    uniform, branching = [], []
    for capabilityId in EVERY_ID:
        sigs = [signature(probe(m, capabilityId)) for m in models]
        if all(s is None for s in sigs):
            continue
        if len(set(map(repr, sigs))) == 1:
            uniform.append((capabilityId, sigs[0]))
        else:
            branching.append((capabilityId, sigs))

    total = len(uniform) + len(branching)
    platforms = {
        kind: " + ".join(sorted(name.removesuffix(".py") for name in files))
        for kind, files in platforms_consuming().items()
    }

    print("# Capability reference")
    print()
    print(
        "Every capability id `capability.py` answers for, and what it becomes,\n"
        "read out of the mapping this run. Nothing is stored: what follows is\n"
        "true of the working tree it was run against, and of nothing else."
    )
    print()
    print(
        "An entry reads `name · type · diag · off`: the entity name, which is\n"
        "also its translation key; the mapping type, which decides the platform\n"
        "that builds the entity; whether it lands in the diagnostic category;\n"
        "and whether it arrives switched off in the entity registry."
    )
    print()
    print(
        f"{total} ids in total. Names and types here are what the mapping\n"
        "claims, not what has been verified against hardware -- most of the\n"
        "table came from one user's capture of one device."
    )
    print()
    print(f"## The {len(uniform)} ids that answer the same on every device")
    print()
    print(
        "The mapping ignores the model for these: whatever reports the id gets\n"
        "the same entity."
    )
    print()
    print("| id | entity | platform |")
    print("| ---: | --- | --- |")
    for capabilityId, sig in uniform:
        print(f"| {capabilityId} | {cell(sig)} | {platforms.get(sig[1], '?')} |")

    print()
    print(f"## The {len(branching)} ids that depend on the device")
    print()
    print(
        "`—` means nothing maps the id for that device; `declined` means the\n"
        "mapping claims the id and refuses it there on purpose, which is how a\n"
        "model flag removes an entity."
    )
    print()
    for capabilityId, sigs in branching:
        print(f"### {capabilityId}")
        print()
        print("| device | entity |")
        print("| --- | --- |")
        grouped = {}
        for label, sig in zip(labels, sigs, strict=True):
            grouped.setdefault(repr(sig), (sig, []))[1].append(label)
        for sig, owners in grouped.values():
            print(f"| {', '.join(owners)} | {cell(sig)} |")
        print()

    descriptors = {
        capabilityId: row.name
        for capabilityId, row in CAPABILITIES.items()
        if not row.enabled_by_default and row.category is CapabilityCategory.DIAG
    }
    print(f"## The {len(descriptors)} ids that arrive switched off")
    print()
    print(
        "Named from the vendor's own capability list, which gives an identifier\n"
        "and nothing else -- no unit, no encoding, no way to read a bitmask. They\n"
        "are surfaced as raw strings and arrive switched off, so they cost\n"
        "nothing until someone turns one on to investigate it. They appear in the\n"
        "tables above like any other id."
    )
    print()
    print("| id | name |")
    print("| ---: | --- |")
    for capabilityId, name in sorted(descriptors.items()):
        print(f"| {capabilityId} | `{name}` |")


if __name__ == "__main__":
    # The output is long and meant to be piped into grep, head or less. Python
    # turns a closed pipe into a traceback on the way out, which buries the
    # answer the reader was looking for.
    if hasattr(signal, "SIGPIPE"):
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)

    main()
