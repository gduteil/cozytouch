"""The tools Assist is handed : what they ask for, and what they write.

A voice assistant is the one caller that cannot be corrected halfway. It gets
one shot at a tool call, so what matters here is that the shape it is offered
cannot be filled in wrongly (the day names are an enum, the times are parsed
rather than trusted) and that a period reaches the device as a *merge* : the
model never hands back a day, so it cannot drop a slot it forgot to repeat.

Skipped whole on an install too old for the platform, which is also the
install `hacs.json` declares -- the floor cannot run this file and does not
have to, since nothing imports the module there either.
"""

import asyncio
from datetime import UTC, datetime
from functools import partial
import json
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant.components.llm")

from test_services import FakeHub, make_hass
import voluptuous as vol

from custom_components.cozytouch import llm, services
from custom_components.cozytouch.hub import Hub
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers.llm import LLM_API_ASSIST, ToolInput

# Cooling, whose seven days start here.
FIRST = 203
WEEK = json.dumps([[0, 26], [420, 24], [1320, 26]] + [[0, 0]] * 7)

CONTEXT = SimpleNamespace(context=None, assistant="conversation")


def bus(hass):
    """Give the fake hass a service bus that actually runs the handlers."""
    services.async_register_services(hass)

    async def async_call(domain, service, data, blocking=False,
                         return_response=False, context=None):
        handler, schema, _ = hass.services.registered[(domain, service)]
        return await handler(SimpleNamespace(data=schema(data)))

    hass.services.async_call = async_call
    hass.config_entries.async_entries = lambda domain: ["an entry"]
    return hass


def call(tool, hass, **args):
    return asyncio.run(
        tool.async_call(hass, ToolInput(tool.name, args), CONTEXT)
    )


class WritingHub(FakeHub):
    """A hub that reads back what was written to it.

    `FakeHub` only records the write, which is all test_services asks of it;
    here a tool reads the program after writing it, so the two have to agree.
    """

    async def set_capability_value(self, capabilityId, value):
        await super().set_capability_value(capabilityId, value)
        self.values[capabilityId] = value


def registries(
    monkeypatch, entity_id="climate.salon", platform="cozytouch", extra=()
):
    """The registries the tools walk to list what Assist may reach."""
    entries = {
        eid: SimpleNamespace(
            entity_id=eid,
            domain=eid.split(".")[0],
            platform=platform,
            name=None,
            original_name="Climatisation",
            area_id="salon",
            device_id=None,
            translation_key=key,
        )
        for eid, key in ((entity_id, None), *extra)
    }
    monkeypatch.setattr(
        llm,
        "er",
        SimpleNamespace(async_get=lambda hass: SimpleNamespace(entities=entries)),
    )
    monkeypatch.setattr(
        llm,
        "ar",
        SimpleNamespace(
            async_get=lambda hass: SimpleNamespace(
                async_get_area=lambda area_id: SimpleNamespace(name="Salon")
            )
        ),
    )
    monkeypatch.setattr(
        llm, "dr", SimpleNamespace(async_get=lambda hass: SimpleNamespace())
    )
    monkeypatch.setattr(llm, "async_should_expose", lambda hass, assistant, eid: True)


@pytest.fixture
def hass(monkeypatch):
    hub = WritingHub({FIRST + index: WEEK for index in range(7)})
    registries(monkeypatch)
    return bus(make_hass(monkeypatch, hub)), hub


def test_assist_is_offered_the_two_tools(hass):
    tools = llm.async_get_tools(hass[0], CONTEXT, LLM_API_ASSIST)
    assert [tool.name for tool in tools.tools] == [
        "cozytouch_get_schedule",
        "cozytouch_set_schedule_period",
    ]


def test_another_api_is_offered_nothing(hass):
    assert llm.async_get_tools(hass[0], CONTEXT, "some-other-api") is None


def test_an_install_with_no_reachable_device_is_offered_nothing(monkeypatch, hass):
    registries(monkeypatch, platform="somebody_else")
    assert llm.async_get_tools(hass[0], CONTEXT, LLM_API_ASSIST) is None


def test_the_prompt_names_the_devices_and_where_they_are(hass):
    """A model told no entity id writes the one it would have chosen."""
    tools = llm.async_get_tools(hass[0], CONTEXT, LLM_API_ASSIST)
    assert "- climate.salon: Climatisation, Salon" in tools.prompt


def test_an_id_that_does_not_exist_is_refused_with_the_ones_that_do(hass):
    """The first real call invented an id; the error has to make a retry work."""
    with pytest.raises(ServiceValidationError, match=r"climate\.salon"):
        call(llm.ReadSchedule(), hass[0],
             entity_id="climate.clim_chambre_parents", program="cooling")


def test_an_entity_kept_from_assist_is_not_named_either(monkeypatch, hass):
    monkeypatch.setattr(llm, "async_should_expose", lambda hass, a, eid: False)
    assert llm.async_get_tools(hass[0], CONTEXT, LLM_API_ASSIST) is None


def test_reading_answers_with_the_week(hass):
    answer = call(llm.ReadSchedule(), hass[0],
                  entity_id="climate.salon", program="cooling")
    assert answer["days"]["monday"] == [
        {"time": "00:00", "temperature": 26},
        {"time": "07:00", "temperature": 24},
        {"time": "22:00", "temperature": 26},
    ]


def test_a_period_is_merged_into_the_day_rather_than_replacing_it(hass):
    """The slots the assistant never mentioned have to survive it."""
    hub = hass[1]
    call(llm.SetPeriod(), hass[0], entity_id="climate.salon", program="cooling",
         days=["monday"], start="09:00", end="17:00", temperature=21)

    capabilityId, value = hub.written[0]
    assert capabilityId == FIRST
    assert json.loads(value)[:5] == [
        [0, 26], [420, 24], [540, 21], [1020, 24], [1320, 26]
    ]


def test_a_shortcut_writes_every_day_it_stands_for(hass):
    hub = hass[1]
    call(llm.SetPeriod(), hass[0], entity_id="climate.salon", program="cooling",
         days=["weekdays"], start="09:00", end="17:00", temperature=21)

    assert sorted(written[0] for written in hub.written) == list(
        range(FIRST, FIRST + 5)
    )


def test_identical_days_are_written_in_one_call(hass):
    """Seven writes for one sentence is seven refreshes of the device."""
    hub = hass[1]
    call(llm.SetPeriod(), hass[0], entity_id="climate.salon", program="cooling",
         days=["all"], start="09:00", end="17:00", temperature=21)

    assert hub.refreshed == 1


def test_a_period_answers_with_the_program_as_it_now_stands(hass):
    answer = call(llm.SetPeriod(), hass[0], entity_id="climate.salon",
                  program="cooling", days=["monday"], start="09:00",
                  end="17:00", temperature=21)
    assert {"time": "09:00", "temperature": 21} in answer["days"]["monday"]


@pytest.mark.parametrize(
    "args",
    [
        {"days": ["someday"]},
        {"days": []},
        {"program": "ventilation"},
        {"start": "nine"},
        {"entity_id": "not an entity"},
    ],
)
def test_a_tool_call_that_cannot_be_filled_in_is_refused(hass, args):
    """The model gets one shot, so a wrong field stops before the device."""
    with pytest.raises(vol.Invalid):
        call(llm.SetPeriod(), hass[0],
             **{"entity_id": "climate.salon", "program": "cooling",
                "days": ["monday"], "start": "09:00", "end": "17:00",
                "temperature": 21, **args})


# --- the absence -------------------------------------------------------------


AWAY_SWITCH = "switch.hub_absence"
START = int(datetime(2099, 10, 1, 8, 0, tzinfo=UTC).timestamp())
END = int(datetime(2099, 10, 8, 18, 0, tzinfo=UTC).timestamp())


class AwayHub(FakeHub):
    """A gateway with an away switch, whose absence the services set."""

    def __init__(self):
        super().__init__({152: "0", 222: "[0,0]"})
        self.account = object()
        self.absences = []
        self.away_mode_switches = partial(Hub.away_mode_switches, self)
        self.reported_away_window = partial(Hub.reported_away_window, self)

    async def set_away_mode(self, start, end):
        self.absences.append((start, end))
        away = start is not None
        self.values[222] = f"[{start},{end}]" if away else "[0,0]"
        self.values[152] = "2" if away else "0"
        return True


@pytest.fixture
def away(monkeypatch):
    hub = AwayHub()
    registries(monkeypatch, extra=((AWAY_SWITCH, "away_mode"),))
    return bus(make_hass(monkeypatch, hub)), hub


def test_assist_is_offered_the_absence_tools_where_there_is_a_switch(away):
    tools = llm.async_get_tools(away[0], CONTEXT, LLM_API_ASSIST)
    assert [tool.name for tool in tools.tools] == [
        "cozytouch_get_schedule",
        "cozytouch_set_schedule_period",
        "cozytouch_get_away_mode",
        "cozytouch_set_away_mode",
        "cozytouch_clear_away_mode",
    ]
    assert "whole home" in tools.prompt


def test_a_home_without_an_away_switch_is_offered_no_absence_tool(hass):
    tools = llm.async_get_tools(hass[0], CONTEXT, LLM_API_ASSIST)
    assert "cozytouch_set_away_mode" not in [tool.name for tool in tools.tools]


def test_setting_an_absence_goes_through_the_service_and_reads_it_back(away):
    """The model hands two local dates ; the service does the rest."""
    hass, hub = away

    status = call(
        llm.SetAway(),
        hass,
        start="2099-10-01 08:00+00:00",
        end="2099-10-08 18:00+00:00",
    )

    assert hub.absences == [(START, END)]
    assert status[AWAY_SWITCH]["absence"] == "programmed"
    assert status[AWAY_SWITCH]["start"].startswith("2099-10-01")
    assert status[AWAY_SWITCH]["end"].startswith("2099-10-08")


def test_an_end_before_the_start_is_refused_before_anything_is_written(away):
    hass, hub = away

    with pytest.raises(ServiceValidationError):
        call(llm.SetAway(), hass, start="2099-10-08 18:00", end="2099-10-01 08:00")

    assert hub.absences == []


def test_clearing_ends_it_and_says_so(away):
    hass, hub = away
    call(llm.SetAway(), hass, end="2099-10-08 18:00")

    status = call(llm.ClearAway(), hass)

    assert hub.absences[-1] == (None, None)
    assert status == {AWAY_SWITCH: {"absence": "off", "start": None, "end": None}}


def test_reading_says_off_when_there_is_none(away):
    assert call(llm.ReadAway(), away[0]) == {
        AWAY_SWITCH: {"absence": "off", "start": None, "end": None}
    }


def test_a_switch_kept_from_assist_is_not_offered(monkeypatch, away):
    monkeypatch.setattr(
        llm, "async_should_expose", lambda hass, a, eid: eid != AWAY_SWITCH
    )
    tools = llm.async_get_tools(away[0], CONTEXT, LLM_API_ASSIST)
    assert "cozytouch_set_away_mode" not in [tool.name for tool in tools.tools]
