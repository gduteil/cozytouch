"""Repair issues the integration raises about itself.

A model the table does not know is asked about at the one moment it is obvious
the mapping is missing, with the report already written. See docs/decisions.md.
"""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

ISSUE_TRACKER = "https://github.com/mathieuletyrant/cozytouch-hacs/issues"

# The device report form, opened rather than the bare issue list. Somebody
# arriving from a notice has not decided to write a report yet -- they were
# told by Home Assistant -- and the form is what says which three things the
# answer needs. See docs/decisions.md.
DEVICE_REPORT = ISSUE_TRACKER + "/new?template=device_report.yml"


# One issue per device and code, so two faults on one boiler read as two and
# a cleared one goes away on its own. See docs/decisions.md.
FAULT_ISSUE = "fault_{subentry_id}_{code}"

# One issue for the whole account, not one per device and not one per id: the
# answer to all of them is the same single file. See docs/decisions.md.
UNNAMED_ISSUE = "unnamed_capabilities"



def async_check_faults(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Raise, or clear, an issue per fault the account's devices report.

    Not fixable : nothing Home Assistant does settles a hydraulic pressure
    fault. The issue is there to say, in the vendor's words, what the device
    is complaining about. See docs/decisions.md.
    """
    raised: set[str] = set()

    unnamed: set[int] = set()
    devices = 0
    for hub in entry.runtime_data.hubs.values():
        # The suppressed ones are somebody's decision, not a gap, so they are
        # not what this asks about. See docs/decisions.md.
        _, _, ids = hub.get_capability_names()
        if ids:
            devices += 1
            unnamed.update(ids)

    if unnamed:
        raised.add(UNNAMED_ISSUE)
        ir.async_create_issue(
            hass,
            DOMAIN,
            UNNAMED_ISSUE,
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            learn_more_url=DEVICE_REPORT,
            translation_key="unnamed_capabilities",
            translation_placeholders={
                "count": str(len(unnamed)),
                "devices": str(devices),
                "ids": ", ".join(str(capabilityId) for capabilityId in sorted(unnamed)),
            },
        )

    for subentry_id, hub in entry.runtime_data.hubs.items():
        subentry = entry.subentries.get(subentry_id)
        for described in hub.get_faults().values():
            for fault in described:
                issue_id = FAULT_ISSUE.format(
                    subentry_id=subentry_id, code=fault["code"]
                )
                raised.add(issue_id)
                ir.async_create_issue(
                    hass,
                    DOMAIN,
                    issue_id,
                    is_fixable=False,
                    severity=ir.IssueSeverity.ERROR,
                    translation_key="device_fault",
                    translation_placeholders={
                        "device_name": subentry.title if subentry else "",
                        "code": fault["code"],
                        "label": fault["label"],
                        # Kept on one line: a repair card renders markdown, and
                        # the vendor's newlines turn into one run-on paragraph
                        # either way.
                        "repair": fault["repair"] or "-",
                    },
                )

    # A fault that cleared, or a device that left, takes its issue with it.
    # The sweep covers every issue this integration has open, not only the
    # faults, so the unknown-model repairs an older version raised go with
    # them rather than sitting there forever.
    for issue_id in _open_issues(hass) - raised:
        ir.async_delete_issue(hass, DOMAIN, issue_id)


def _open_issues(hass: HomeAssistant) -> set[str]:
    """The issues this sweep is allowed to clear.

    `unnamed_capabilities` clears itself the moment the mapping names the last
    of them, which is the whole point of raising it.

    `unknown_model_` is there for the repairs an older version raised, which
    nothing creates any more : a device is typed from what it reports now, so
    the dialog that asked someone to find a model id has no question left to
    ask. Without this they would sit in Repairs forever. Anything else this
    integration opens is left alone. See docs/decisions.md.
    """
    registry = ir.async_get(hass)
    return {
        issue_id
        for (domain, issue_id) in registry.issues
        if domain == DOMAIN
        and issue_id.startswith(("fault_", "unknown_model_", UNNAMED_ISSUE))
    }
