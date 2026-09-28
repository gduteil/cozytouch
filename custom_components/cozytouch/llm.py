"""What a voice assistant is allowed to do with a device's weekly program.

Home Assistant discovers this module by name : the `llm` integration imports
`<integration>/llm.py` from every loaded integration and asks it for tools,
so nothing here has to be registered and nothing outside it has to change.
That platform is newer than the Home Assistant version `hacs.json` declares,
which is why this module is not in the floor test's list -- an install too
old to have the platform never imports it. See docs/decisions.md.

The absence tools are the services, on the other hand : setting an absence
is one window and a switch, with nothing on the device to merge into, so the
model hands over two dates and `set_away_mode` does the rest -- the window
is the account's, and a start still to come is written as programmed.

The two program tools are deliberately not the two services. A service writes a whole
day, because that is what the device stores; a person asks for a stretch of
one. Handing the raw write to an assistant means asking a language model to
copy nine slots back unchanged, and the day that gets written is the day it
remembered. `apply_period` does the merge instead.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any

import voluptuous as vol

from homeassistant.components.homeassistant import async_should_expose
from homeassistant.components.llm import LLMTools
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import (
    area_registry as ar,
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
)
from homeassistant.helpers.llm import LLM_API_ASSIST, LLMContext, Tool, ToolInput
from homeassistant.util import dt as dt_util
from homeassistant.util.json import JsonObjectType

from .const import DOMAIN, PROGRAM_DAYS, WRITABLE_PROGRAM_BLOCKS
from .services import (
    DAY_GROUPS,
    SERVICE_CLEAR_AWAY_MODE,
    SERVICE_GET_SCHEDULE,
    SERVICE_SET_AWAY_MODE,
    SERVICE_SET_SCHEDULE,
    _resolve_hub,
    apply_period,
    expand_days,
)

PROMPT = (
    "A Cozytouch heater or air conditioner keeps its own weekly program, which "
    "runs whether or not Home Assistant is up. A day is a list of slots, each "
    "one a time it starts and a temperature it asks for, and a slot runs until "
    "the next one starts. Read the program before answering questions about it, "
    "and change it with the period tool rather than describing the change."
)

AWAY_PROMPT = (
    "The Cozytouch absence (away mode) belongs to the whole home, not to one "
    "device : setting it sets it everywhere. An absence whose start is still "
    "to come is programmed, and starts on its own. Dates are the home's local "
    "time. Read the absence before answering questions about it."
)

# What an away switch's value means, in the words the tools answer with.
AWAY_STATES = {"value_off": "off", "value_pending": "programmed", "value_on": "on"}

_ENTITY = vol.Required(
    "entity_id",
    description="The climate entity, as its entity id, for example climate.salon",
)
_PROGRAM = vol.Required(
    "program",
    description="Which of the device's two programs, heating or cooling",
)
_DAYS = vol.Required(
    "days",
    description=(
        "The days to change. Either day names, or the shortcuts "
        f"{', '.join(DAY_GROUPS)}"
    ),
)


def _programmable(hass: HomeAssistant, llm_context: LLMContext) -> dict[str, str]:
    """The devices these tools can reach, as entity id to where it lives.

    Both tools take an entity id, and a language model that has not been told
    one will write the id it would have chosen -- which is how the first real
    call went, `climate.clim_chambre_parents` for an entity actually called
    `climate.chambre_parents_clim_chambre_parents_climatisation`. So the list
    goes in the prompt, and in the error when an id is wrong anyway.

    Only what the assistant is allowed to see : an entity kept from Assist
    should not be named by a tool description either.
    """
    entities = er.async_get(hass)
    areas = ar.async_get(hass)
    devices = dr.async_get(hass)

    found: dict[str, str] = {}
    for entry in entities.entities.values():
        if entry.platform != DOMAIN or entry.domain != "climate":
            continue
        if llm_context.assistant and not async_should_expose(
            hass, llm_context.assistant, entry.entity_id
        ):
            continue

        area_id = entry.area_id
        if area_id is None and entry.device_id:
            device = devices.async_get(entry.device_id)
            area_id = device.area_id if device else None
        area = areas.async_get_area(area_id) if area_id else None

        name = entry.name or entry.original_name or entry.entity_id
        found[entry.entity_id] = f"{name}, {area.name}" if area else name

    return found


def _checked(hass: HomeAssistant, llm_context: LLMContext, entity_id: str) -> str:
    """Refuse an unknown id with the ids that do exist, so a retry can work."""
    known = _programmable(hass, llm_context)
    if entity_id in known:
        return entity_id

    listed = "; ".join(f"{eid} ({what})" for eid, what in known.items())
    raise ServiceValidationError(
        f"There is no Cozytouch device called {entity_id}. "
        + (f"The ones there are: {listed}" if listed else "This account has none.")
    )


def _away_switches(hass: HomeAssistant, llm_context: LLMContext) -> list[str]:
    """The away switches Assist may reach, one per account or more.

    The services keep one write per account, so handing them every switch is
    how an absence reaches every account the assistant can see.
    """
    return [
        entry.entity_id
        for entry in er.async_get(hass).entities.values()
        if entry.platform == DOMAIN
        and entry.domain == "switch"
        and entry.translation_key == "away_mode"
        and not (
            llm_context.assistant
            and not async_should_expose(hass, llm_context.assistant, entry.entity_id)
        )
    ]


def _local(timestamp: int) -> str:
    return dt_util.as_local(datetime.fromtimestamp(timestamp, UTC)).isoformat(
        timespec="minutes"
    )


def _away_status(hass: HomeAssistant, llm_context: LLMContext) -> JsonObjectType:
    """What each reachable switch says : off, programmed or on, and when."""
    status: dict[str, Any] = {}
    for entity_id in _away_switches(hass, llm_context):
        hub = _resolve_hub(hass, entity_id)
        for capabilityId, settings in hub.away_mode_switches().items():
            value = hub.get_capability_value(capabilityId, None)
            state = next(
                (word for key, word in AWAY_STATES.items() if settings[key] == value),
                "unknown",
            )
            window = hub.reported_away_window() if state != "off" else None
            status[entity_id] = {
                "absence": state,
                "start": _local(window[0]) if window else None,
                "end": _local(window[1]) if window else None,
            }
    return status


class ReadAway(Tool):
    """Say whether the home is away, and from when to when."""

    name = "cozytouch_get_away_mode"
    description = (
        "Read the Cozytouch absence of the home : off, programmed (its start "
        "is still to come) or on, with when it starts and ends."
    )
    parameters = vol.Schema({})

    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        """Answer with the absence as the devices report it."""
        return _away_status(hass, llm_context)


class SetAway(Tool):
    """Set the home's absence, from a start to an end."""

    name = "cozytouch_set_away_mode"
    description = (
        "Put the home in absence on Cozytouch, from a start to an end, in the "
        "home's local time. Without a start it begins in a minute. The heating "
        "or air conditioning follows the absence for the whole home."
    )
    parameters = vol.Schema(
        {
            vol.Optional(
                "start",
                description="When the absence starts, as YYYY-MM-DD HH:MM",
            ): cv.string,
            vol.Required(
                "end", description="When the absence ends, as YYYY-MM-DD HH:MM"
            ): cv.string,
        }
    )

    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        """Hand the window to the service, then answer with what it set."""
        args = self.parameters(tool_input.tool_args)
        await hass.services.async_call(
            DOMAIN,
            SERVICE_SET_AWAY_MODE,
            {"entity_id": _away_switches(hass, llm_context), **args},
            blocking=True,
            context=llm_context.context,
        )
        return _away_status(hass, llm_context)


class ClearAway(Tool):
    """End the home's absence."""

    name = "cozytouch_clear_away_mode"
    description = (
        "End the Cozytouch absence of the home, or cancel a programmed one."
    )
    parameters = vol.Schema({})

    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        """Switch the absence off everywhere, then answer with the result."""
        await hass.services.async_call(
            DOMAIN,
            SERVICE_CLEAR_AWAY_MODE,
            {"entity_id": _away_switches(hass, llm_context)},
            blocking=True,
            context=llm_context.context,
        )
        return _away_status(hass, llm_context)


class ReadSchedule(Tool):
    """Read a device's weekly program back."""

    name = "cozytouch_get_schedule"
    description = (
        "Read the weekly program a Cozytouch heater or air conditioner keeps in "
        "its own memory. Answers with each day's slots: when each one starts and "
        "the temperature it asks for, a slot running until the next one."
    )
    parameters = vol.Schema(
        {_ENTITY: cv.entity_id, _PROGRAM: vol.In(WRITABLE_PROGRAM_BLOCKS)}
    )

    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        """Answer with the program, as the device holds it."""
        args = self.parameters(tool_input.tool_args)
        entity_id = _checked(hass, llm_context, args["entity_id"])
        return await _read(hass, llm_context, entity_id, args["program"])


class SetPeriod(Tool):
    """Hold one temperature over a stretch of a day, on the days asked for."""

    name = "cozytouch_set_schedule_period"
    description = (
        "Have a Cozytouch heater or air conditioner hold one temperature between "
        "two times of day, on the days given, leaving the rest of each day as it "
        "is. Use this for any change to the program: it reads the day first and "
        "puts back whatever was running when the period ends."
    )
    parameters = vol.Schema(
        {
            _ENTITY: cv.entity_id,
            _PROGRAM: vol.In(WRITABLE_PROGRAM_BLOCKS),
            _DAYS: vol.All(
                cv.ensure_list,
                vol.Length(min=1),
                [vol.In([*PROGRAM_DAYS, *DAY_GROUPS])],
            ),
            vol.Required(
                "start", description="When the period starts, as HH:MM"
            ): cv.time,
            vol.Required(
                "end",
                description=(
                    "When the period ends, as HH:MM. 00:00 means the end of the "
                    "day"
                ),
            ): cv.time,
            vol.Required(
                "temperature", description="The temperature to hold, in °C"
            ): vol.Coerce(float),
        }
    )

    async def async_call(
        self, hass: HomeAssistant, tool_input: ToolInput, llm_context: LLMContext
    ) -> JsonObjectType:
        """Merge the period into each day, then write the days that changed."""
        args = self.parameters(tool_input.tool_args)
        entity_id = _checked(hass, llm_context, args["entity_id"])
        program = args["program"]

        stored = (await _read(hass, llm_context, entity_id, program))["days"]

        # Days that end up identical are written together : one call is one
        # refresh of the device, and seven of them for "every day" is a poll
        # storm for a single sentence.
        together: dict[str, list[str]] = {}
        for day in expand_days(args["days"]):
            if day not in stored:
                continue
            slots = apply_period(
                stored[day], args["start"], args["end"], args["temperature"]
            )
            written = [
                {"time": slot["time"].isoformat(timespec="minutes"),
                 "temperature": slot["temperature"]}
                for slot in slots
            ]
            together.setdefault(json.dumps(written), []).append(day)

        for shape, days in together.items():
            await hass.services.async_call(
                DOMAIN,
                SERVICE_SET_SCHEDULE,
                {
                    "entity_id": entity_id,
                    "program": program,
                    "days": days,
                    "slots": json.loads(shape),
                },
                blocking=True,
                context=llm_context.context,
            )

        # The program as it now stands, so the assistant reports what the
        # device holds rather than what it asked for.
        return await _read(hass, llm_context, entity_id, program)


async def _read(
    hass: HomeAssistant, llm_context: LLMContext, entity_id: str, program: str
) -> dict[str, Any]:
    """The get_schedule response for one entity."""
    response = await hass.services.async_call(
        DOMAIN,
        SERVICE_GET_SCHEDULE,
        {"entity_id": entity_id, "program": program},
        blocking=True,
        return_response=True,
        context=llm_context.context,
    )
    return (response or {})[entity_id]


@callback
def async_get_tools(
    hass: HomeAssistant, llm_context: LLMContext, api_id: str
) -> LLMTools | None:
    """Offer Assist the tools for what the home has, and nothing otherwise."""
    if api_id != LLM_API_ASSIST:
        return None

    tools: list[Tool] = []
    prompts: list[str] = []

    known = _programmable(hass, llm_context)
    if known:
        listed = "\n".join(f"- {eid}: {what}" for eid, what in known.items())
        tools += [ReadSchedule(), SetPeriod()]
        prompts.append(
            f"{PROMPT}\nThe devices with a program, by entity id:\n{listed}"
        )

    if _away_switches(hass, llm_context):
        tools += [ReadAway(), SetAway(), ClearAway()]
        prompts.append(AWAY_PROMPT)

    if not tools:
        return None

    return LLMTools(tools=tools, prompt="\n\n".join(prompts))
