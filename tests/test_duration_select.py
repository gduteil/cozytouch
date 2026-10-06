"""The air-circulation duration offered as the app's picker.

The vendor app writes this setting from a grid the device declares -- 102025
the minimum, 102026 the maximum, 102022 the step -- and never lets a value
between two steps through. These pin the grid the select builds, the HH:MM
labels it shares with the app, and the two seams that matter: a device
reporting the duration without its grid falls back to the mapping's
constants, and a reported value off the grid reads as unknown rather than
snapping to a neighbour.

The entity is driven unbound against a stand-in, the way test_diagnostics.py
drives Hub.get_diagnostics: _handle_coordinator_update touches nothing of
Home Assistant beyond async_write_ha_state.
"""

from types import SimpleNamespace

from custom_components.cozytouch.infos import CapabilityInfos
from custom_components.cozytouch.select import (
    CozytouchDurationSelect,
    duration_options,
    format_duration,
    parse_duration,
)

# The grid every capturing model (557-559) reports: 15 to 300 by 15.
CORPUS_GRID = (15, 300, 15)


def test_the_corpus_grid_is_the_apps_picker():
    options = duration_options(*CORPUS_GRID)

    assert len(options) == 20
    assert options[0] == "00:15"
    assert options[1] == "00:30"
    assert options[-1] == "05:00"


def test_labels_read_like_a_clock():
    assert format_duration(75) == "01:15"
    assert format_duration(300) == "05:00"


def test_every_label_writes_back_the_minutes_it_stands_for():
    for option in duration_options(*CORPUS_GRID):
        assert format_duration(parse_duration(option)) == option


def test_a_maximum_off_the_grid_is_not_overshot():
    assert duration_options(15, 40, 15) == ["00:15", "00:30"]


def test_a_zero_step_yields_no_options_rather_than_hanging():
    assert duration_options(15, 300, 0) == []


def capability(**extra):
    """The 102021 mapping as capability.py builds it."""
    infos = CapabilityInfos()
    infos.capabilityId = 102021
    infos.lowestValueCapabilityId = 102025
    infos.highestValueCapabilityId = 102026
    infos.stepCapabilityId = 102022
    infos.lowest_value = 15
    infos.highest_value = 300
    infos.step = 15
    for key, value in extra.items():
        infos[key] = value
    return infos


def entity(values, capabilityInfos=None):
    """A stand-in carrying only what _handle_coordinator_update touches."""
    written = []
    fake = SimpleNamespace(
        _capability=capabilityInfos if capabilityInfos is not None else capability(),
        coordinator=SimpleNamespace(
            get_capability_value=lambda capabilityId, default="0": values.get(
                capabilityId, default
            )
        ),
        async_write_ha_state=lambda: written.append(True),
    )
    # The update reads the grid through the entity's own helper, so the
    # stand-in has to carry the real one.
    fake._grid_value = lambda idField, fallbackField: (
        CozytouchDurationSelect._grid_value(fake, idField, fallbackField)
    )
    return fake


def test_the_grid_is_read_from_the_device_not_from_the_mapping():
    """A device declaring a different grid gets that grid, not the corpus one."""
    fake = entity({102021: "60", 102025: "30", 102026: "120", 102022: "30"})

    CozytouchDurationSelect._handle_coordinator_update(fake)

    assert fake._attr_options == ["00:30", "01:00", "01:30", "02:00"]
    assert fake._attr_current_option == "01:00"


def test_a_device_without_its_grid_falls_back_to_the_mapping():
    """The sibling ids answer None when the device does not report them."""
    fake = entity({102021: "45", 102025: None, 102026: None, 102022: None})

    CozytouchDurationSelect._handle_coordinator_update(fake)

    assert len(fake._attr_options) == 20
    assert fake._attr_current_option == "00:45"


def test_a_value_off_the_grid_reads_as_unknown_not_as_a_neighbour():
    fake = entity({102021: "17", 102025: None, 102026: None, 102022: None})

    CozytouchDurationSelect._handle_coordinator_update(fake)

    assert fake._attr_current_option is None


def test_a_value_that_is_not_a_number_reads_as_unknown():
    fake = entity({102021: None, 102025: None, 102026: None, 102022: None})

    CozytouchDurationSelect._handle_coordinator_update(fake)

    assert fake._attr_current_option is None
