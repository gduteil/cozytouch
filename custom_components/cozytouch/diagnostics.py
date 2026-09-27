"""Diagnostics for the Atlantic Cozytouch integration.

What the API says about the account, one click away, with the account details
taken out. See docs/decisions.md.
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .hub import CozytouchConfigEntry

# The catalogue's own encoding of what a value is. Numbers in the payload,
# words in the dump, because a dump is read by a person.
CAPABILITY_TYPES = {
    1: "int",
    2: "float",
    3: "string",
    4: "bool",
    5: "enum",
    6: "other",
    7: "struct",
}

# Credentials, and everything that would place the account at an address.
TO_REDACT = {
    "username",
    "password",
    "address",
    "formattedAddress",
    "latitude",
    "longitude",
    "locality",
    "postalCode",
    "gatewaySerialNumber",
    "serialNumber",
    # On a consumption series ; a device URL names the gateway's serial.
    "deviceUrl",
}


def describe(row: dict) -> dict:
    """One catalogue row, cut down to what a reader of a dump needs.

    Atlantic's `name` is an internal identifier and its `description` is a
    line of prose; both are here, because the identifier is what a report can
    be searched for and the prose is what says what the thing is. The rest is
    only carried where the catalogue states it.
    """
    described: dict[str, Any] = {
        "name": row.get("name"),
        "description": row.get("description"),
        "type": CAPABILITY_TYPES.get(row.get("type"), row.get("type")),
        # Bit 4 of accessType. Whether a value can be written is the first
        # question asked about an unmapped id, and guessing it wrong is how a
        # control that writes into the void gets shipped.
        "writable": bool((row.get("accessType") or 0) & 4),
    }

    for field in ("unit", "min", "max", "resolution"):
        if row.get(field) is not None:
            described[field] = row[field]

    enum = row.get("enum") or {}
    if enum.get("values"):
        # A bitmask is declared as an enum whose keys are the bit values, so
        # this is both tables at once and the id says which it is.
        described["values"] = {
            str(member["Key"]): member["Value"] for member in enum["values"]
        }

    return described


def _with_what_atlantic_says(dump: dict, catalogue: dict[int, dict]) -> dict:
    """Add the vendor's answer for every id this account's devices report.

    Every id they report, and not only the unmapped ones: an id named
    *wrongly* makes an entity that looks perfectly fine and reads the wrong
    thing, and nothing makes that visible unless the vendor's type, unit and
    enum sit beside ours to be compared against.

    And only the ids they report. The catalogue covers Atlantic's whole range,
    405 capabilities across boilers, heat pumps, ventilation and tanks; on the
    account this was measured with, 91 of them are reported and the other 314
    describe hardware nobody there owns. Carrying all of them would put the
    same two hundred kilobytes in every report on earth. Once, for the account,
    rather than under each device, since two rooms of one installation report
    the same ids. See docs/decisions.md.
    """
    if not catalogue:
        return dump

    reported = {
        capabilityId
        for device in dump.get("devices", [])
        for capabilityId in (device.get("capabilities") or {}).get("values", {})
    }

    return dump | {
        # An id the catalogue does not carry gets no entry, which is a reading
        # too: three ids this integration ships are absent from it.
        "atlanticSays": {
            capabilityId: describe(catalogue[capabilityId])
            for capabilityId in sorted(reported)
            if capabilityId in catalogue
        }
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: CozytouchConfigEntry
) -> dict[str, Any]:
    """Return what the API reports for this account, minus the account itself.

    One dump per account, covering every device the setup view returned.
    """
    runtime = entry.runtime_data

    # One request per dump, never on the poll, and an empty answer is not an
    # error: the dump is still the dump. See docs/decisions.md.
    catalogue = await runtime.account.fetch_capability_catalogue()

    # Any hub describes the whole account : what the dump flags as set up
    # here comes from the entry's subentries, not from the hub's own device.
    hub = next(iter(runtime.hubs.values()), None)

    return async_redact_data(
        {
            "entry": {
                "options": dict(entry.options),
                # data carries the credentials; only the non-secret keys are useful.
                "data": {
                    key: value
                    for key, value in entry.data.items()
                    if key not in ("username", "password")
                },
                "devices": {
                    subentry_id: subentry.data.get("deviceId")
                    for subentry_id, subentry in entry.subentries.items()
                },
            },
            "online": runtime.account.online,
            # As the endpoint answered, so a report shows what a meter sends
            # -- or that this setup has none. See docs/decisions.md.
            "consumptions": {
                # What 164 says ; False means the endpoint was never asked.
                "declared": runtime.account.consumption_declared(),
                "status": runtime.account.consumptions_status,
                "answer": runtime.account.consumptions,
            },
            **_with_what_atlantic_says(
                hub.get_diagnostics() if hub is not None else {}, catalogue
            ),
        },
        TO_REDACT,
    )
