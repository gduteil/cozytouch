# Consumption

A device whose setup reports consumption gets energy sensors on its `Maison`
device : what the home consumed, from the setup's daily consumption history.
This is what the Energy dashboard reads.

## Sub-features

- `consumption-today` shows today's consumption.
- `consumption-absent` : a setup that reports none gets no sensor.

## How to get to it (user POV)

- Settings → Devices → `Maison` → Sensors.
- Settings → Dashboards → Energy, once the sensor is added there.

## Driving it with run.py

Preconditions:

- Started with `scripts/test_ha/water_heater.json` (a Duralis ACI HYB, 393) ;
  `R doctor` shows that dump.

- **Find it.** Run `R states maison`. The consumption sensors are listed
  with a number.
- **Value.** Compare with the dump : the fake serves its `consumptions`
  moved so the latest day is today, so today's sensor equals the dump's
  latest day.
- **Absent.** Start with the default `navizone.json`, whose setup reports
  no consumption. `R states maison` lists no consumption sensor.
- **Proof.** Screenshot the `Maison` device page
  (`R device <one of the sensors>`) and the two `states` outputs.

## Gotchas

- The real endpoint was never seen answering on the maintainer's Navizone ;
  this is the shape from another fork's capture (`docs/decisions.md`,
  *Consumption*). A sensor here proves the parsing, not the endpoint.
- Not driven when this map was written : the entity ids are left to
  `R states maison` until a run records them here.
