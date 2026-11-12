"""The hot-water mode select offers what 105011 declares.

The options used to come from a per-model table, `HeatingModes`, which gave
every tank manual, eco_plus and prog. The vendor's app builds the list from
105011 instead (issue #206) : a tank that does not declare prog greys it
out, and one in eco_comfort_schedule (87 = 2) is in a mode the table did
not know, which the select then showed as its last known option.

The masks below are the four the corpus of #206 reports, plus the Lineo
1959's 7941 (2026-11-12). A device without 105011 keeps its table.
"""

from types import SimpleNamespace

from custom_components.cozytouch.capability import get_capability_infos
from custom_components.cozytouch.const import declared_dhw_modes
from custom_components.cozytouch.model import get_model_infos
from custom_components.cozytouch.select import CozytouchSelect

LINEO = 1959
TABLE = {0: "manual", 3: "eco_plus", 4: "prog"}


def test_16133_declares_manual_and_eco_plus():
    assert declared_dhw_modes(TABLE, "16133") == {0: "manual", 3: "eco_plus"}


def test_16141_declares_prog_too():
    assert declared_dhw_modes(TABLE, "16141") == {
        0: "manual",
        3: "eco_plus",
        4: "prog",
    }


def test_32003_declares_manual_and_the_eco_comfort_schedule():
    assert declared_dhw_modes(TABLE, "32003") == {
        0: "manual",
        2: "eco_comfort_schedule",
    }


def test_the_lineo_declares_no_prog():
    assert declared_dhw_modes(TABLE, "7941") == {0: "manual", 3: "eco_plus"}


def test_without_105011_the_table_stands():
    assert declared_dhw_modes(TABLE, None) == TABLE


def test_a_mask_naming_no_writable_mode_keeps_the_table():
    """256 alone is boost, a state : an empty select would be worse."""
    assert declared_dhw_modes(TABLE, "256") == TABLE


def select(values):
    modelInfos = get_model_infos(LINEO, None, None)
    capability = get_capability_infos(
        modelInfos, 87, values.get(87, "0"), set(values)
    )
    coordinator = SimpleNamespace(
        get_capability_value=lambda capabilityId, default="0": values.get(
            capabilityId, default
        ),
        get_model_infos=lambda: modelInfos,
    )
    return CozytouchSelect(
        coordinator=coordinator,
        capability=capability,
        config_title="Ballon",
        config_uniq_id="sub-1",
    )


def test_the_select_offers_what_the_tank_declares():
    assert select({87: "0", 105011: "7941"}).options == ["manual", "eco_plus"]


def test_a_tank_in_eco_comfort_schedule_reads_it():
    entity = select({87: "2", 105011: "32003"})
    entity.get_value()

    assert entity.current_option == "eco_comfort_schedule"


def test_a_mode_outside_the_list_reads_unknown_rather_than_stale():
    entity = select({87: "4", 105011: "7941"})
    entity.get_value()

    assert entity.current_option is None
