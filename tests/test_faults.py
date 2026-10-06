"""The fault a device reports, in the vendor's own words.

A fault-code capability carries a matrix and nothing else, so until now a
faulted boiler read `40_13_0_3` and the person reading it had to own the
manual. Atlantic's own table is fetched instead of shipped, which is what
keeps their strings out of this repository.

The load-bearing case is the packing: a matrix row is the four bytes of the
`parentProductErrorCode` the table is keyed on, and the three codes pinned
below are the ones the live API returned (research, September 2026). If that
arithmetic is wrong every lookup silently misses and the sensor quietly goes
back to showing a bare code.

The rest is about what a healthy account costs -- no request at all -- and
about a fault that clears taking its repair notice with it.
"""

import asyncio
from types import SimpleNamespace

import pytest

from custom_components.cozytouch import faults, repairs
from custom_components.cozytouch.hub import Hub

# Three rows from model 56's table, as the vendor returns them: the dotted
# code an interface displays, and the packed integer beside it.
PACKED_CODES = (
    ([40, 13, 0, 3], 671940611),
    ([40, 1, 0, 3], 671154179),
    ([10, 15, 0, 3], 168755203),
)

# One entry per shape the table has: a parent on its own, and a parent whose
# fault is refined by a child.
TABLE = [
    {
        "parentProductErrorCode": 671940611,
        "childProductErrorCode": None,
        "parentErrorLabel": "Perte de la communication radio",
        "childErrorLabel": "",
        "probableCauseErrorLabel": "",
        "repairInstructionsLabel": "- Rapprocher le thermostat",
    },
    {
        "parentProductErrorCode": 168755203,
        "childProductErrorCode": 13,
        "parentErrorLabel": "Erreur unité extérieure",
        "childErrorLabel": "84 : Erreur capteur de courant",
        "probableCauseErrorLabel": "Capteur débranché",
        "repairInstructionsLabel": "",
    },
]

HEALTHY = "[[0,0,0,0],[0,255,0,4]]"
FAULTED = "[[40,13,0,3],[0,0,0,0]]"


@pytest.mark.parametrize(("row", "expected"), PACKED_CODES)
def test_a_matrix_row_packs_to_the_code_the_table_is_keyed_on(row, expected):
    assert faults.packed(row) == expected


def test_a_fifth_field_takes_no_part_in_the_lookup():
    """Some firmwares report five columns; the key is the first four."""
    assert faults.packed([40, 13, 0, 3, 7]) == faults.packed([40, 13, 0, 3])


def test_a_row_that_cannot_be_a_code_is_not_guessed_at():
    """Too short, or a field past a byte: no key rather than a wrong one."""
    assert faults.packed([40, 13, 0]) is None
    assert faults.packed([40, 13, 0, 300]) is None


def test_the_active_rows_are_the_faults_and_nothing_else():
    assert faults.active_rows(HEALTHY) == []
    assert faults.active_rows("[[40,13,0,3],[40,13,0,3]]") == [[40, 13, 0, 3]]
    assert faults.active_rows("not json") is None


def test_the_vendor_names_the_fault_and_says_what_to_do():
    described = faults.describe(TABLE, [40, 13, 0, 3])

    assert described == {
        "code": "40_13_0_3",
        "label": "Perte de la communication radio",
        "cause": "",
        "repair": "- Rapprocher le thermostat",
    }


def test_a_child_row_refines_the_parent_it_hangs_off():
    described = faults.describe(TABLE, [10, 15, 0, 3])

    assert described is not None
    assert described["label"] == (
        "Erreur unité extérieure / 84 : Erreur capteur de courant"
    )
    assert described["cause"] == "Capteur débranché"


def test_a_code_the_table_does_not_carry_is_not_invented():
    assert faults.describe(TABLE, [99, 99, 0, 1]) is None


def test_every_fault_capability_is_one_the_mapping_actually_produces():
    """The set is derived from the table rather than restated here, so an
    ERROR_CODE row added later is covered without anyone editing this.
    """
    assert {150, 290, 303} <= faults.FAULT_CAPABILITIES


def fake_hub(value, table=TABLE, modelId=56):
    """A hub stand-in with one fault capability and a table behind it."""
    asked = []

    async def fetch_fault_table(model):
        asked.append(model)
        return table

    hub = SimpleNamespace(
        _faults={},
        _account=SimpleNamespace(fetch_fault_table=fetch_fault_table),
        get_capability_value=lambda capabilityId, default=None: (
            value if capabilityId == 303 else None
        ),
        get_model_id=lambda: modelId,
        asked=asked,
    )

    asyncio.run(Hub._refresh_faults(hub))
    return hub


def test_a_healthy_device_spends_no_request():
    """The table is read when a code is active, never on a beat: a healthy
    account polls every 30s and must not ask Atlantic anything extra.
    """
    hub = fake_hub(HEALTHY)

    assert hub.asked == []
    assert hub._faults == {}


def test_a_faulted_device_reads_its_model_s_table_once():
    hub = fake_hub(FAULTED)

    assert hub.asked == [56]
    assert hub._faults[303][0]["label"] == "Perte de la communication radio"


def test_a_device_whose_model_is_unknown_still_reports_the_code():
    """No model id means no table, which is not a reason to raise."""
    hub = fake_hub(FAULTED, modelId=None)

    assert hub.asked == []
    assert hub._faults == {}


class FakeRegistry:
    """The issue registry, as much of it as the fault notice touches."""

    def __init__(self, open_issues=()):
        self.created = []
        self.deleted = []
        self.issues = {("cozytouch", issue): None for issue in open_issues}
        self.IssueSeverity = SimpleNamespace(ERROR="error", WARNING="warning")

    def async_get(self, hass):
        return self

    def async_create_issue(self, hass, domain, issue_id, **kwargs):
        self.created.append((issue_id, kwargs))

    def async_delete_issue(self, hass, domain, issue_id):
        self.deleted.append(issue_id)


def entry_reporting(described, unnamed=()):
    """An account entry whose one device reports the given faults."""
    return SimpleNamespace(
        subentries={"sub-1": SimpleNamespace(title="Chaudière")},
        runtime_data=SimpleNamespace(
            hubs={
                "sub-1": SimpleNamespace(
                    get_faults=lambda: described,
                    get_capability_names=lambda: ({}, [], list(unnamed)),
                )
            }
        ),
    )


def check_faults(monkeypatch, described, open_issues=(), unnamed=()):
    registry = FakeRegistry(open_issues)
    monkeypatch.setattr(repairs, "ir", registry)
    repairs.async_check_faults(None, entry_reporting(described, unnamed))
    return registry


def test_an_id_nothing_names_asks_for_a_diagnostics_file(monkeypatch):
    """One notice for the account, not one per device and not one per id:
    the answer to all of them is the same single file.
    """
    registry = check_faults(monkeypatch, {}, unnamed=(305, 104047, 305))

    issue_id, kwargs = registry.created[0]
    assert issue_id == "unnamed_capabilities"
    assert kwargs["is_fixable"] is False
    assert kwargs["translation_placeholders"]["count"] == "2"
    assert kwargs["translation_placeholders"]["devices"] == "1"
    assert kwargs["translation_placeholders"]["ids"] == "305, 104047"


def test_a_device_whose_ids_are_all_named_raises_nothing(monkeypatch):
    registry = check_faults(monkeypatch, {})

    assert registry.created == []


def test_the_notice_goes_when_the_mapping_catches_up(monkeypatch):
    """It clears itself, which is the point of raising it at all."""
    registry = check_faults(
        monkeypatch, {}, open_issues=("unnamed_capabilities",)
    )

    assert registry.deleted == ["unnamed_capabilities"]


def test_a_fault_raises_a_notice_nobody_is_asked_to_fix(monkeypatch):
    """Not fixable on purpose: no dialog settles a hydraulic pressure fault.
    The notice is there to say what the device is complaining about.
    """
    registry = check_faults(
        monkeypatch,
        {303: [faults.describe(TABLE, [40, 13, 0, 3])]},
    )

    issue_id, kwargs = registry.created[0]
    assert issue_id == "fault_sub-1_40_13_0_3"
    assert kwargs["is_fixable"] is False
    assert kwargs["translation_placeholders"]["device_name"] == "Chaudière"
    assert (
        kwargs["translation_placeholders"]["label"]
        == "Perte de la communication radio"
    )


def test_a_fault_that_cleared_takes_its_notice_with_it(monkeypatch):
    registry = check_faults(
        monkeypatch, {}, open_issues=("fault_sub-1_40_13_0_3",)
    )

    assert registry.created == []
    assert registry.deleted == ["fault_sub-1_40_13_0_3"]


def test_the_sweep_clears_the_repair_that_no_longer_exists(monkeypatch):
    """`unknown_model_` notices were raised by an older version and nothing
    creates them now : a device is typed from what it reports, so the dialog
    that asked someone to find a model id has no question left. Without this
    they would sit in Repairs forever.
    """
    registry = check_faults(monkeypatch, {}, open_issues=("unknown_model_99999",))

    assert registry.deleted == ["unknown_model_99999"]


def test_an_unrelated_issue_is_left_alone(monkeypatch):
    """The sweep knows the two prefixes it owns and touches nothing else."""
    registry = check_faults(monkeypatch, {}, open_issues=("something_else",))

    assert registry.deleted == []
