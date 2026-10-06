"""The vendor's own words for a fault the device is reporting.

A fault-code capability carries a matrix of codes and nothing else. The text
lives on Atlantic's side, keyed on the model, and is fetched rather than
shipped. See docs/decisions.md.
"""

from __future__ import annotations

import json

from .capability_table import CAPABILITIES
from .infos import CapabilityType

# What a healthy fault code reads as, and the value an empty slot carries.
# See docs/decisions.md.
HEALTHY = "OK"
EMPTY_SLOT = 255

# The four fields a row starts with, which are what the vendor's table is
# keyed on. A fifth, where a firmware reports one, rides along in the code but
# takes no part in the lookup.
CODE_FIELDS = 4

FAULT_CAPABILITIES: frozenset[int] = frozenset(
    capabilityId
    for capabilityId, entity in CAPABILITIES.items()
    if entity.type is CapabilityType.ERROR_CODE
)


def active_rows(raw: str | None) -> list[list[int]] | None:
    """The rows of a fault matrix that are faults, or None if it does not parse.

    A row is a fault only when it is neither all-zero nor carrying the
    empty-slot sentinel. Duplicates are dropped: the same fault repeated
    across slots is one fault.
    """
    if raw is None:
        return None

    try:
        matrix = json.loads(raw)
        rows = [[int(field) for field in row] for row in matrix]
    except (ValueError, TypeError):
        return None

    active: list[list[int]] = []
    for row in rows:
        if not any(row) or EMPTY_SLOT in row:
            continue
        if row not in active:
            active.append(row)

    return active


def code_of(row: list[int]) -> str:
    """A row as the code it is written as, fields joined by underscores."""
    return "_".join(str(field) for field in row)


def packed(row: list[int]) -> int | None:
    """A row as the single integer the vendor's table is keyed on.

    `[40, 13, 0, 3]` is the code an interface displays as `40.13.0.3`, and the
    table carries it as `671940611` -- the four fields packed one per byte.
    Established against three codes on two models ; see docs/decisions.md.
    """
    fields = row[:CODE_FIELDS]
    if len(fields) < CODE_FIELDS or any(
        not 0 <= field <= 255 for field in fields
    ):
        return None

    value = 0
    for field in fields:
        value = (value << 8) | field

    return value


def describe(table: list[dict], row: list[int]) -> dict[str, str] | None:
    """What the vendor's table says about one active row, if it says anything.

    Matched on the parent code alone : a table entry that also names a child
    code describes a sub-fault of the same parent, and picking the parent-only
    entry when one exists keeps the general answer over an arbitrary specific
    one.
    """
    key = packed(row)
    if key is None:
        return None

    entries = [
        entry for entry in table if entry.get("parentProductErrorCode") == key
    ]
    if not entries:
        return None

    entry = next(
        (item for item in entries if item.get("childProductErrorCode") is None),
        entries[0],
    )

    described = {
        "code": code_of(row),
        "label": (entry.get("parentErrorLabel") or "").strip(),
        "cause": (entry.get("probableCauseErrorLabel") or "").strip(),
        "repair": (entry.get("repairInstructionsLabel") or "").strip(),
    }
    child = (entry.get("childErrorLabel") or "").strip()
    if child:
        described["label"] = f"{described['label']} / {child}".strip(" /")

    return described
