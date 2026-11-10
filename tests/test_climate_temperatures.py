"""Which names the climate entity reports its temperatures under.

Home Assistant 2026.11 moved the climate temperatures to `native_*` names and
reads the old ones through a shim that logs a warning, until 2027.11. The
floor `hacs.json` declares has only the old names, so the entity declares one
set or the other, never both, depending on what the installed release reads.
These pin that on whichever release the job installed. See docs/decisions.md.
"""

from custom_components.cozytouch.climate import CozytouchClimate
from homeassistant.components.climate import ClimateEntity
from homeassistant.const import UnitOfTemperature

NATIVE = {
    "native_current_temperature",
    "native_target_temperature",
    "_attr_native_temperature_unit",
}
DEPRECATED = {"current_temperature", "target_temperature", "_attr_temperature_unit"}


def native_release():
    return hasattr(ClimateEntity, "native_current_temperature")


def test_the_entity_declares_the_names_the_installed_release_reads():
    declared = vars(CozytouchClimate).keys()
    wanted, unwanted = (NATIVE, DEPRECATED) if native_release() else (
        DEPRECATED,
        NATIVE,
    )

    assert wanted <= declared
    assert not unwanted & declared


def test_the_values_come_from_the_device_under_either_name():
    entity = object.__new__(CozytouchClimate)
    entity._current_value = 21.5
    entity._native_value = 19.0
    prefix = "native_" if native_release() else ""

    assert getattr(entity, f"{prefix}current_temperature") == 21.5
    assert getattr(entity, f"{prefix}target_temperature") == 19.0
    assert getattr(entity, f"{prefix}temperature_unit") == UnitOfTemperature.CELSIUS
