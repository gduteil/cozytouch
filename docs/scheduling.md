# 🗓️ Scheduling

The weekly program a Cozytouch device holds itself : the actions that
read and write it, the triggers that watch it, the entities that show
it, the card that edits it, and asking for it out loud.

[Back to the README](../README.md)


Two actions write and read the weekly program the device holds itself, the one
the Cozytouch app calls *Chauffage* and *Refroidissement*. It keeps running when
Home Assistant is off, which is the difference with scheduling the climate
entity from an automation.

`Cozytouch: Set a day program` writes one day program to as many days as you
pick. Days can be named one by one or through `Every day`, `Weekdays` and
`Weekend`. The first slot has to start at `00:00` -- the device has no target
temperature for the hours before the first one -- and a day holds ten slots at
most, fewer if the device says so.

`Cozytouch: Read a week's program` returns the seven days of a program in the
shape the other action takes, so a program can be read, edited and written
back rather than retyped :

```yaml
- action: cozytouch.get_schedule
  target:
    entity_id: climate.salon
  data:
    program: heating
  response_variable: schedule

- action: cozytouch.set_schedule
  target:
    entity_id: climate.salon
  data:
    program: heating
    days: [weekend]
    slots: "{{ schedule['climate.salon'].days.monday }}"
```

On Home Assistant older than 2025.7 the slots field is still a YAML editor
rather than a list of time and temperature pickers : the schema'd form is not
something those frontends can draw. Everything else works the same.

Temperatures are whole degrees. Every program captured from a real device holds
integers, so a half degree has never been confirmed to survive the write.

## Triggering on the program

Five device triggers, offered per device and only when the device reports what
they read. Pick them in the automation editor under *Add trigger > Device*, or
write them out :

| Trigger | Fires when |
| ------- | ---------- |
| `The heating program changed` | any of the seven heating days was rewritten, whether from here, from the Cozytouch app or from the panel |
| `The cooling program changed` | the same, for the cooling block |
| `… went back to its program` | the device resumed following its weekly program |
| `… program was overridden` | a temporary setpoint took over -- which is what setting a temperature while in `prog` does |
| `… stopped following its program` | the program was switched off for a manual setpoint |

The three preset triggers take an optional `for`, so *overridden for two hours*
is a trigger rather than an automation with a timer in it.

```yaml
triggers:
  - trigger: device
    domain: cozytouch
    device_id: 8dd8b7f4c3a24b1e9e0e4a6d5c7b2f10
    type: heating_schedule_changed
```

Everything else worth automating on is already a device trigger Home Assistant
builds itself : *connected* and *disconnected* from the Cozytouch connectivity
sensor, *turned on* from the away-mode switch, *HVAC mode changed* from the
climate entity. Conditions and actions about presets come from the `climate`
domain the same way.

## Seeing and editing the program

A device that holds a program also gets a calendar entity for it -- *Heating
Program*, *Cooling Program*, *Hot Water Program*, whichever of the three it
reports -- so the week can be looked at on a dashboard instead of read off
seven sensors. Each slot is an event running until the next one takes over, and
its title is the target temperature.

The seven per-day sensors of a block the calendar shows are disabled by
default, on existing installations too : fourteen near-identical diagnostic
rows per air conditioner said the same thing worse. Nothing is removed -- a
dashboard or template that reads one can have it back from the device page,
under the disabled entities, and it stays enabled from then on.

The heating and cooling calendars are editable from the card itself, which is
the point of them : add an event and that slot is added, drag or resize one and
it moves, delete one and it goes. The title is the target temperature -- "19",
"19 °C" and "19,5" all work, a title with no number in it is refused.

Two things follow from a slot having only a start. An event that ends before
the end of the day adds a second slot there, putting back whatever the day held
after it, so the block drawn is the block that runs. And the slot at 00:00
cannot be deleted, since the beginning of a day must have a setpoint : retitle
it instead.

Every edit lands on that weekday for good -- the week repeats, there is no
"only this occurrence". The hot water calendar stays read-only until somebody
captures how that block is written ; `Cozytouch: Set a day program` remains the
way to write several days at once from an automation.

What they are good for besides looking at them is the `calendar` triggers,
since an event starting *is* the program moving to its next setpoint :

```yaml
triggers:
  - trigger: calendar
    entity_id: calendar.salon_heating_program
    event: start
```

The hot-water program is shown but cannot be written : `Cozytouch: Set a day
program` covers heating and cooling only, because what the second value of a
hot-water slot means has never been confirmed on a real device. Reading it back
is what the hot-water prog sensors have always done.

The times are read in Home Assistant's own timezone. The device stores minutes
past midnight and nothing in the API says which clock those belong to, so a hub
in a different timezone from the house it heats would show the program shifted.

## The schedule card

A weekly program is a list of slots, and the integration ships a card that
edits it as one -- a chip per slot, carrying the time it starts and the
setpoint it asks for. Closed, it shows the setpoint the program holds right
now; click the header to edit the week :

![The schedule card, one program open and one closed.](images/schedule-card.png)


```yaml
type: custom:cozytouch-schedule-card
entity: climate.salon
program: cooling     # or heating ; heating is the default
title: Salon cooling # optional
```

No HACS frontend repository to add : the integration serves the card itself.
Declare it once, in **Settings → Dashboards → ⋮ → Resources → Add**, as a
**JavaScript module**:

```
/cozytouch/cozytouch-schedule-card.js
```

Restart Home Assistant first if the integration was just installed -- the URL
only exists once it has started. The card is served with `Cache-Control:
no-cache`, so an update arrives on a browser refresh and the resource never
needs editing again.

Edit a time or a setpoint straight in its chip, **×** removes a slot and **+**
adds one, in the middle of the longest stretch the day leaves free and at
whatever was already in charge there. Nothing is sent until **Save**, which
writes only the days that changed.

The same rules the service has apply : a day holds ten slots at most, no two
start at the same time, and the slot at 00:00 cannot be removed -- only given
another setpoint. Heating and cooling only, for the same reason `set_schedule`
covers those two.

## Changing the program by voice

If you run Assist with a conversation agent that can use tools -- any of the
LLM integrations -- the program is one of the things you can simply ask for :

> Set the living room air conditioning to 24 between 9am and 5pm on weekdays

> What is the bedroom heating programmed to on Tuesday?

Nothing to configure : the integration offers Assist two tools, one that
reads a week and one that holds a temperature over a stretch of a day, as
soon as a Cozytouch account is set up. The device and its climate entity have
to be exposed to Assist, which is the usual **Settings → Voice assistants →
Expose**.

The writing tool changes only the stretch you name. It reads the day first,
puts back whatever was running when the period ends, and leaves every other
slot alone -- so asking for an afternoon does not cost you your evening. It
still cannot get past what the device holds : ten slots a day, one of them at
00:00.

Needs a Home Assistant recent enough to have the `llm` integration platform;
on an older one the tools are simply not offered, and everything else works
as before.

Day names follow the language set in your Home Assistant profile, and the
times display in your browser's own format.

This writes the program **into the device**, which is the difference between
it and `scheduler-card` or a Home Assistant automation : those fire a service
call at a time of day, so they stop working when Home Assistant does. What
this card writes is what the unit runs on its own.
