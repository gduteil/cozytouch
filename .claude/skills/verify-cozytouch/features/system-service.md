# System service

Each room carries a `Service du système` select : the service the whole
system runs (off, heat, cool, auto, dry), shared by every room, as the
Cozytouch app draws it. Choosing it on one room changes it for all of them ;
`off` is the general stop.

## Sub-features

- `service-select` changes the system's service from any room.
- `service-propagate` shows the new service on every room.
- `service-stop` stops the system : every room off.

## How to get to it (user POV)

- Settings → Devices → any room → Controls → `Service du système`.

## Driving it with run.py

Preconditions:

- Default dump (all three rooms cooling) ; `R doctor` healthy.

- **Read.** Run `R states service_du_systeme`. All three selects read
  `cool` ; the options are `['off', 'heat', 'cool', 'auto', 'dry']`.
- **Change from one room.** Run
  `R call select.select_option '{"entity_id": "select.room_bureau_service_du_systeme", "option": "dry"}'`.
  `R journal` shows one 102020 write. After the next poll, every room's
  select reads `dry`.
- **General stop.** Run the same call with `"option": "off"`. After a poll
  every select reads `off` and every `climate.room_*_piece` reads `off`.
- **Proof.** Screenshot two rooms' device pages after the change, with the
  journal line.

## Gotchas

- Propagation to every room is played by the fake, as a capture showed the
  cloud does it ; it proves the integration reads it, not that Atlantic
  still does.
- What starting again after a general stop does to the rooms was never
  captured ; the fake does not invent it.
