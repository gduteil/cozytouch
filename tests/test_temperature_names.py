"""The climate temperatures, under the names the installed release reads.

Home Assistant 2026.11 renamed what a climate entity provides :
current_temperature, target_temperature and _attr_temperature_unit became
native_current_temperature, native_target_temperature and
_attr_native_temperature_unit. The old names still answer there, but a class
that provides them is warned about at every start, and they stop working in
2027.11. Before 2026.11 only the old names exist. So the entity declares one
set or the other, and these pin that it declares the set the installed release
reads -- whichever the job installed, as test_topology.py does for
via_device_id. CI's two releases both predate the rename.

The properties are read unbound against a stand-in, the way
test_hvac_action.py drives the entity.
"""

from types import SimpleNamespace

from custom_components.cozytouch import climate as climate_module
from custom_components.cozytouch.climate import CozytouchClimate
from homeassistant.components.climate import ClimateEntity

NATIVE = hasattr(ClimateEntity, "native_current_temperature")
NAMES = (
    ("native_current_temperature", "native_target_temperature")
    if NATIVE
    else ("current_temperature", "target_temperature")
)
OTHER_NAMES = (
    ("current_temperature", "target_temperature")
    if NATIVE
    else ("native_current_temperature", "native_target_temperature")
)


def test_the_flag_matches_the_installed_release():
    assert climate_module._NATIVE_TEMPERATURES is NATIVE


def test_the_entity_provides_only_the_names_the_release_reads():
    """Providing the old names at all is what 2026.11 warns about, so the
    entity must not carry both sets.
    """
    declared = vars(CozytouchClimate)

    assert all(name in declared for name in NAMES)
    assert not any(name in declared for name in OTHER_NAMES)


def test_the_temperatures_read_what_the_device_reported():
    fake = SimpleNamespace(_current_value=21.5, _native_value=19.0)
    current, target = (getattr(CozytouchClimate, name) for name in NAMES)

    assert current.fget(fake) == 21.5
    assert target.fget(fake) == 19.0
