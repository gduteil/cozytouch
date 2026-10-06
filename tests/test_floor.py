"""What the declared minimum Home Assistant has to provide.

`hacs.json` names the oldest Home Assistant this integration claims to work
on, and `requirements_test_min.txt` exists so the claim is tested rather than
asserted. Until now the only thing testing it was that the suite imported --
and the suite imports four modules out of thirteen, none of which touches the
config flow or the platforms. A release that quietly needed something newer
would have surfaced as a bug report.

Two things here. Every module gets imported, so a name that does not exist on
the floor is a failure at the floor rather than at somebody's install. And the
handful of APIs the current shape genuinely rests on are named, so raising the
floor -- or discovering it has to be raised -- says which call did it.
"""

import importlib
import inspect
import json

import pytest

MODULES = (
    "account",
    "binary_sensor",
    "capability",
    "climate",
    "config_flow",
    "const",
    "datetime",
    "diagnostics",
    "hub",
    "model",
    "number",
    "repairs",
    "select",
    "sensor",
    "services",
    "switch",
    # "llm" is deliberately absent : the platform it is written against is
    # newer than the floor, and an install without it never imports the
    # module. tests/test_llm_tools.py skips itself for the same reason.
)


@pytest.mark.parametrize("name", MODULES)
def test_every_module_imports(name):
    """A missing name is a failure here, not on somebody's Home Assistant."""
    assert importlib.import_module(f"custom_components.cozytouch.{name}")


def test_the_integration_module_imports():
    """Separately, because importing the package pulls in every platform."""
    assert importlib.import_module("custom_components.cozytouch")


def test_config_subentries_exist_at_all():
    """One entry per account, one subentry per device, is the whole shape.

    Subentries arrived in Home Assistant 2025.2. Everything below is what
    `hacs.json` is really claiming.
    """
    from homeassistant.config_entries import (
        ConfigSubentry,
        ConfigSubentryData,
        ConfigSubentryFlow,
    )

    assert ConfigSubentry is not None
    assert ConfigSubentryData is not None
    assert ConfigSubentryFlow is not None


def test_a_config_flow_can_create_an_entry_with_its_subentries():
    """The devices are picked in the same flow as the credentials, so they are
    created with the entry rather than added one dialog at a time after it.
    """
    from homeassistant.config_entries import ConfigFlow

    parameters = inspect.signature(ConfigFlow.async_create_entry).parameters

    assert "subentries" in parameters


def test_an_entity_can_be_added_under_a_subentry():
    """Without this the entities of every device would land on the account,
    which is the flat list the subentries exist to replace.

    Read off the code object rather than through `inspect.signature`: the
    annotations of that method do not resolve under Python 3.14, and what is
    being asked here is whether the argument exists.
    """
    from homeassistant.helpers.entity_platform import EntityPlatform

    assert (
        "config_subentry_id"
        in EntityPlatform.async_add_entities.__code__.co_varnames
    )


def test_an_integration_can_declare_which_subentries_it_supports():
    """The "Add device" button on the integration page is this method."""
    from homeassistant.config_entries import ConfigFlow

    assert hasattr(ConfigFlow, "async_get_supported_subentry_types")


def test_the_reauth_helpers_exist():
    """The reauth step reads its entry and writes back through these two.

    Both are conveniences Home Assistant added at some point, so they belong in
    the list of things the declared floor has to have rather than in a
    traceback on somebody's old install.
    """
    from homeassistant.config_entries import ConfigFlow

    assert hasattr(ConfigFlow, "_get_reauth_entry")

    parameters = inspect.signature(ConfigFlow.async_update_reload_and_abort).parameters

    assert "data_updates" in parameters


def test_the_coordinator_can_be_pushed_to():
    """The hubs no longer have a clock; the account tells them.

    `async_set_updated_data` and `async_set_update_error` are what a coordinator
    driven from outside is made of, and the account poll calls both -- one on
    every tick, the other whenever the account fails and every device has to
    say so.
    """
    from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

    assert hasattr(DataUpdateCoordinator, "async_set_updated_data")
    assert hasattr(DataUpdateCoordinator, "async_set_update_error")


def test_the_number_selector_takes_a_unit():
    """The poll interval is seconds, and the box says so.

    `unit_of_measurement` on a NumberSelector is the difference between asking
    for a number and asking for a duration; a floor that does not have it would
    reject the options schema at import time.
    """
    from homeassistant.helpers import selector

    assert "unit_of_measurement" in selector.NumberSelectorConfig.__annotations__


def test_the_declared_floor_is_the_one_the_tests_run_against():
    """hacs.json and requirements_test_min.txt have to say the same thing, or
    the job proving the floor is proving a different one.
    """
    with open("hacs.json", encoding="utf-8") as handle:
        declared = json.load(handle)["homeassistant"]

    with open("requirements_test_min.txt", encoding="utf-8") as handle:
        pinned = [
            line.split("==")[1].strip()
            for line in handle
            if line.startswith("homeassistant==")
        ]

    assert pinned == [declared]
