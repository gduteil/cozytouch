"""How the Pagosa's two time slots are written.

On one Pagosa account (2026-11-13), Overkiz refused a setProgrammingSlots
holding slot1 alone (HTTP 400 from its driver, which reads slot2's start),
accepted slot2 at 00:00-00:00 beside it, and the heater then reported that
single slot. The heater also renumbers its slots, the longer one first, so
changing one boundary through a time entity may land on the other slot.
These pin the answer : the set_programming_slots action always sends both
slots in one command, an absent second slot as 00:00-00:00. See
docs/decisions.md, *The Pagosa's time slots*.
"""

import asyncio
from datetime import time

import pytest
import voluptuous as vol

from custom_components.cozytouch.pagosa.hub import NO_SLOT, PagosaHub, programming_slots
from custom_components.cozytouch.services import (
    SET_PROGRAMMING_SLOTS_SCHEMA,
    requested_slots,
)


def test_a_single_slot_is_written_with_an_empty_second_one():
    assert programming_slots([("11:00", "19:00")]) == {
        "slot1": {"start": "11:00", "end": "19:00"},
        "slot2": NO_SLOT,
    }


def test_two_slots_are_written_as_given():
    assert programming_slots([("01:56", "06:56"), ("13:56", "16:56")]) == {
        "slot1": {"start": "01:56", "end": "06:56"},
        "slot2": {"start": "13:56", "end": "16:56"},
    }


def test_a_slot_may_run_past_midnight():
    assert programming_slots([("22:00", "06:00")])["slot1"] == {
        "start": "22:00",
        "end": "06:00",
    }


@pytest.mark.parametrize(
    ("slots", "reason"),
    [
        ([], "one or two"),
        ([("10:00", "10:00")], "starts and ends"),
        ([("01:00", "02:00")] * 3, "one or two"),
    ],
)
def test_what_the_heater_cannot_mean_is_refused(slots, reason):
    with pytest.raises(ValueError, match=reason):
        programming_slots(slots)


def test_the_second_slot_needs_both_ends():
    with pytest.raises(vol.Invalid):
        SET_PROGRAMMING_SLOTS_SCHEMA(
            {
                "entity_id": "time.chauffe_eau_programmation_1_debut",
                "slot1_start": "11:00",
                "slot1_end": "19:00",
                "slot2_start": "02:00",
            }
        )


def test_the_action_reads_its_fields_as_hours_and_minutes():
    data = SET_PROGRAMMING_SLOTS_SCHEMA(
        {
            "entity_id": "time.chauffe_eau_programmation_1_debut",
            "slot1_start": "01:56:00",
            "slot1_end": time(6, 56),
            "slot2_start": "13:56",
            "slot2_end": "16:56",
        }
    )
    assert requested_slots(data) == [("01:56", "06:56"), ("13:56", "16:56")]


def test_the_hub_sends_one_command_and_shows_it_at_once():
    hub = object.__new__(PagosaHub)
    sent = []
    shown = []

    async def execute(command, parameters=None, label=None, refresh=True):
        sent.append((command, parameters, refresh))

    async def run(operation, optimistic_states=None, label=""):
        shown.append(optimistic_states)
        await operation()

    hub.async_execute_overkiz_command = execute
    hub.async_run_pagosa_operation = run

    asyncio.run(hub.async_set_programming_slots([("11:00", "19:00")]))

    value = {"slot1": {"start": "11:00", "end": "19:00"}, "slot2": NO_SLOT}
    assert sent == [("setProgrammingSlots", [value], False)]
    assert shown == [{"io:ProgrammingSlotsState": value}]
