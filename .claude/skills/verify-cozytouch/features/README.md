# Cozytouch verification map

The maintained list of what a user of the integration touches in Home
Assistant, and how to prove each part works. Read this index before driving
an instance, then use the matching feature file as the recipe. `R` is the
`R()` function defined in [`../SKILL.md`](../SKILL.md), which wraps
`python3 scripts/test_ha/run.py`.

## Baseline preconditions

- An instance started by this run, per `../SKILL.md` *Launch*, on a port
  nobody else holds (`TEST_HA_PORT=8124` when 8123 is taken).
- `R doctor` shows both processes running, the intended HA version,
  `cozytouch entry: loaded`, and the intended dump.
- Unless a recipe says otherwise, the dump is the default
  `scripts/test_ha/navizone.json` : a gateway `HUB` and three rooms named
  `ROOM_0`, `ROOM_1`, `ROOM_2` (zones *Chambre parentale*, *Bureau*,
  *Chambre enfant*), all three cooling, no absence set.
- Never drive an instance this run did not start.

## Driving conventions

- Act through `R call DOMAIN.SERVICE JSON` : the call a dashboard makes.
  Never write into the fake or into `.test-ha/` to produce a state.
- Entities follow a write at the next poll ; wait up to a minute, then read
  with `R states TEXT` or `/api/states/<entity_id>`.
- Every write lands in `R journal` ; check it there, not only in a state.
- Screenshots go to `<scratchpad>/shots/`. Open each with Read before
  sending it.

## Proof and skip reporting

- A proof names the feature ID, the dump, the HA version, the action taken,
  the resulting state, and the journal line for any write.
- UI proof is a screenshot of the page or dialog a user would look at.
- Say what the fake does not simulate (`../SKILL.md`) when the question is
  about the cloud's answer rather than the integration's reading.
- A path the instance cannot reach (a device the dump lacks) is reported as
  skipped with the reason, never as verified through another path.

## Feature entry contract

Each feature file starts with an H1 title and one paragraph on the
user-visible behaviour, then exactly four H2 sections in this order :
`Sub-features`, `How to get to it (user POV)`, `Driving it with run.py`
(opening with `Preconditions:`), `Gotchas`. Implementation details stay out ;
the map names user paths, entity ids, commands and observable proof.

## Features

- [Room climate](./room-climate.md) : current temperature, setpoint, mode
  and preset of a room behind a gateway.
- [Absence](./absence.md) : the gateway's absence switch, its two date
  pickers, and every room following it.
- [System service](./system-service.md) : the house-wide service select on
  each room, general stop included.
- [Consumption](./consumption.md) : the energy sensors of a water heater
  whose setup reports consumption.
