"""When Home Assistant refuses Eco and the setpoint for an Absence.

On 2026-11-13 the Pagosa's ``core:OperatingModeState`` still read
``absence: on`` hours after the Absence had ended : the Atlantic period was
empty, the vendor app showed the heater in auto mode and the heat pump was
running, yet Eco was refused before any request left. The guard now needs
both the heater's flag and an Atlantic period that is not over ; anything
less is left to the heater, which refuses Eco itself while absent. See
docs/decisions.md, *Absence read as over*.
"""

import time

import pytest
from test_pagosa import hub

from custom_components.cozytouch.pagosa import controls


def absent_hub(period):
    the_hub = hub()
    the_hub._overkiz_states["core:OperatingModeState"] = {
        "relaunch": "off", "absence": "on"
    }
    the_hub._overkiz_states["io:AwayModeDurationState"] = "always"
    the_hub._setup["absence"] = period
    return the_hub


def test_a_period_still_running_refuses_eco():
    now = int(time.time())
    the_hub = absent_hub({"startDate": now - 3600, "endDate": now + 3600})
    with pytest.raises(controls.exceptions.HomeAssistantError):
        controls._require_not_absent(the_hub)


def test_a_flag_left_on_with_no_period_lets_eco_through():
    controls._require_not_absent(absent_hub({"startDate": None, "endDate": None}))


def test_a_flag_left_on_after_the_period_ended_lets_eco_through():
    now = int(time.time())
    the_hub = absent_hub({"startDate": now - 86400, "endDate": now - 3600})
    controls._require_not_absent(the_hub)


def test_no_flag_is_never_absent():
    now = int(time.time())
    the_hub = absent_hub({"startDate": now - 3600, "endDate": now + 3600})
    the_hub._overkiz_states["core:OperatingModeState"] = {
        "relaunch": "off", "absence": "off"
    }
    controls._require_not_absent(the_hub)


def test_a_flag_left_on_with_a_zero_duration_reads_as_over():
    """2026-11-13 12:27 : AwayModeDurationState went from always to 0."""
    the_hub = absent_hub({"startDate": None, "endDate": None})
    the_hub._overkiz_states["io:AwayModeDurationState"] = "0"
    assert the_hub._get_current_operating_mode()["absence"] == "off"


def test_an_absence_under_way_still_reads_as_on():
    now = int(time.time())
    the_hub = absent_hub({"startDate": now - 3600, "endDate": now + 3600})
    the_hub._overkiz_states["io:AwayModeDurationState"] = "always"
    assert the_hub._get_current_operating_mode()["absence"] == "on"
    with pytest.raises(controls.exceptions.HomeAssistantError):
        controls._require_not_absent(the_hub)
