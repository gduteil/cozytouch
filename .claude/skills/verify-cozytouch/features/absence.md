# Absence

The gateway's `Absence` switch puts the whole account away, between the
start and end its two date pickers hold. Every room behind the gateway
follows it, and shows it in its own `Absence` sensors.

## Sub-features

- `absence-on` turns the absence on ; a start still to come reads as
  programmed.
- `absence-off` clears it, on the gateway and every room.
- `absence-pickers` hold the start and end : empty while off until someone
  picks a date, the window sent once on.
- `absence-rooms` mirror the gateway's state and window.

## How to get to it (user POV)

- Settings → Devices → `HUB` → Controls : `Absence`, `Absence Début`,
  `Absence Fin`.
- The `cozytouch.set_away_mode` action, from an automation.

## Driving it with run.py

Preconditions:

- Default dump (no absence set) ; `R doctor` healthy.

- **Off, empty.** Run `R states hub_navizone_absence`. The switch is `off`
  and both `datetime.hub_navizone_absence_debut` and `_fin` read `unknown`.
- **On.** Run
  `R call switch.turn_on '{"entity_id": "switch.hub_navizone_absence"}'`.
  The call returns without error. `R journal` shows one absence PUT on the
  setup with a start about a minute from now and an end two days later,
  then the 222 and 152 writes on the gateway.
- **Followed.** After the next poll, `R states absence` shows the switch
  `on`, `sensor.hub_navizone_absence` `pending` (programmed), both pickers
  holding the window, and every room's `Absence` sensor following.
- **Off.** Run
  `R call switch.turn_off '{"entity_id": "switch.hub_navizone_absence"}'`.
  The journal shows a PUT with an empty absence ; after a poll the switch,
  the sensors and the pickers are back to `off` / `unknown`.
- **Proof.** Screenshot the HUB device page
  (`R device switch.hub_navizone_absence`) on and off, with the journal
  lines.

## Gotchas

- The fake accepts every write. The Navizone answers 403 on the 152 mirror
  write while still taking the absence (PR #169) : a missing error here
  proves nothing about that case.
- The fake never turns a programmed absence (2) into a running one (1) at
  its start ; nothing here can show that transition.
- Picking a date while the absence is off sends nothing ; the window is sent
  when the switch goes on. A journal with no write after a picker change is
  correct.
