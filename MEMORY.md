# Project memory

What past sessions settled, so the next one does not redo it. Each line is a
conclusion with where its evidence lives. Newest correction wins ; when you
overturn one, edit the line here in the same pull request.

## Settled — do not re-probe

- **The capability catalogue exists.** `GET /magellan/productmodels/capabilities`
  returns 405 ids with name, enum, unit, bounds and `accessType`, readable with
  an ordinary account token. `scripts/capability_catalogue.jsonl` is the last
  read. Atlantic's `name` is an internal id, not a translation key : check a
  row's meaning against it, never rename an entity to match it.
- **The model catalogue exists.** `GET /magellan/productmodels/models/{modelId}`
  answers for any model id, owned or not. Query it before asking a reporter
  what a device is called.
- **No second data plane.** `setupviewv2` is the whole functional payload,
  but for consumption : `GET /magellan/setups/<setupId>/consumptions?periodicity=daily`,
  implemented from `mmnlfrrr/cozytouch`'s ACI HYB capture and never seen
  answering here. Capability 164 gates it : the Navizone reads 0 and is never
  asked, the fork's Duralis 1040. `docs/decisions.md`, *Consumption*.
- **The Overkiz plane is empty for us.** The token mints an Overkiz JWT, but
  `enduserAPI/login` answers 401. `docs/api-surface.md`.
- **`productId` classifies a device, not `modelId`** -- the vendor app resolves
  on the pair (own `productId`, parent's `productId`). `docs/decisions.md`.
- **100022 is the firmware family's mode mask, not the device's** ; 166 narrows
  it but moves with the season, so it picks modes, never a device type.
- **102020 is the system's service** and propagates to every room ; 7 is the
  room's own state. Settled by capturing the iOS app. `docs/decisions.md`.
- **The general stop is 102020 at 0**, and every room follows : 7 and 181 to
  0, 166 to 1. Read off a dump taken after the app's stop (2026-09-28) ; what
  starting again does to the rooms is unseen. `docs/decisions.md`.
- **Air circulation is household-wide, but the app shows it per room**, so the
  per-room entities are correct. Do not move them onto the gateway.
- **The Android dex is spent** for naming : it names 188 ids, all but five
  already mapped. Its write call sites are the only writability signal
  (`docs/decisions.md`).
- **A programmed absence is 2** : the app writes 152 = 2 for a start still to
  come, and the rooms' 100261 follow at 2. 2026-09-28 dump, Navizone.
- **The setup PUT is what sets an absence** ; the Navizone refuses the
  152/222 mirror writes (403, state 4) and still turns programmed.
  2026-10-05 HA history, `docs/decisions.md`.
- **153 stays 0 on the Navizone rooms while cooling**, so it is no running
  signal there. **Absence timestamps are plain unix time** ; 315 is not
  added. Both from the 2026-09-25 dump, `docs/decisions.md`.
- **Atlantic named eleven hot-water ids once**, on gduteil/cozytouch#129
  (234-288). Check that list before reverse-engineering an id in that range.

## Rejected — do not re-propose

- Turning the capability branches into a `SIMPLE_CAPABILITIES` dict (#86).
- An `OVERRIDES` entry typing LORIA 416-425 as a heat pump : deduced from the
  catalogue, not measured. Wait for a dump ; if it carries `modelFamily`, there
  is nothing to map.
- Rewiring `_room_entity` on capability 103026 : one observation, on air
  conditioners only. A room behind a *radiator* gateway reading 16/32/64 there
  is what would settle it.
- A "house" climate entity on the HUB carrying the system's modes, with the
  rooms cut down to off and the current mode : declined by the maintainer
  (2026-09-28), with five other shapes the same day. The answer, as the app
  draws it : a select per room for the system's service (102020, general
  stop included), and each room's climate reduced to off and the house's
  current mode (7). `docs/decisions.md`.

## Parked — each needs one specific piece of evidence

- 105906/105907 read as °C ; the catalogue says % (V40 charge). Needs a V40
  app screenshot.
- 100004/100021 bits 1 and 2 : catalogue and Android app disagree on hygro vs
  temperature. Needs a unit reporting one without the other.
- Whether the cloud turns a programmed absence (152 = 2) to 1 at its start.
  The 2026-09-25 dump fits, but that absence was touched from Home Assistant
  first. Needs a dump taken after the start of one programmed from the app.
- A room slot (557-561) is a room index behind a gateway, not a product ; read
  the gateway's model via `masterDeviceId` before touching `model.py`.

## Working here

- Pull requests go to `mathieuletyrant/cozytouch-hacs`, base `main` ; the
  repository is no longer tied to `gduteil/cozytouch` or
  `mathieuletyrant/cozytouch`. A Claude Code on the web session opens them
  through the GitHub MCP tools, scoped to this repository, and cannot
  attach images : its proxy refuses GraphQL, Git Data writes and any
  pushed ref but a branch (tested 2026-10-05, #179).
- `scripts/check.sh` runs ruff, pyright and pytest, CI's three checks ; run
  it before every push.
- Releases are the maintainer's call : never run the release workflow, tag or
  `gh release create`.
- Anything that logs into the real account is run by the maintainer, not by an
  agent. A refused login is what can lock the account ; match `account.py`'s
  token request byte for byte before pointing a script at it.
- Research findings live under `docs/research/` (how the apps were read,
  the corpus) ; the local `research/` folder is gone. Never commit the APK,
  decompiled code or vendor UI text : `docs/research/methods.md`.
- The README contact address is a deliberate public alias ; never change it.
- To see a change in Home Assistant, use the `verify-cozytouch` skill : a
  local HA against a fake cloud, with screenshots. Never the real account.
- Python changes on a running Home Assistant need a full restart ; reloading
  the entry keeps the cached module.
- Only the HUB Navizone (1758), its rooms (557-561) and THZONE (1505-1507) can
  be checked on hardware. Say so when a change touches anything else.
