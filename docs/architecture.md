# How the integration works

`CLAUDE.md` says what to do and where. This says how the thing runs, so that
a change can be reasoned about before it is made. It was written by reading
the code as it stands on `main`, and it says which parts are load-bearing and
which are inherited from upstream and never exercised.

## The one thing to understand first

The Cozytouch API has no vocabulary. A device reports a list of items shaped
exactly like this, and nothing else:

    {"capabilityId": 93, "modificationDate": 1786182322, "value": "1"}

No name, no type, no unit, no bounds, no enum labels. `docs/api-surface.md`
records the session that went looking for a catalogue and established there
isn't one — `refs/` holds only `countries`, and no OpenAPI spec is published.

So the whole integration is one long act of translation: **a numeric model id
plus a numeric capability id become a Home Assistant entity**. Two halves
carry all of it:

- `model.py` — what the API says about a device → what it is and what it can do
- `capability.py` — `capabilityId` (+ the model's answer) → what entity to build

The first half is read from the payload, the way the vendor's own client reads
it. The second was reverse-engineered from captures, and still is: a
capability is a number on the wire with no name and no unit.

Everything else is plumbing around those two.

## The shape of a running install

One config entry is **one Atlantic account**, and one subentry of it is **one
device**. An account with a gateway and three room air conditioners is one
entry with four subentries: one login, and one poll — for the account, not for
each device, because the setup view answers for all of them at once.

It was one entry per device until the account entry landed, which is why the
per-account state matters: four entries each held their own copy of a payload
describing all four, and that state lived on the `Hub` *class* for a while, so
they wrote over each other and the last one to connect won. It is one object
now, shared on purpose. `tests/test_regressions.py` pins both halves — nothing
on the class, and one login when ten hubs reconnect at once.

```
config entry (the account) ──> CozytouchAccount
                                │
                                │  POST /users/token                      once, then on expiry
                                │  GET  /magellan/cozytouch/setupviewv2   every 30s — the beat
                                │  GET  /magellan/setups/{id}/consumptions  every 15 min, if any
                                │
                                ├─ setup     address, zones count, rateLimit…
                                ├─ zones     zone id → name, refreshed on every setup view
                                └─ devices   every device on the account, each with the
                                             capability list the setup view gave for it
                                │
                       AccountCoordinator ── the only thing on a clock
                                │  refresh_setup(), then tells every hub
                                ▼
  subentry (a device) ──> Hub (DataUpdateCoordinator, update_interval=None)
                                │
                                │  GET /magellan/capabilities/?deviceId=  after a write only
                                │
                    get_capabilities_for_device()
                                  │
                       for each reported capability:
                       get_capability_infos(modelInfos, id, value, availableIds)
                                  │
                                  ▼
                    a dict — name, type, category, wiring —
                    which each platform filters on `type`
                                  │
   ┌────────┬────────┬───────┬────┴────┬────────┬─────────────┐
 climate  sensor   switch  number   select  datetime   binary_sensor
```

Each platform's `async_setup_entry` loops over `entry.subentries` and adds its
entities with `config_subentry_id=`, which is what puts them under the right
device.

Four kinds of entity are not capability-driven, and so are not in that
fan-out. The consumption sensors are the setup's rather than a device's :
they read `GET /magellan/setups/{id}/consumptions` through the account, every
15 minutes, are entities of `AccountCoordinator` rather than of a hub, and
sit on a device of their own named after the setup -- asked for only when
no device declares an empty 164, and built only when the first answer
carries a series (`docs/decisions.md`, *Consumption*).
The other three are per device.

`binary_sensor` builds exactly one per subentry, a connectivity sensor
reflecting `hub.online` — which is the *account's* connection, the same answer
for every device on it. The sensor platform builds one more beside its
capability entities: a `timestamp` diagnostic carrying the newest
`modificationDate` the device reports, which is what says whether the hardware
is still talking to Atlantic's cloud when a reading has stopped moving. And
`calendar` builds one per program block the device reports — heating (196-202),
cooling (203-209), hot water (237-243) — expanding the seven stored days over
real dates. The last two follow the same rule: they exist only when the device
reports what they read, which for the calendar means all seven days of a block
rather than any of them, since a missing day would read as an unscheduled one.

The calendar's block table is its own, and wider than the services': while
`set_schedule` and `get_schedule` know 196 and 203, it knows 237 as well. The
asymmetry is deliberate — reading a program and writing one are not the same
risk. What the second member of a hot-water slot means has never been confirmed
against a capture, and writing the block on that basis could leave a water
heater running a program it never had; showing what the prog sensors have
rendered all along costs nothing.

It is read-only for a second reason too. An event has a start and an end; a
program slot has only a start, and the next slot is what ends it, so writing
one back would mean deciding what happens to the slots after it. That decision
belongs to `set_schedule`, which is where somebody said it out loud.

## One poll for the account

The beat is `AccountCoordinator`, and it re-reads the setup view. That payload
carries a capability list for **every** device on the account — the same three
fields the per-device route returns — so one request refreshes all of them.
It used to be one coordinator per device on its own 60-second timer, which
meant N requests a minute for N devices, all fetching slices of a payload that
describes the lot.

What that bought:

| | before | now |
| - | ------ | --- |
| requests/min, 1 device | 1 | 2 |
| requests/min, 7 devices | 7 | 2 |
| interval | 60s | 30s |
| `absence` freshness | on reconnect, so ~1h | every poll |

The hubs are still coordinators, so every entity is a `CoordinatorEntity` of
its own device and a device can be unavailable on its own. What they no longer
have is a clock: `update_interval=None`, and `async_account_updated()` pushes
to them. Their own `_async_update_data` survives for the one case that should
not wait for the account's tick — `async_request_refresh()` after a write,
where re-reading the whole household to confirm one setpoint would be absurd.

**The unverified part.** Nobody has compared the *latency* of the two routes.
They carry the same fields, and the integration has always built its entities
from the setup view at startup, but a setup view served from an aggregated
cache would look identical while being minutes behind.
`scripts/probe_api.py --cadence` is what settles it: `modificationDate` is in
both answers and read by neither. If it shows a lag, the per-device poll has to
come back as the beat, and the 429 handling below is the half of this that
stands either way.

## Being told to slow down

A 429 is the one status that must not be answered with a reconnect. It used to
fall into the generic non-200 branch, which clears `online`, so the next poll
spent a `POST /users/token` and a `GET setupviewv2` — two more requests, one of
them the failed-login kind that can lock an account out — in answer to a
complaint about making too many requests.

Now `_note_rate_limited` arms `_backoff_until` from `Retry-After`, leaves
`online` alone, and logs every `X-RateLimit-*` header it saw at warning level.
That last part is the point: `rateLimit: 30` has never been decoded, and the
first person to capture a real 429 is holding the only evidence that would say
what it counts. Every read checks the backoff before spending a request;
writes do not, because somebody pressed a button and a throttled *reader* is no
reason to swallow it.

## The account and the hub

`account.py` is the HTTP client and everything the account declares.
`hub.py` is the account coordinator, a `DataUpdateCoordinator` per device, and
the mapping accessors the platforms call. Worth knowing before changing either:

**Reconnect is driven by `account.online`.** Almost every failure path clears
it and raises `UpdateFailed`; the next poll sees it False and calls
`connect()`, which re-authenticates and re-fetches the setup view. There is no
separate retry loop — the coordinator's own schedule is it. Token expiry is
handled the same way, pre-emptively: `_token_expiry` is set 60 seconds short of
what the server said, and crossing it just clears `online`. A rate limit is the
exception that proves it: `CozytouchRateLimited` is the one failure that leaves
`online` set, precisely so none of this happens.

`connect()` is idempotent under an `asyncio.Lock`, and re-checks `online` once
the lock is held, so a successful reconnect costs one login however many
devices asked for it. A *failing* one is not collapsed: the flag stays clear,
so each waiter tries in turn. That is right for a network failure and wrong for
a refused password, which is why the next paragraph exists.

**A refused password is the one failure that is not retried.** No number of
attempts fixes wrong credentials, and repeated *failed* logins are the one
thing that could lock a Cozytouch account out (`docs/api-surface.md`). So
`InvalidAuth` — raised only for the token endpoint's `invalid_grant`, never for
a merely malformed response — is the one exception `connect()` lets out instead
of folding into `online = False`. `connect_or_auth_failed` turns it into
`ConfigEntryAuthFailed`, which is what makes Home Assistant ask for the
password; it also stops the coordinator that raised it from rescheduling
itself, which is what ends the loop rather than slowing it down.

```
invalid_grant ──> InvalidAuth ──> ConfigEntryAuthFailed ──> async_step_reauth
anything else ──> online = False ──> ConfigEntryNotReady / UpdateFailed ──> retry
```

The reauth step asks for the password only, never the username: changing that
would point the entry at a different account, where the `deviceId` of every
subentry means nothing or something else. And because the account is one entry,
it is one dialog and one write — with an entry per device it took a loop
copying the new password to every sibling, or each of them raised a prompt of
its own for the same password.

**The session belongs to Home Assistant.** `async_get_clientsession(hass)`,
which is closed at shutdown. There is nothing to close by hand, which matters
because HA does not call `async_unload_entry` when a setup fails — it discards
whatever the setup built and tries again.

**Setup does not depend on the polls landing.** The setup view carries a
capability list for every device, so the entities are built from what it said;
each hub's first poll only refreshes values. Only the account's `connect()`
raises `ConfigEntryNotReady`, so one flaky device leaves its own entities stale
instead of failing a setup its siblings share.

**Writes are not fire-and-forget.** `set_capability_value` POSTs to
`writecapability`, gets an execution id back, then polls
`/magellan/executions/{id}` — once immediately, then up to five more times at
one-second intervals — waiting for state 3. Only then is the local value
updated. A write that never completes leaves the local cache stale until the
next poll corrects it.

**Away mode is the exception to everything.** It is the one feature that does
not go through `writecapability` alone: the absence window is `PUT` to
`/magellan/v2/setups/{id}` — a setup-level resource, not a device one, which
is why `set_absence` lives on the account and the staging on the hub — and
only then written to the timestamps capability. And it is deferred: editing
the start or end datetime entity stages the value on the hub and stamps
`_timestamp_away_mode_last_change`; `_async_update_data` commits it once that
stamp is more than 20 seconds old. The delay is deliberate — it lets someone
set both ends before either is sent. The switch entity compensates for the
API lagging behind by ignoring the reported value for a few reads
(`_nb_ignore`).

## What a device is

There is no table of model ids. `get_model_infos` reads what the API sends
about a device and works the answer out, which is what Atlantic's own client
does — its `GacomaDeviceFactory` never looks at a model id.

Three inputs, in this order :

- **`productId`**, against the ranges the vendor writes out in its own
  `ProductType` enum. 26-30 and 97-111 are a room, 31-40 a wall control, 65-94
  a zone, 54 the connected board of an Alfea, 58-61 its generator, 47 and 62 a
  hot water tank, 63/95/96/98 the gateways.
- **the parent's `productId`**, where the first said `ROOM`. A room's own id is
  an index and says nothing about the hardware in it ; only an Alfea's board
  answers differently, and its rooms are heating circuits.
- **`modelFamily`**, where Atlantic assigns no product id at all —
  `Boiler`, `Water_Heater`, `Heat_Pump`, `Towel_Dryer`, `Connectivity_Box`
  and the rest of its `ModelFamily` enum.

`model_product_ids.py` answers the same question for a model id with no device
beside it — a test, a dump read offline — from the vendor's catalogue, as 168
contiguous runs. Its `LEARNED_FROM_DUMPS` holds what a live payload sent where
that catalogue leaves a 0, which is how a row gets corrected without touching
code.

Three tables take part, and only one of them decides anything :

```
        a device from the setup view
        (modelId, productId?, modelFamily?)
                     │
                     ▼
          productId sent? ──── no ───┐
                     │               ▼
                    yes    ┌──────────────────────────┐
                     │     │ model_product_ids.py     │
                     │     │ modelId → productId      │
                     │     │ (catalogue + dumps)      │
                     │     └──────────────────────────┘
                     ▼               │
          ┌───────────────────────────┐
          │ PRODUCT_TYPES (model.py)  │  decides what the
          │ productId → kind          │  device is
          │ else modelFamily          │
          └───────────────────────────┘
                     │
                     ▼
          ┌───────────────────────────┐
          │ name                      │  names it,
          │ 1. room / zone label      │  decides nothing
          │ 2. model_catalogue.py     │
          │ 3. the name the API sent  │
          │ 4. Unknown product (id)   │
          └───────────────────────────┘
                     │
                     ▼
          capabilities narrow the modes,
          then OVERRIDES and MODEL_NAMES
          have the last word
```

Then the device gets the last word on its modes. `narrow_by_capabilities`
reads capability 100022, a bitmask over the mode values, and narrows the
table's modes to what the unit supports ; and if the device reports none of
the capabilities its modes would arrive on, it has none, whatever any table
says. An empty capability list means *not known yet* rather than *reports
nothing* — `account.py` creates a device that way and fills it on the first
poll.

`OVERRIDES` is what is left : nineteen model ids where the device is wrong
about itself or cannot say. Each one is a measured difference between what a
branch used to answer and what the derivation gives, so the set is the honest
size of what this project knows and the API does not. `MODEL_NAMES` is six
names the vendor's catalogue does not carry. Nothing else is written per model.

**One device is recognised by its name instead of its id**, and it is the only
one: a THZONE, which is a zone of a ducted heat pump rather than a product. The
check runs first, so `deviceName` starting with `THZONE` wins over any id —
including an id that also belongs to a real product. Keying on the name is not
a shortcut, it is what the payload supports: a capture pairs model id 1505 with
the device the API calls `THZONE_0`, and issue #93's household reports a zone
under its parent's id, which has no product id of its own. The API's `name` is
read rather than `customName`, since renaming a zone in the Cozytouch app is a
thing people do.

A zone reports two capabilities, neither of which resolves to anything, and no
climate capability. So it is **ignored, not surfaced**:
`CozytouchAccount.device_summaries` leaves it out of what the config flow
offers, and `get_diagnostics` leaves it out of the dump. Adding one would
create a device with an empty page behind it. The raw setup view still holds
them and the `dump_json` option writes it out, which is the way back if
anybody needs to see what a zone reports.

Every lookup passes `dev["name"]`, because one without it cannot recognise a
zone. That is `hub.py` for the capability walks and the dump.

`get_zone_name` answers **None** when the account does not name a zone, where it
used to answer the id as a string. Every caller puts the result in front of
somebody — a device name, a line in a dump — and `Zone (1030104)` is a worse
name than no name: the id is ours to join on, not a room anybody recognises. A
zone with no room falls back to the name the app shows (`THZONE_0`), and a room
to its position (`Room (#1)`).

Three kinds of key come back:

- **Identity** — `name`, `type`, `modelId`.
- **Enumerations** — `HVACModes`, `HeatingModes`, `fanModes`, `swingModes`,
  `AirCirculationSpeeds`. Each maps the integer the device reports to the
  Home Assistant constant.
- **Flags** — `ecoModeAvailable`, `awayModeTemperatureAvailable`,
  `quietModeAvailable`, `overrideModeAvailable`, `exhaustTemperatureAvailable`,
  `currentTemperatureAvailable{,Z1,Z2}`.

The flags are the dangerous part, and `tests/test_capability.py` exists
because of it. A flag is read by `capability.py` to decide whether an entity
exists at all, and most of them default to `True` when absent — so a flag
nobody sets is a flag that lets an entity through, and a default flipped in
`capability.py` changes every device at once. The isolation tests walk the
whole id range and assert which ids declare each flag, which is the only place
that catches it.

`HVACModesCapabilityId` is the subtlest entry. It says which capability id
carries the mode for this product: `{7, 8}` by default, `{1, 2}` for the Alfea
Extensa Duo A.I. 3 R32, and empty for the half of an appliance that drives
nothing. The same physical function, a different number, on two models of the
same product family.

`zoneName` is threaded in for one purpose: a room is named `Room (Salon)`
rather than `Room (#1)` when the zone is known. `Hub.get_model_infos` resolves
the zone, following the `iothubChildrenIds` tag to a master device's zone for
sub-devices.

## The capability mapping

`get_capability_infos(modelInfos, capabilityId, capabilityValue, availableCapabilityIds)`
answers for 172 ids. Reading the chain end to end is one way to find out what
one of them becomes; `scripts/dump_capability_map.py` is the other — it walks
every id against one model per device type and prints the answer. It writes
nothing, so there is no table anywhere to fall out of date.

Three return values, and they are not the same:

- **a dict** (`CapabilityInfos`, declared field by field in `infos.py` like
  the model table's) — build this entity
- **`{}`** — this id is claimed, and refused for this device. Capability 172
  (the absence setpoint) returns `{}` on air conditioners because they report
  it and never honour it.
- **`None`** — nothing maps this id. It shows up in the diagnostics dump under
  `unmapped`, and becomes a raw entity only if the user ticked
  `Create entities for unknown capabilities`.

The dict's `type` is what routes it to a platform, and the routing is
one-to-many. A `switch` capability produces **both** a `CozytouchSwitch` on
the switch platform and a `CozytouchBinarySensor` on the sensor platform. An
`away_mode_timestamps` capability produces four entities: two sensors and two
datetimes. A `climate` capability produces a climate entity and a sensor. This
is inherited behaviour, not an accident to clean up casually — the entity ids
are in people's dashboards.

Which type reaches which platform is only visible by reading the seven
`async_setup_entry` functions, so here it is once:

| type | platform |
| --- | --- |
| `climate` | climate **+** sensor |
| `string`, `int`, `temperature`, `pressure`, `energy`, `volume`, `water_consumption`, `percentage`, `signal`, `time`, `timezone`, `prog`, `progtime`, `binary` | sensor |
| `switch` | sensor **+** switch |
| `away_mode_switch` | sensor **+** switch |
| `away_mode_timestamps` | sensor ×2 **+** datetime ×2 |
| `temperature_adjustment_number`, `temperature_percent_adjustment_number`, `hours_adjustment_number`, `minutes_adjustment_number` | number |
| `select` | select |

It also runs the other way. A device can report two ids for the same thing —
222 and 226 both carry the away-mode window — so the mapping names each as a
`capabilityDuplicate` of the other, and `get_capabilities_for_device` drops
whichever arrives second. One window, one pair of entities, whichever id the
hardware happens to use.

The fourth argument, `availableCapabilityIds`, is what the device actually
reports. It exists because a model id is reused across hardware that does not
implement the same things: the mapping asks "does this device back that
feature?" before wiring it. That is why the climate branch is full of
`if 100507 in availableCapabilityIds`.

### The climate branch is the wiring hub

Capabilities 1, 2, 7 and 8 don't just produce a climate entity — they collect
the ids of every other capability that entity needs, and the climate entity
reads them back out:

| key | points at | used for |
| --- | --- | --- |
| `targetCapabilityId` | 40, or 17/18 on a heat pump | the setpoint |
| `targetCoolCapabilityId` | 177 | the cooling setpoint |
| `currentValueCapabilityId` | 117 / 118 | the measured temperature |
| `lowest/highestValueCapabilityId` | 160 / 161 | the setpoint bounds |
| `lowest/highestCoolValueCapabilityId` | 162 / 163 | the cooling bounds |
| `hvacActionCapabilityId` | 181 | the mode actually running |
| `stepCapabilityId` | 294 | the setpoint granularity |
| `fanModeCapabilityId` | 100801 | fan speed |
| `quietModeCapabilityId` | 100802 | the quiet fan mode |
| `swingMode/swingOnCapabilityId` | 100803 / 100804 | louvres |
| `activity/eco/boostCapabilityId` | 100506 / 100507 / 100505 | presets |
| `progCapabilityId` + override trio | 184, 157, 158, 159 | the schedule presets |
| `airCirculationCapabilityId` | 102024 | reporting FAN while circulating |

Two details in there are not obvious. `hvacActionCapabilityId` (181) exists
because on a zoned install only the master picks the mode: a slave keeps
showing its own request while running whatever the master imposes. And
`HVACMode.AUTO` is deliberately absent from the `HVAC_ACTIONS` table — a
system in auto is really heating, cooling or idle, and guessing would be
worse than reporting nothing.

The presets are a small state machine. `basic`/`prog`/`override` come from the
scheduler (184 and 157); `none`/`activity`/`eco`/`boost` come from the three
mode capabilities. Setting a temperature while in `prog` silently switches to
`override` first, because writing a setpoint the scheduler will overwrite in
an hour would be a lie.

## Entity identity, and why renaming is safe

Unique ids key on the capability id, never on the name:

    sensor    cozytouch_{subentry_id}_{capabilityId}
    select    cozytouch_{subentry_id}_{capabilityId}  (same shape, other platform)
    switch    cozytouch_{subentry_id}_switch_{capabilityId}
    number    cozytouch_{subentry_id}_number_{capabilityId}
    climate   cozytouch_{subentry_id}_climate_{capabilityId}
    datetime  {subentry_id}_0 / _1        (away mode, not domain-prefixed)

Every platform funnels that id through one parameter, `config_uniq_id`, which
is also what the device is registered under — `identifiers={(DOMAIN, it)}`. It
was the config entry id when an entry meant a device. Nothing else in the
integration builds an identity, which is why moving to subentries touched one
argument per platform.

So renaming a capability changes its translation key and its friendly name and
leaves every existing entity in place. Recent commits rely on this — four
water-heater capabilities were renamed without breaking anyone's history.

The name doubles as the translation key, which is why a new capability needs
an entry in all three of `strings.json`, `translations/en.json` and
`translations/fr.json`. Miss one and Home Assistant shows the raw key —
`available_system_modes` — in the UI.
`tests/test_capability_coverage.py` walks every name the mapping can produce
and fails on the gap, so this is caught rather than discovered by a user.

Devices are registered per subentry, and hung under their gateway via
`get_via_device` — but only when the gateway was added as a device of its own.
The API declares the parent in `masterDeviceId`, so the topology is reported
rather than inferred; what has to be got right is not claiming a link to a
device Home Assistant doesn't have. `tests/test_topology.py` pins that.

## Diagnostics is the intake path

`get_diagnostics` is not a debugging afterthought, it is how new hardware gets
mapped. One dump per account. It lists **every** device the setup view returned
— including the ones nobody added — with its model id, whether the table knows
it, and the capability ids that came back `None`. That last list is literally
what a new mapping is written from, and unmapped hardware is usually hardware
nobody has added yet, which is why it is no longer held back to the configured
device. Credentials and anything that would place the account at an address
are redacted.

`isConfiguredHere` says which devices have a subentry, and so which have
entities. It no longer says anything about freshness: the account poll reads
the setup view, which carries every device, so a dump describes hardware nobody
added as of the last tick rather than the last reconnect. That is the half a
dump is read for. It is read off the entry's subentries, so the dump does not
depend on which hub produced it.

The dump carries the raw material a capability-only reading needs — every
capability id with its value, and the API's own identity fields
(`customName`, `longName`, `modelFamily`, `masterDeviceId`) — rather than a
computed reading of them. A `derived` block used to sit in each device's
`model` and was dropped; `docs/decisions.md` has the derivation's evidence
and why the dump now carries inputs, not conclusions.

## The services

Two services, and they are the same shape read in either direction.
`cozytouch.set_schedule` writes a weekly program, `cozytouch.get_schedule`
reads one back in the shape the first one takes. A day is a
`[[minutes, temperature], …]` matrix of ten slots, unused ones `[0, 0]`, and
the days are seven consecutive capability ids — 196 for heating Monday, 203
for cooling Monday. The write validates that the first slot starts at 00:00,
since otherwise the start of the day would have no target.

The padding is the one thing to get right in both directions: `[0, 0]` ends
the day, but a genuine midnight slot carries a setpoint, so a pair of zeroes
is padding and `[0, 17]` is not. The prog sensors already read it that way,
and `parse_slots` is the one place that reads it now — `get_schedule` and
`calendar.py` both go through it, so a calendar and a service response cannot
disagree about what a day holds.

It resolves the hub through the entity registry rather than `hass.data`, which
lets it tell apart "that entity belongs to another integration" from "that is
ours but its entry isn't loaded". The registry entry's `config_subentry_id` is
the last hop: it names which device, and so which hub.

Capabilities 100320–100333 are a second heating/cooling weekly program, on a
different device family, and the services do not reach them: `set_schedule`
and `get_schedule` know 196 and 203 only. Widening them wants a capture from
one of those devices first. `calendar.py` reads the same two blocks, from the
same table, so it stops in the same place — and so does the hot-water program
(237–243), which nothing has confirmed uses the same matrix shape.

## The device triggers

`device_trigger.py` adds five, and the interesting part is what it leaves out.
Home Assistant builds device triggers from the entity domains a device happens
to have — the connectivity binary sensor gives connected/disconnected, the
away-mode switch gives turned on, the climate entity gives HVAC mode changed —
so the only ones worth writing are the ones no domain covers:

| trigger | what it watches |
| --- | --- |
| `heating_schedule_changed` | the seven day sensors of 196–202, as a state trigger |
| `cooling_schedule_changed` | the same for 203–209 |
| `schedule_resumed` | the climate `preset_mode` attribute reaching `prog` |
| `schedule_overridden` | … reaching `override` |
| `schedule_stopped` | … reaching `basic` |

The program pair carries no `entity_id`: a program is seven sensors and no
entity stands for it, so the trigger is keyed by device and resolves the seven
at attach time, by registry id so a rename does not break it. The preset three
do carry one, since a device can hold more than one climate entity.

Both are offered only when the device has what they read — the program block
in the entity registry, the preset in the climate entity's `preset_modes` —
which is the same rule the capability table follows: declare nothing the
device has not shown you.

`climate` already ships preset conditions and actions, so there is no
`device_condition.py` and no `device_action.py` here. Adding them would put
two entries meaning the same thing in the same picker.

## Testing

Most of the suite is characterisation tests. They pin the mapping as it
stands, not as it ought to be: most entries came from one user's capture of one
device, so green means "nobody changed this by accident", never "this is
correct". `tests/test_snapshot.py` is that idea taken whole: both tables
pinned into JSON files, so a pure refactor is provable — if the snapshots do
not change, no answer did.

Almost all of them are table tests. Two of the exceptions cover
`sensor.py`. `tests/test_sensor_values.py` pins what the value builders return
character for character — the zero padding, the double space before a
temperature, a float setpoint still reading as a whole number. That file
renders the strings people actually look at and had no tests at all, which is
how a formatting change can be both invisible in review and visible on every
dashboard. `tests/test_sensor_metadata.py` covers what the platform says about
a value rather than the value: it drives `async_setup_entry` with a hub
stand-in and asserts the state class and device class each capability type
comes out with, including that the pair is one Home Assistant accepts.

**Almost nothing tests the API client.** `tests/test_reauth.py` reaches the
HTTP layer -- a `FakeSession` answering from a script -- and covers one path
end to end: what the token endpoint said, what `connect()` raises, what setup
and the poll make of it, and what the dialog does with the password somebody
types. `tests/test_regressions.py` covers the connect lock and what the setup
view fills in. Token expiry, the write-execution polling and the away-mode PUT
are still documented and unverified. That is the largest hole left in the
suite; `FakeSession` is the thing to extend when closing it.

`tests/test_floor.py` is what makes the second CI job mean something: it
imports every module — the suite otherwise imports four of them — and names the
subentry APIs the declared minimum Home Assistant has to provide. The floor was
set by running it, not by reading a changelog.

`CLAUDE.md` has the per-file breakdown and the venv instructions. Two things
worth repeating: `test_capability.py` carries a hard count of mapped model ids
(63) and walks `range(1, 2500)` — adding a model means updating the count, and
adding one above 2500 means widening the walk — and the requirements are pinned
exactly, so the version of Home Assistant the tests run against is a decision
somebody made rather than whatever pip found. CI runs the suite twice, once on
that pin and once on the oldest release `hacs.json` claims to support.

`ruff check .` is the other half, and CI gates on it. `pyproject.toml` carries
the configuration and the reason for every rule that is switched off.

## Rough edges, verified

Things that are true of the code today and would otherwise be discovered the
hard way. Most are inherited from upstream.

This list is only worth having if it is accurate, and it had gone stale: five
entries described code that had already been fixed or removed — a `time`
platform that no longer exists, a `power` type, three capabilities filed under
`diagnostic`, `percentage` claiming `SensorDeviceClass.BATTERY`, and an unused
`CozytouchDateTime`. They were checked one by one against the tree and dropped.
Anything below has been re-verified; add to it in the same spirit, and delete
from it when a change makes an entry untrue.

- **`signal` maps to `SIGNAL_STRENGTH` with `UnitOfSoundPressure.DECIBEL`.**
  The unit string is `dB`, which is valid for the device class, but it is
  reached through the sound-pressure enum.
- **The away-mode timestamp sensor applies the device's timezone offset twice.**
  `CozytouchAwayModeTimestampSensor.get_value` adds the offset the device
  reports to the unix timestamp, then formats the sum with a bare
  `datetime.fromtimestamp()` — which reads it in Home Assistant's local zone,
  adding the offset again for anyone not on UTC. `tz=UTC` is the fix; it changes
  what the sensor displays, so it wants a capture of what the Cozytouch app
  shows before it is made. The line carries a `noqa: DTZ006` so the linter does
  not have to be argued with twice, and
  `tests/test_sensor_values.py::test_the_timezone_offset_is_applied_twice_outside_utc`
  pins it, so making the fix shows up as that test failing rather than as a
  silent shift in what people see.
- **A few capabilities are deliberate placeholders.** 101–104 come out as
  `Capability_101`…, 105906/105907 as `Target 105906`…, and 312 is commented
  `For test`. The coverage test skips them by regex, which is why they have no
  translations.
- **A version 1 config entry cannot be loaded.** One entry per device became
  one entry per account with a subentry per device, and no
  `async_migrate_entry` was written — nobody was running the integration yet.
  Such an entry lands in `MIGRATION_ERROR`, and the fix is to remove the
  integration and add it again.
- **`create_unknown` is account-wide**, so turning it on to investigate one
  device adds raw entities on all of them.

## Where the boundaries are

- **Do not fetch a capability catalogue.** There isn't one.
  `docs/api-surface.md` records roughly 90 paths already ruled out; read it
  before probing anything.
- **Do not add a model id to make one product work.** The device says what it
  is ; if it comes out wrong, the question is which of `productId`,
  `modelFamily` or the parent is being misread, and the answer is usually a
  row in `model_product_ids.py` that a dump can correct. `OVERRIDES` is for a
  device that is wrong about itself, and every entry in it was measured.
- **Do not claim a type for a capability whose encoding is unverified.** Its
  row says `STRING`, `DIAG` and `enabled_by_default=False`, and sets neither
  `bits` nor `reads_as`: named, raw, off by default. 30 rows read that way
  today.
- **Do not rename entities to tidy up.** Unique ids survive a rename, but the
  friendly name people built dashboards on does not.
