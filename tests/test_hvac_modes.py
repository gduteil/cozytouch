"""What the climate entity offers, against what the unit says it supports.

A model's `HVACModes` is the product line's table, and two units off the same
line differ : a heat pump sold without the cooling kit reports the same model
id as one sold with it. Capability 100022 is the bitmask that separates them,
and this is what reading it does to the mode list.

The masks are read from `HVAC_MODE_MASKS`, which is derived from the two
tables in `capability_table.py` rather than written out, so a case here fails
if either of them moves.
"""

import pytest

from custom_components.cozytouch.const import HVAC_MODE_MASKS, narrowed_modes
from homeassistant.components.climate import HVACMode

# The air conditioner table, the widest one the mapping produces.
AC_MODES = {
    0: HVACMode.OFF,
    1: HVACMode.AUTO,
    3: HVACMode.COOL,
    4: HVACMode.HEAT,
    7: HVACMode.FAN_ONLY,
    8: HVACMode.DRY,
}


def supported_hvac_modes(modes, supported):
    return list(narrowed_modes(modes, supported).values())


def test_a_unit_reporting_nothing_keeps_the_whole_table():
    """The capability is not on every device, and its absence says nothing."""
    assert supported_hvac_modes(AC_MODES, None) == list(AC_MODES.values())


def test_the_room_air_conditioners_keep_every_mode_they_had():
    """415 is what 557-561 report across the capture corpus : every mode of
    the table they are given, so the narrowing is a no-op on them.
    """
    assert supported_hvac_modes(AC_MODES, "415") == list(AC_MODES.values())


def test_a_unit_without_the_cooling_kit_loses_cooling():
    """29 is the Alfea Extensa S interface of issue #93 -- off, auto, cool
    and heat, where the same line's fan and dry bits are clear.
    """
    assert supported_hvac_modes(AC_MODES, "29") == [
        HVACMode.OFF,
        HVACMode.AUTO,
        HVACMode.COOL,
        HVACMode.HEAT,
    ]


def test_a_heating_only_unit_keeps_off_and_heat():
    """17 is what the heating-only boilers and heat pumps (1382, 1444) read."""
    assert supported_hvac_modes(AC_MODES, "17") == [HVACMode.OFF, HVACMode.HEAT]


def test_auto_owns_two_bits():
    """The vendor's app matches a mode when *any* bit of its mask is set, and
    auto's mask is 6. 411 and 415 differ by bit 2 alone and are the same set
    of modes ; a table written one-bit-per-mode would read them apart.
    """
    assert supported_hvac_modes(AC_MODES, "411") == supported_hvac_modes(
        AC_MODES, "415"
    )


@pytest.mark.parametrize("value", [5, 6, 9])
def test_a_mode_no_bit_names_is_never_dropped(value):
    """Emergency heat, pre-cooling and sleep are values the API uses and no
    mask names. Narrowing on a bitmask cannot speak for them, so they stay.
    """
    assert value not in HVAC_MODE_MASKS
    assert supported_hvac_modes({value: HVACMode.AUTO}, "17") == [HVACMode.AUTO]


def test_a_mask_that_leaves_nothing_leaves_the_table_alone():
    """A climate entity with no mode at all is broken in Home Assistant, which
    is worse than one offering a mode that does nothing. 0 is also what a
    device that does not report the capability answers by default.
    """
    assert supported_hvac_modes(AC_MODES, "0") == list(AC_MODES.values())
