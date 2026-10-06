# Room climate

Each room behind a gateway is a climate entity named `Pièce` on its device
page : the room's current temperature, its setpoint, the mode it runs in and
its preset (`prog`, `basic`, `override`). It is what a thermostat card shows
and what a user changes the temperature from.

## Sub-features

- `climate-current` shows the room's measured temperature (capability 117).
- `climate-setpoint` shows and changes the setpoint of the running mode.
- `climate-mode` shows the room's mode and action (`cool` / `cooling`).
- `climate-preset` switches between the program and a manual setpoint.

## How to get to it (user POV)

- Settings → Devices → the room (`ROOM_0`…) → the `Pièce` row in Controls,
  which opens the climate dialog.
- A thermostat card on a dashboard.

## Driving it with run.py

Preconditions:

- Default dump ; `R doctor` healthy.

- **Read.** Run `R states climate.room_bureau_piece`. It reads
  `cool {'hvac_action': 'cooling', 'preset_mode': 'prog', ...}`. Its
  attributes (`/api/states/climate.room_bureau_piece`) show
  `current_temperature: 23.9` and `temperature: 24.0`.
- **Current temperature, on screen.** Run
  `node scripts/test_ha/screenshot.cjs "$(R device climate.room_bureau_piece)" <scratchpad>/shots/climate.png --click "Pièce"`.
  The dialog shows `Température actuelle` with `23,9 °C` above the dial.
- **Setpoint.** Run
  `R call climate.set_temperature '{"entity_id": "climate.room_bureau_piece", "temperature": 25}'`.
  `R journal` shows the capability write ; after the next poll the
  attribute `temperature` reads `25.0` and the `Température Consigne Cool`
  number on the device page follows.
- **Preset.** Run
  `R call climate.set_preset_mode '{"entity_id": "climate.room_bureau_piece", "preset_mode": "basic"}'`.
  The journal shows the write and `preset_mode` reads `basic`.
- **Proof.** The screenshot, the attributes before and after, and the
  journal lines.

## Gotchas

- `current_temperature` reads 117 whatever 103150 says (PR #170). A room
  with 117 missing has no current temperature at all ; that is not the same
  bug.
- With a room off (7 = 0) the dial reads `Éteint` but still shows
  `Température actuelle` above it : a missing line there is the bug, not the
  off state.
- The room offers only the modes its system allows (`hvac_modes` is
  `['off', 'cool']` here) ; a heat mode missing on this dump is correct.
