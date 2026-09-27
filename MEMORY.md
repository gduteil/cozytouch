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
- **Air circulation is household-wide, but the app shows it per room**, so the
  per-room entities are correct. Do not move them onto the gateway.
- **The Android dex is spent** for naming : it names 188 ids, all but five
  already mapped. Its write call sites are the only writability signal
  (`docs/decisions.md`).
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

## Parked — each needs one specific piece of evidence

- 105906/105907 read as °C ; the catalogue says % (V40 charge). Needs a V40
  app screenshot.
- 100004/100021 bits 1 and 2 : catalogue and Android app disagree on hygro vs
  temperature. Needs a unit reporting one without the other.
- A room slot (557-561) is a room index behind a gateway, not a product ; read
  the gateway's model via `masterDeviceId` before touching `model.py`.

## Working here

- Pull requests go to `mathieuletyrant/cozytouch-hacs`, base `main` ; the
  repository is no longer tied to `gduteil/cozytouch` or
  `mathieuletyrant/cozytouch`. A Claude Code on the web session has no `gh`
  and opens them through the GitHub MCP tools, scoped to this repository.
- `scripts/check.sh` runs ruff, pyright and pytest, CI's three checks ; run
  it before every push.
- Releases are the maintainer's call : never run the release workflow, tag or
  `gh release create`.
- Anything that logs into the real account is run by the maintainer, not by an
  agent. A refused login is what can lock the account ; match `account.py`'s
  token request byte for byte before pointing a script at it.
- `research/` is git-excluded, so a finding made there is lost unless it is
  written into `docs/`.
- To see a change in Home Assistant, use the `test-ha` skill : a local HA
  against a fake cloud, with screenshots. Never the real account.
- Python changes on a running Home Assistant need a full restart ; reloading
  the entry keeps the cached module.
- Only the HUB Navizone (1758), its rooms (557-561) and THZONE (1505-1507) can
  be checked on hardware. Say so when a change touches anything else.
