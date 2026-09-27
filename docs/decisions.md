# Decisions

Why the configuration is what it is. The workflows and the config files say
what happens ; this file says why, so that the reasoning does not have to sit
as a comment block on top of every setting.

One section per file, one entry per setting. An entry states the evidence and
its limits — what was measured, on what, and what the measurement does not
cover — in the same way a commit message here does.

Files written before this convention still carry their reasoning inline :
`pyproject.toml`, the three requirements files, and the modules under
`custom_components/`. They are not being rewritten wholesale. A file moves
here when it is edited for some other reason.

## `scripts/test_ha/`

### A test Home Assistant, against a fake cloud rather than the account

Checking a change on a running Home Assistant used to mean the maintainer's
own install, on the real account -- and agents are kept off the account,
because a refused login is what can lock it. So a page was first seen after
a release.

The fake serves a diagnostics dump as the account, which is what a dump
already is : every device, every capability value, the setup's absence.
Writes are stored and served back. The only cloud behaviour it plays is what
a capture showed -- 102020 reaching every room, a gateway's 152 and 222
mirrored onto its rooms -- because anything guessed there would be tested
against itself. The integration is copied, not imported from the
repository, with its API address rewritten in the copy, so the code under
test is not edited to be testable. Home Assistant runs from a venv of its
own, `.venv-ha`, since its first start installs the frontend and the
default integrations' requirements, and the pinned test venv must not grow
them.

`navizone.json` is the 2026-09-25 Navizone dump (1758, rooms 557-559) with
the names, device ids, zone ids and setup id replaced, and the absence
cleared so a scenario starts from home.

## `.github/workflows/tests.yaml`

### ruff, and not `ruff format`

Check only. The tree is not formatter-clean, and reformatting it is a change
that should be reviewed on its own rather than folded into a lint pass.
`pyproject.toml` holds the configuration, including which rules are off and
why.

### The ruff job installs with pip, the pytest job with uv

Measured, not assumed : ruff is one small wheel, so pip fetches it in about
four seconds. Installing uv first to halve that costs three seconds, which
leaves nothing. The pytest job is where the installer is worth changing.

### The pytest job installs with uv

Nine tenths of this workflow was the installer, not the tests. On run
32898866439, pip took 47 s on the pinned environment and 96 s on the floor,
against 4 s of pytest and under a second of ruff ; the median run over the
preceding thirty was 92 s. The suite itself is not slow — 279 tests finish in
three seconds.

uv fetches and unpacks in parallel and reads a wheel's metadata without
downloading the whole file, which on a dependency tree of Home Assistant's size is
where the time goes. Measured on `requirements_test_min.txt`, cold cache :
96 s of pip becomes 9 s, with Home Assistant 2024.12.0 and the same 279 tests
passing. The whole step sequence, from `pip install uv` to the last
assertion, runs in 19 s.

What that does not cover : the pinned leg. No 3.14 interpreter is installable
off the runner, so 47 s is CI's own figure and the gain there is inferred
from the floor's.

### uv is pinned

Same reason `requirements_lint.txt` gives for pinning ruff : a tool that
arrives on its own can turn a green branch red without a commit. Bump it
deliberately.

### A venv, rather than `uv pip install --system`

`--system` is the shorter spelling, and it resolves whatever interpreter
`PATH` happens to hold — then refuses outright on one its distribution marks
as externally managed. The runner's is not, so `--system` would work there,
but it is the form that cannot be rehearsed anywhere else. The venv names the
interpreter instead of inheriting it.

Consequence worth knowing : `uv venv` does not put pip in the venv, so
`.venv/bin/pip` does not exist and the step that reports what was installed
uses `uv pip show`.

### Nothing is cached

A warm uv cache does the install in 0.7 s rather than 9 s. The cache is
444 MB for one matrix leg alone : restoring that costs about what the cold
install costs, and there would be two of them living under the repository's
cache quota to buy it.

### The matrix does not fail fast

One combination failing should not hide the result of the other. Which of the
two broke is the whole diagnostic.

### The two legs

`requirements_test.txt` on Python 3.14.2 is the pinned environment : what a
contributor's venv resolves to, and what CLAUDE.md tells you to build.
`requirements_test_min.txt` on Python 3.13.7 is the floor `hacs.json`
declares, tested so that the declaration keeps meaning something ;
`tests/test_floor.py` is the part of the suite that leg exists for.

The floor is 2025.4.0, and it was found by running that suite rather than by
reading a changelog. Config subentries — one entry per account, one subentry
per device — are absent from 2025.2.0, and the whole 2025.3.x line cannot be
installed at all : it pins an `aiohttp` release PyPI has since yanked.
`requirements_test_min.txt` carries the same reasoning inline, at more
length.

### A job named `pytest`, on top of the matrix

Everything outside the workflow refers to a check by its name, and a matrix
renames every job it touches : `pytest` became `pytest (HA … on Python …)`,
twice. Anything that required the old name — the branch protection rule
requiring `ruff`, `pytest` and `validate-hacs` above all — then waits forever
for a check that no longer reports, which looks exactly like the tests never
starting.

So the name stays, on a job that does nothing but agree with the matrix.
`needs` on a matrix job is the aggregate : success only if every leg
succeeded. `if: always()` because a skipped job reports neither pass nor fail,
and the point of this one is to always report something.

### Python is pinned down to the patch

Not `"3.14"`. Home Assistant pins its Python floor that precisely — 2026.8.3
needs >= 3.14.2 — so a floating minor would let the runner image decide which
Home Assistant is installable, which is the drift the pinned requirements
exist to remove.

### pyright, on the typed core

The declared fields on `ModelInfos`/`CapabilityInfos` are only worth what
checks them, and until this job nothing did. `pyproject.toml` scopes pyright
to `infos.py`, `model.py` and `capability.py` — the typed core,
where the declarations live — rather than the tree : the platforms and the hub read
Home Assistant's heavily-typed API, and making them pyright-clean is its own
project, not a line in this one. Basic mode for the same reason.

`pythonVersion` is `"3.13"`, the floor's Python, not the pinned 3.14 : syntax
the floor cannot parse has to fail here, and anything 3.13 accepts 3.14
accepts too.

The pin is `requirements_typecheck.txt`, its own file, because pyright needs
the full test environment to resolve the `homeassistant` imports — it cannot
live in `requirements_lint.txt` without dragging Home Assistant into the ruff
job. It started inline in the workflow ; it moved to a file when
`.claude/hooks/session-start.sh` needed the same pin, so that a cloud session
has the same three checks as CI without a second copy to keep in step.

Measured before wiring it up : 11 errors on the scope, of which 10 were the
missing venv configuration and one was real — `get_model_infos` could assign
a `str | None` device name into the zone's `name` field, which the
`(deviceName or "")` guard hid from the checker. The run that stays green is
the run that found one.

## `custom_components/cozytouch/binary_sensor.py`

### Two connectivity sensors, not one

`isAvailable` (the cloud's per-device reachability) and `online` (the account's
session, the existing CloudConnectivity sensor) are two different questions,
and the DeviceAvailability sensor keeps them apart rather than folding them.

Folding — `is_on = online and isAvailable` — was considered and rejected: a
single sensor could not say *which* was down when it read off, and the whole
value of `isAvailable` is telling "the cloud is unreachable" from "this one
device is". So there are two connectivity binary sensors on each device: the
account session (same answer everywhere) and this device's own availability.

`is_on` is the raw `isAvailable`, no gateway→child derivation: the cloud
already marks a child unavailable when its gateway drops (every capture where
one device is false has the whole account false), so deriving it again would
only risk contradicting the field. When the session drops the sensor keeps its
last value and stays available itself — consistent with the 429 backoff, which
holds last values rather than flapping every entity unavailable; the
CloudConnectivity sensor is what says whether the reading is still fresh.
Absent field reads as unknown, never a guessed state.

Enabled by default, unlike the static descriptors: it is one sensor per device
and it is the answer to "is my device reachable", which the freshness sensor
(`last_device_update`) cannot give — a healthy but idle device has an old date
without being down.

## `custom_components/cozytouch/capability.py`

### Capability 218 is a connectivity code, and was never a wifi flag

218 was mapped as a boolean binary sensor whose `is_on` was `value == "1"`.
It read permanently "disconnected" on working hardware, because the value is
never "1": across 42 models in the capture corpus it is "0" (92 readings) or
"4" (6), never "1". It was then surfaced raw and off by default, with this
entry saying plainly that nothing decoded the 0/4 value space -- not the
decompiled Dart, not the Kotlin SDK, not any reflected enum, which confirmed
only the name: id 218 -> case 2 -> `wifiConnected`.

That name was the whole problem. Atlantic's own catalogue calls 218
`ConnectivityDiagnosis`, "Defines the connectivity of our system", and
publishes the codes it answers at
`GET /magellan/productmodels/connectivitydiagnosis` -- seven of them, each
with a description and the vendor's own troubleshooting text:

| | |
| --- | --- |
| 0 | connectivity OK, no error |
| 1 | the product is unreachable, and the Cozytouch bridge is fine |
| 2 | the Cozytouch bridge is offline |
| 3 | the product is unreachable, and the Navilink interface is fine |
| 4 | the Navilink interface is offline |
| 5 | a technical issue in Atlantic's cloud |
| 6 | maintenance |

So the corpus reads exactly as it should: 92 devices saying "no error" and 6
saying "the Navilink interface this hangs off is offline". Nothing was ever
broken about the value; the mapping was asking it a question it does not
answer.

The row is renamed and reads its codes. It stays a diagnostic and stays off
by default: per-device reachability is still `isAvailable`, which is what the
app uses, and this is a fault code rather than a live link state. A zone
still gets nothing at all, having no readings to go with it.

The rename changes what the entity is called for anybody who had enabled it.
Its unique id is built from the capability id and does not move, so no history
is lost, and the old name asserted something false.

### An electric heater's action is the element (153), not the mode (181)

181 carries the mode a device is really running, as against the one it was
asked for, and the climate entity turns it into an `HVACAction`. On a radiator
that reads `heating` from the moment the thing is switched on : 181 says heat,
and heat is what it says whether or not the element is drawing.

gduteil/cozytouch#68 is that seen from a dashboard. A Sauter Tahual behind a
CozyBox, setpoint 19, room 22.95, and Home Assistant reporting that the
radiator was heating. Its dump has `153` -- the element -- reading 0, which is
the answer: on, at temperature, idle.

153 is not new here. It already ships as a binary sensor, named `resistance`
on an electric heater and `flame` on a boiler, so what it means is established
in the mapping rather than guessed for this. The wiring is narrow on purpose:
`heatingActiveCapabilityId` is set only for `ELECTRIC_HEATERS`, and only when
the device reports 153. It can only ever turn `HEATING` into `IDLE` -- off
stays off, and nothing else is second-guessed.

Limits. The only capture is one radiator idling, 153 at 0 with the room three
degrees over setpoint; nobody has sent a paired reading of the same radiator
drawing. The reading rests on what the mapping already calls the capability,
not on that pair. **Boilers are deliberately left out** even though 153 is the
flame there : a boiler's flame can be lit for domestic hot water while the
central heating circuit is genuinely idle, so the same rule would report the
opposite error on hardware nobody has a dump for. Air conditioners too -- 153
is reported on the room slots behind a Navizone and reads 0 on every one of
them, which is either an idle compressor or a field the hardware never fills,
and one dump cannot say which.

### Capability 100450 `activationProgAnticipation` is a switch

The vendor app's "Anticipation de chauffe" toggle, per room: on, the device
starts early so the room is at temperature at the scheduled time; off, it
starts heating at the scheduled time. Promoted from a self-describing raw
sensor to a writable switch on a live experiment (2026-08-29): the toggle
was flipped Off on one of three room ACs and the diagnostics dump read back
`100450 = "0"` on that unit with a `modificationDate` stamped at the moment
of the toggle, `"1"` untouched on the other two -- and 100450 was the *only*
capability whose date moved, so the app writes this id directly rather than
through a sibling.

Limits: verified on models 557-559, which are also the only models in the
capture corpus that report the id at all, always as 0/1. The companion
103450 (`progMilestoneAnticipationState`, presumably "currently
anticipating") appears on no captured hardware and stays self-describing.

### Capability 171 `awayCooling` is read-only, where 172 is a number

171 sits next to 172 `awayHeating`, which has been the writable
`away_mode_temperature` since long before this entry. The name comes from the
decompiled app (`research/Capability-Reference.md`), and the capture corpus
agrees on the unit without exception : 35.0 on all eight models that report it
(211, 422, 1444, 1693, 1715, 1758, 1941, 2145), against 17.0 for the heating
side on the boiler the mapping was read from.

What no capture shows is anything writing it. 172 is a number because the app
offers that setting and a dump read the written value back ; nothing equivalent
was seen for 171, and every reading of it is the same untouched 35.0. So it is
a temperature sensor, diagnostic, `enabled_by_default` False -- the unit is
known, the direction is not. Promoting it takes one person moving the absence
cooling setpoint in the app and a dump showing 171 followed.

It carries the same `awayModeTemperatureAvailable` gate as 172, for the reason
given there : an air conditioner stores an absence setpoint and never acts on
it.

The heat-pump branch used to carry `# capability.highestValueCapabilityId =
171` commented out, which would have read the absence setpoint as a maximum
bound. It was never live and is now gone.

## `custom_components/cozytouch/model.py`

### 1734-1737 are the room air conditioners a gateway numbers past its fifth (issue #61)

One household (issue #61, September 2026) runs nine room units behind a
single HUB Cozytouch (1457). The API names them `ROOM_0` to `ROOM_8` and
hands the first five the ids 557-561, then jumps : `ROOM_5` is 1734 and
`ROOM_6`, `ROOM_7`, `ROOM_8` are 1735, 1736, 1737, with `productId` running
97-100 where the first block runs 26-30. So 1734, mapped earlier on its own
from a single report, was the first id of a second block rather than a
separate product, and the three after it are the same thing : the
`iothubChildrenIds` tag is a `THZONE_n` on every one of them, `masterDeviceId`
is the hub, and the reporter calls the units a "Murao" -- the Atlantic
wall-mounted split, sold in multi-split sets, which is what nine indoor units
on one gateway would be.

What the dump shows is the same capability id set on 1734, 1735, 1736 and
1737, id for id -- 77 of them, the climate ids, both program blocks, the fan
and louver ids 100801/100803, the eco flag 100507 -- and 557 differs from
them only by four more : 341, 347, 348 and 100100. The values read as an air conditioner
too : 100022 is 415 on all of them, the same bitmask the 557-561 units carry
for {off, auto, cool, heat, fan_only, dry} ; 1736 was captured cooling, with
7 and 181 both at 3 and its cooling setpoint at 16.0 ; and every fan and
louver value falls inside the vocabularies `model.py` declares.

So the branch condition widens from `modelId == 1734` to `1734 <= modelId <=
1737` and nothing else changes : the same flags 1734 had, the same
`(#n)` fallback name counted from 1734 -- which almost nobody sees, since a
hub child always carries a zone name and that is what the entity is called.

Limits. The range stops at 1737 because that is where this household stops ;
a tenth room would arrive unmapped and ask for its own report, which is the
right failure -- the ids are not known to be per-slot the way the THZONE ones
are. The eco gate that 557-561 carry (`ecoModeAvailable = False`) now covers
1734-1737 too. It was held back here for want of a statement about what the
app shows, since reading 100507 at 0 on every one of them says nothing about
whether the app exposes it. The statement came from the same household, which
owns both ranges : no eco mode appears on any of its rooms. Two other things
agree with it -- the two ranges declare identical feature bitfields (100002
`ventilation_options_supported` 111, 100021 `ventilation_controls_supported`
201, 100004 `ventilation_controls_available` 197), so they are one class as
far as the vendor is concerned ; and the app has no availability data for the
eco mode at all, where every neighbouring feature has an Available/Supported
pair -- `IVentilationFeature` declares `isSavingEnergyModeEnabled()` alone,
and neither `VentilationOption` nor `VentilationControls` names an energy
member. So this is not derivable from a capability, and the flag stays.

An eco switch disappears from an install that has 1734-1737. It wrote to a
capability the vendor's own app does not offer, which is the reason to take
the removal rather than keep a control that looks like it does something. The `(#n)` numbering was left alone rather than
made to read `#6` for 1734 : it would rename an existing model's fallback on
the strength of one household's slot order.

### Thirty-eight boilers named from the vendor's catalogue, and nothing else claimed

`GET /magellan/productmodels/models/{modelId}` answers for any model id, not
only the ones an account owns (`docs/api-surface.md`). It gives the vendor's
`longName`, a `commercialReference`, and a `productId`. That is `model.py`'s
first column, published -- and it is where ids 1-12, 54 and 55 come from.

They are the Naema and Naia, both generations, filling in around the three
ids (56, 61, 65) that were already mapped from real reports. All of them
report `productId` 1, which the Android app's own `ProductType` table calls
`PASS_APC_BOILER` -- and every one of the seventeen ids in that family this
table already knew is mapped `GAZ_BOILER`, with no exception. Seventeen
independent agreements is what the inference rests on.

What they declare is deliberately the minimum: the name, the type, and the
off/heat pair. No flag. There is no capture for any of them, and the three
boilers mapped from real reports declare exactly this and nothing more, so
copying that shape claims no more than the evidence does. The fall-through
already gave these ids `{off, heat}`, so nothing a device *does* changes --
what changes is the name (`Unknown product (1)` becomes `Naema Micro 30`), the
type, and the repair that used to ask a reporter for a dump the catalogue
already answers.

They share one branch and a name table rather than one `elif` each, because
the body is identical and only the commercial name differs. Two names repeat
across ids (257/260, 258/261); they are distinct models in the vendor's
catalogue and stay distinct here.

**The other ~165 ids sharing `productId` 1 are deliberately left unmapped.**
They are Guillot collective boilers -- VARMAX, VARBLOK, VARFREE, CONDENSINOX
-- a product class nobody has ever reported running through this integration.
The argument that makes the Naema safe (a family with seventeen confirmed
members) does not reach them, and mapping a model is what *stops* the
unknown-model repair asking its owner for a dump. Naming a line we have never
seen would trade away the only signal that would tell us it exists.

Limits. The catalogue gives a name; it says nothing about capabilities, modes
or flags. A boiler here that turns out to need a flag will need a dump like
any other. **The nine Alfea heat pumps the same sweep returned (25, 29, 32,
34-39) were deliberately left out**: `CozytouchDeviceType.HEAT_PUMP` wires
`currentTemperatureAvailableZ1` / `Z2`, `HeatingModes` and
`exhaustTemperatureAvailable`, and every mapped heat pump got those from a
capture. Naming them would mean guessing which zones they report, which is
the one thing this table must not do.

The sweep itself stopped at model id 56 when this was written
(`research/fetch_model_catalogue.py` is resumable); it has since been finished,
and what that changed is the entry below.

### The whole catalogue ships, as a name and nothing more

`research/fetch_model_catalogue.py` finished the sweep the boilers entry above
started : 1759 rows, every id `GET /magellan/productmodels/models/{id}` answers
for, up to 2450. `model_catalogue.py` is that table, verbatim, minus the 101
rows whose name is a firmware slot rather than a product -- `BD1 DEFAULT`,
`ROOM_0`, `UI_3`, the `GENERATOR_n` nodes. 1583 names, of which 1526 belong to
ids this table has no branch for.

It is read in one place, the fall-through at the end of `get_model_infos`, and
it sets the name and nothing else. The type stays `UNKNOWN`, the modes stay the
off/heat pair the fall-through always gave, and `get_unmapped_models` keys on
the type -- so every repair that asked its owner for a dump still asks. What
changes is that the dialog is about "Alfea Extensa A.I. 3 R32" instead of
"Unknown product (207)", which is the difference between a reporter recognising
their hardware and not.

This is the opposite trade from the boilers above, and deliberately so. Mapping
a model *silences* the repair, which is why only 38 of these 1583 were mapped :
naming one in the fall-through costs nothing, because the signal that the model
exists is untouched. The names are kept in the vendor's own spelling, capitals
and all -- `BILBAO 4 H 0750W BLC` reads oddly in Home Assistant, but inventing
a prettier form for 1526 products nobody here has seen would be a guess per
product.

Limits. A name is all it is : no capabilities, no modes, no flags, and no type.
`productId` was dropped from the shipped table -- it groups the catalogue into
families (1 boilers, 2 heat pumps, 47/62 water heaters, 53/64 radiators) and
that grouping is exactly the inference the boilers entry argues has to be
earned family by family, not read off a column.

### Seven names the vendor spells differently

The same sweep is checkable against the branches, and it contradicts seven of
them on a point of fact rather than of style :

| id | was | now | what the catalogue says |
| -: | --- | --- | --- |
| 418 | Atlantic Loria Duo 6006 | Loria 3 Duo R32 | 416-425 is a contiguous Loria R32 block; 418 is `LORIA 3 DUO R32`, and the Loria Duo 4/6-8 are ids 575-578 |
| 1543, 1546, 1547, 1551 | Asama Connecté II **Ventilo** … | Asama Connecté II … | the catalogue enumerates the whole line as wattage × colour (1540-1555) with no Ventilo variant, and these four land on a cell each |
| 1622 | Thermor Riva 5 | Riva 5 étroit 1300W BLC | `RIVA 5 ETROIT 1300W BLC BRI`; the plain Riva 5 is 1559-1561 |
| 2374 | Explorer EVO 3 (260L) | Explorer EVO 3 (270L) | `AE CV5 DACH FS 270L PE COIL (DE)` |

The forty-odd other disagreements are left alone : they are the branches
spelling a readable name where the catalogue has an internal reference
(`Calypso 200L` against `TD 200 VS AT 1200M TYB V5S`) or a slot placeholder
(`Naviclim Hub` against `CLIF Default`), and the readable one is the point.
Nothing here touches a type, a mode or a flag -- the seven are names on
hardware nobody here owns, and the evidence is a name.

### A room slot is whatever its gateway drives, not an air conditioner (issue #172)

`557-561` was read as "air conditioner room unit" from the accounts that had
one. It is not a product: it is the *room's index* behind a gateway. Issue
gduteil/cozytouch#172 (September 2026) is the same five ids reporting Sauter
connected radiators, and the two are indistinguishable device-side:

| | Navizone account (Mathieu, 28/08) | CozyBox account (issue #172) |
| - | - | - |
| `modelId` / `productId` | 557-559 / 26-28 | 557-560 / 26-29 |
| `longName` | `ROOM_0`… | `ROOM_0`… |
| `modelFamily`, `productRange` | null | null |
| gateway | 1758, `Air_Conditioning` | 2447, `Connectivity_Box` |

So the gateway is the only thing that differs, and `get_model_infos` gains a
fourth input for it. Resolving it needs the account's whole device list
(`masterDeviceId` is an id, not a model), which is why every caller now goes
through `get_device_model_infos(devices, dev, zoneName)` instead of calling
the table with a bare model id -- a caller that passed the id alone got the
wrong answer silently, and there were seven of them.

The radiators get `CozytouchDeviceType.RADIATOR`, a member added next to
`TOWEL_RACK` rather than reusing it: the API's own `ProductMainFamily` splits
`Radiator` from `Towel_Dryer` (`research/data/model_families.txt`), and the
reporter's first complaint after "it is not an air conditioner" would have
been "it is not a towel rail". The wiring is the towel rail's, via
`ELECTRIC_HEATERS` in `capability.py`; the one id where they part is 100506,
which stays dropped for towel dryers only -- no capture has one reporting it,
and the room radiators both report it and are sold on presence detection.

Limits, and they are real.

*The gateway is a proxy, not the answer.* Sauter sells the CozyBox for
radiators **and** heat pumps, so "behind a 2447" does not mean "radiator" in
general -- it means "not an air conditioner", which is the half that fixes
this report. A CozyBox driving a reversible heat pump would be named wrong
here. It stays this way because the alternative is worse: nothing the child
reports separates the two. The corpus was checked id by id --

- 100022 (`supportedSystemOperatingMode`, the HVAC-mode bitmask) reads 415 on
  the radiators and 415 on the 1734-1737 air conditioners. Useless.
- 166 reads 17 = {off, heat} on the radiators, but it is the *currently
  permitted* mask: the same Navizone air conditioners read 9 = {off, cool}
  under a summer lock and 411 elsewhere. An air conditioner under a winter
  lock would read 17 too.
- presence of 100800/100802/100804 (fan, quiet, louver) does not split them
  either: the radiators report all three and the Navizone units report none.

*One account.* Four rooms behind one CozyBox is the whole of the evidence,
and the commands were never tested -- the reporter said as much.

### A zone of a ducted heat pump is matched on its name, not its model id

The API reports the zones of a ducted heat pump as devices of their own. The
ids look like they encode the zone's index rather than a product: one capture
pairs 1505 with `THZONE_0`, 1506 with `THZONE_1`, and so on up. A range
guessed from one household is therefore a range a bigger installation walks
off the end of, which is why the branch matches the `THZONE` prefix on the
device's name instead. It reads the API's own `name` field and not
`customName` -- renaming a zone in the Cozytouch app is a thing people do, and
this has to survive it.

What a zone reports, in that one capture, is two capabilities -- 218 reading
`"0"` and 100014 reading `"255"` -- and no climate capability at all: no
setpoint, nothing to drive. So the branch claims a name, the `ZONE` type, and
an empty `HVACModes`. That last one is the point of mapping it: the
fall-through at the end of `get_model_infos` hands every unmapped model an
`{off, heat}` pair, and that is what made a zone read as a thermostat that
could heat.

The rest is silence. Unmapped, six zones arrived as `Unknown product (1505)`
*and* raised an unmapped-model repair each -- six dialogs asking for a
diagnostics dump about hardware working as designed. `Hub.get_diagnostics`
drops zones from the dump for the same reason. Reported upstream as
gduteil/cozytouch#167.

### The Alfea Extensa S is two devices, and its slots are not products (issue #93)

One household (issue #93, September 2026) runs an Alfea Extensa S Duo, and it
arrives as five devices : 2303 and 2327, both unmapped and both named
`Alfea Extensa S Duo`, plus three slots with ids the table already knew.

The catalogue's `productId` is what separates the two halves, because it names
the slot rather than the product. 2303 carries `productId` 54, the one
`CESA V2 DEFAULT` (1387) sits on -- the connected interface board. 2327 carries
58, shared with `GENERATOR_0` (1391) and `GENERATOR_HEAT_PUMP_0` (1432) -- the
generator. What each reports agrees: 2303 has the whole-appliance readings
(consumption, outside temperature, away mode, error code, serial number) and
2327 the hydraulics (pump hours and starts for heating and hot water, water
pressure, flow and discharge temperature). Neither carries a room setpoint.

The split runs through the catalogue cleanly. Of the 26 Alfea Extensa S ids,
2295-2317 are `productId` 54 and each has its own commercial reference
(024281, 024420 and so on) ; 2326-2328 are `productId` 58 with no reference at
all, three of them, one per range -- S, S Duo, S Duo XL. So the two branches
match contiguous ranges and take their name from `MODEL_CATALOGUE`, which
already held all 26 and is the only place the vendor's spelling should live.

Neither half gets a climate entity. `HVACModesCapabilityId` is empty on both,
which is the point of mapping them at all : the interface reports capability 8,
the default would have read it as an HVAC mode, and its value is `3000` --
neither 0 nor 4, so the entity had no mode it could show. The heating and hot
water controls are on the slots below, and what capability 8 does mean is still
open (asked on issue #93).

Mapping them changes nothing else. Run through `get_capability_infos` with the
capability ids the dump reports, both halves produce the same entity list typed
`HEAT_PUMP` as they did typed `UNKNOWN` -- 22 on the interface once the broken
climate goes, 8 on the generator. What mapping buys is the repair no longer
firing and the name no longer coming from the fall-through.

### 1376 and 1388 were never a Calypso or a Doris

Two of the slots under that appliance were mapped to products they are not.
The catalogue calls 1376 `DHW_0 DEFAULT` and 1388 `TESC_0 DEFAULT`, both with
an empty commercial reference, which is how it writes a firmware slot ; the
Calypso SPLIT VS 270L is 1369 and the Doris range starts at 1556. Every
capture in `research/capability-corpus/devices.tsv` that carries either id
shows it as `DHW_0` or `TESC_0` and never as a product. They were guesses, and
the sensors they produce -- a hot water tank on 1376, a setpoint and a water
temperature on 1388 -- are what a slot of that name would report.

So both are renamed by role. 1376 keeps the `WATER_HEATER` type and its 31
entities and becomes `Domestic hot water`; nothing about it changes but the
name. 1388 joins 1389 and 1390, the `TESC_1` and `TESC_2` the catalogue lists
beside it, as `Heating circuit (<zone>)` -- named after the zone the way a room
slot is, since the id carries nothing but an index. Its type becomes `ZONE`,
which is the type this repository already has for a circuit that is not a
product, and the snapshot shows it landing on the digest `THZONE_0` has. The
only entity that moves with it is 218, which `ZONE` drops and which is off by
default anyway.

Renaming a device is not free -- the towel rack table says so, and keeps eight
names it would otherwise spell better. The line is that those are spellings of
the right product and these were the wrong product. An owner of an Alfea saw a
Doris in their device list.

### A room slot behind an Alfea is a heating circuit (issue #93)

Model 557 in that household is `ROOM_0` behind the heat pump's interface, and
it arrived as `Air Conditioner (Circuit 1)` for a floor heating circuit. It
reports a cooling setpoint (177), cooling limits (162, 163) and a full cooling
program, so the dump alone could not say whether the firmware is heating-only.
The reporter's screenshots of the app answer it:

- The zone's mode dialog offers **ON / OFF / AUTO** and nothing else -- the
  app's own words are frost protection (Off), heating (On), or heating driven
  by the outside temperature (Auto). No cooling mode, no cooling setpoint.
- The appliance can do floor cooling. The reporter's does not have the part
  installed for it.
- There is no mode for the heat pump itself, only for the circuit and for the
  hot water, which is the other half of why neither 2303 nor 2327 gets a
  climate entity.

So a third master joins the branch, with its own name and its own table :
`ROOM_n` behind an `ALFEA_EXTENSA_S_INTERFACES` id is `Heating circuit
(<zone>)`, typed `THERMOSTAT` -- what it is, a room control for a circuit --
with modes `{0 off, 1 auto, 4 heat}`. Run against the dump's capability ids
the entity list does not move: the same 57, with capability 7 renamed from
`air_conditioner` to `heat` and the device renamed with it. What changes is
the four modes the entity offered and the appliance cannot reach.

The modes are the app's, and capability 166 agrees exactly -- it reads **21**
on this unit, bits off, auto and heat. It is not the table's source, because
166 is the *currently permitted* mask and moves with the season (see the
entry above), but it is what a second Alfea would be read against.

**Cooling is left out of the table on purpose, and that is the ceiling here.**
100022 reads 29 on this unit, which sets the cool bit: the appliance line
supports cooling and this one cannot reach it. Nothing in the dump separates
"has the kit" from "has not", so an owner with the cooling kit gets a heating
circuit that does not offer cooling, and a report saying so is what would
settle it. The two tiles the app draws for this household -- Circuit 1 and
the hot water -- are what the mapping now produces.

### The Alfea Excellia S is the Extensa S with its generator as a slot

Issue gduteil/cozytouch#173 reports an Alfea Excellia S with two heating
circuits, and the dump is the Extensa S of issue #93 with two of its five
devices numbered differently:

| device | slot | modelId | mapped as |
| ------ | ---- | ------: | --------- |
| interface | `CESA V2` | 1691 | `ALFEA EXCELLIA S`, `HEAT_PUMP` |
| generator | `GENERATOR_0` | 1391 | `Generator`, `HEAT_PUMP` |
| circuit 1 | `TESC_0` | 1388 | `Heating circuit (Circuit 1)`, `ZONE` |
| circuit 2 | `TESC_1` | 1389 | `Heating circuit (Circuit 2)`, `ZONE` |
| room | `ROOM_0` | 557 | `Heating circuit (Chambres)`, `THERMOSTAT` |

Two things follow. The interface ids, 1691 and 1692 (`ALFEA EXCELLIA S TRI`),
are catalogue products like the Extensa S ones and join that branch, so
`ALFEA_S_INTERFACES` is what the room slot is now read against -- a `ROOM_n`
behind either line is a heating circuit, with the same OFF / AUTO / HEAT the
app offers. Capability 166 reads **21** on this unit as it did on the Extensa
S, which is that table exactly, and 100022 reads **29** again: the line does
cooling, this installation does not have the kit.

The generator is the difference. The Extensa S reports it as a catalogue id
(2326-2328) and the Excellia S as `GENERATOR_0`, slot 1391, which the
catalogue does not carry -- so it cannot be named off `MODEL_CATALOGUE` the
way that branch does, and gets the literal name `Generator`. One slot, not a
range: 1388-1390 are three because the catalogue lists `TESC_0` to `TESC_2`,
and nothing says how many generators a slot block allows.

**What is left open is capability 109.** The reporter reads it as an ambient
temperature on the two circuit slots -- 23.07 and 22.01 against a room at
22.69 -- where the table names it `boiler_water_temperature`, and asks for the
gate 116 has. The dump was taken in September with the heating off, when a
circuit's water and the room it heats read the same, so it does not separate
the two readings. The table is left alone until a winter dump says which it
is; a reading of 45 on a circuit would settle it in one line.

### The two app tiles are five devices, and one of them is a pair

Worth writing down, because it reads as a bug. The app draws two tiles and the
API reports five devices, split by zone:

| device | zone | zoneType |
| ------ | ---- | -------- |
| 2303 interface, 2327 generator, 1376 `DHW_0` | `zoneTechnique` | 2 |
| 1388 `TESC_0` | Circuit 1 | 29 |
| 557 `ROOM_0` | Circuit 1 | 1 |

`TESC_0` carries the tag `iothubChildrenIds: ROOM_0`, so the circuit slot and
the room slot are two halves of one tile. `TESC_0` is typed `ZONE`, which is
not offered when adding devices, so what an owner picks from is the room slot
and the hot water -- the two tiles -- plus the two technical halves the app
keeps in its settings.

## What classifies a device is `productId`, not the model id

Every branch in `model.py` that tests a model id range against the device tree
-- `557 <= modelId <= 561`, `1734-1737`, `TESC_SLOTS`, `GENERATOR_SLOT`, the
two `ALFEA_*_INTERFACES` -- is a reconstruction of a field the API already
sends and `account.py` already stores. The Android app reads that field and
nothing else.

`GacomaDeviceFactory.createDevice` (decompiled, in `research/`) takes the
device's `productId`, maps it to a `ProductType`, does the same for the parent
named by `masterDeviceId`, and picks a class from the *pair* :

    (ROOM, CESA_V2_MAIN_COMPONENT)     -> CesaV2Room
    (ROOM, AIR_CONDITIONER)            -> AirConditionerRoom
    (ROOM, ZONI_CLIM_HUB | NAVI_HUB)   -> TransverseRoom
    (ROOM, SPLIT_3S_HUB)               -> Split3SRoom
    (DHW,  CESA_V2_MAIN_COMPONENT)     -> CesaV2DHW
    (DHW,  no parent at all)           -> CethiV5

So the question a room slot poses is not what kind of link `masterDeviceId` is.
It is what the parent's `ProductType` is, and the pair answers.

`ProductType` is an enum of about twenty members, each holding the `productId`
values it covers. The ones this integration meets :

| ProductType | productId |
| ----------- | --------- |
| `ROOM` | 26-30 and 97-111 |
| `AIR_CONDITIONER_UI` | 31-40 |
| `TH_ZONE` | 65-94 |
| `CESA_V2_MAIN_COMPONENT` | 54 |
| `CESA_V2_GENERATOR` | 58-61 |
| `DHW` | 47, 62 |
| `AIR_CONDITIONER` | 25 |
| `NAVI_HUB`, `ZONI_CLIM_HUB`, `SPLIT_3S_HUB`, `S_HUB` | 63, 96, 95, 98 |
| `DISCOVER_MASTER` | 6, 44, 112, 113 |
| `HDG2`, `DARWIN_BOILER`, `TD1`, `BD0`, `HE3Z` | 7, 4, 53, 41, 64 |

The Navizone capture in `research/capability-corpus/local/` shows the field
arriving per device, beside two more the setup view sends : 1758 is
`productId` 96 with `modelFamily` `Air_Conditioning`, its rooms are 26, 27, 28,
and its zones 65, 66, 67. `API_DECLARED_FIELDS` in `account.py` already keeps
`longName`, `modelFamily` and `productRange` -- the comment above it says
"carried to the diagnostics dump, read by nothing", and that is exactly what
happened. `productId` is not even in the list.

What the ranges settle, read against what the branches say today : `ROOM` runs
to `productId` 111, which is `ROOM_19`, where the branches stop at `ROOM_8` ;
`TH_ZONE` is a `productId` range, not the name test `get_model_infos` does ;
and `CESA_V2_MAIN_COMPONENT` / `CESA_V2_GENERATOR` are one fact each, where the
table carries `ALFEA_EXTENSA_S_INTERFACES`, `ALFEA_EXCELLIA_S_INTERFACES`,
`ALFEA_EXTENSA_S_GENERATORS` and `GENERATOR_SLOT` to say the same thing in two
encodings.

What it does not settle. The modes, the flags and the commercial name stay
ours : `ProductType` says what part a device is, never what it can do, and the
app's own classes carry the behaviour. Two `productId` values this
integration maps have no `ProductType` at all : 55-57, the `TESC` heating
circuits, and 0, which the CozyBox carries -- `fromProductId` falls through to
`UNKNOWN` and the app builds a `GacomaUnknownDevice`, so the app classifies
less than the table does, and the table's answer for those two is not a
reconstruction of anything. `longName` is not a substitute -- the
capture has it as `---` on the three zone devices, so `productId` is the field
to read. What a live CozyBox account sends is
unknown until somebody dumps one, so the id set that names it stays.

### The fall-through derives, and the table stays the override layer

`derive()` in `model.py` is that reading turned on, in the one place it cannot
regress anything : the `else` at the end of `get_model_infos`, reached only by
a model id no branch names. A mapped id is answered by its branch exactly as
before, whatever the device declares, which is what keeps the deliberate
suppressions -- `ecoModeAvailable` False on 557-561 among them -- out of reach
of a number on the wire. `tests/test_derivation.py` pins that order first.

It reads three things, in that order : the `productId` against the ranges
above, the parent's `productId` where the first said `ROOM`, and `modelFamily`
where Atlantic assigned no `productId` at all. A room whose parent is not on
the account stays UNKNOWN rather than being guessed at, since guessing is what
handed every unmapped room to the air conditioner branch.

`modelFamily` is an enum of the vendor's own, `ModelFamily.java`, and its
thirteen members are the other axis: `productId` says which part of an
appliance a device is, `modelFamily` says what it heats or cools. All thirteen
are in the table except `Heat_Interface_Unit` and `Double_Flow_Ventilation`,
which nothing here is. The order between the two signals is not arbitrary --
the Navizone sends `Air_Conditioning`, the installation it fronts, and is a
hub; reading the family first would turn every gateway into a climate entity.

Measured over the catalogue: 234 model ids typed before, 1184 after -- 360
towel racks, 183 heat pumps, 165 boilers, 99 thermostats, 96 water heaters.
The five mode tables the mapped ids use are the five this lookup returns, so
the modes come with the type rather than needing a branch of their own.

It names the device too. `hub.py` registers a device under `modelInfos.name`,
so hardware the catalogue does not list read as `Unknown product (1234)` in
Home Assistant -- for a working appliance. A derived room is now named the way
a mapped one is, from the zone the account gives it and otherwise from the
vendor's own index (`productId` 101 is `ROOM_9`), and anything else falls back
to the `longName` the setup view sends, then `customName`. `longName` comes
first because the vendor sends `---` in it for zone devices, which is read as
nothing.

The dump follows: `isMapped` now reports what the *table* names, not what the
device declares, because a dump is read to find what the table does not have.
The repair goes quiet for a derived device, which is the point -- it existed
because the classification was keyed on the wrong field.

### The device answers first, and twenty-seven ids correct it

The derivation started as the fall-through and is now the whole of it. Every
branch is gone : `model.py` holds one `elif`, for the zone recognised by its
name, and what is left is data.

    model_product_ids.py   168 runs, modelId -> productId, generated
    PRODUCT_TYPES          the vendor's ranges, from ProductType.java
    DERIVED_TYPES          what each of those is, and the modes that go with it
    OVERRIDES              27 ids the device gets wrong or cannot say
    MODEL_NAMES            6 names the catalogue does not carry

627 lines deleted, 227 added. The 27 were not chosen : each is the measured
difference between what the branch answered and what the device declares, so
the set is the honest size of what this project knew that the API does not
say. Four shapes account for all of them -- ids the vendor assigns no
productId (the Naema 3s, the TESC circuits, the CozyBox badges), the two Alfea
3s whose modes sit on capabilities 1 and 2, the LINEO volumes with no prog
mode, and the Naviclim box, which the catalogue calls an air conditioner
because it drives one.

Equivalence was checked id by id against the branches, not by the snapshots
alone : of the 234 models the table mapped, **every one answers identically**
apart from the name. 950 that answered UNKNOWN now answer.

Two things the branches did that the data does now. A room behind a CozyBox is
a radiator because the box sends `modelFamily` `Connectivity_Box` (issue
#172), not because four badges are listed here -- a fifth needs no code. And
`productId` 0 is read as absent rather than as a value, since that is what the
vendor leaves on a model it assigns no type.

The names were the one deliberate loss. 91 models took the catalogue's string
in place of one written here, which is louder -- `ASAMA CONNECTE II 0500W BLC`
for `Asama Connecté II 500W BLC` -- and more precise: three Aeromax SPLIT 3
volumes shared one name here where the catalogue names each. A device rename
changes what Home Assistant displays and nothing else; the unique ids are
keyed on the capability id.

### A room is a room, and the CozyBox stops being a special case

`557-561` was answered as a radiator behind a CozyBox and an air conditioner
behind anything else, from the one account that had each. Nothing a slot
reports separates them, and this was measured three ways: 100022 reads 415 on
both, the ventilation ids 100800/100802/100804 are reported by the radiators
and not by a Navizone's air conditioners, and 153 -- the heating element -- is
reported by both. A cooling setpoint does not split them either: every 557 in
the corpus reports 177.

The vendor's own client does not try. `GacomaDeviceFactory` builds one
`TransverseRoom` for every room behind a gateway, whatever it drives, and that
class is a superset of the air conditioner one -- same ventilation and
temperature features, plus air mixing, hot water, prog assistant and settings.
The capabilities decide what the screen offers.

So `CozytouchDeviceType.ROOM` is one type for the lot, `capability.py` gains a
room branch that is the union of the two it replaces with every id asked for
rather than assumed, and the entity reads `room` where it read `heat` or
`air_conditioner`. The Alfea interface stays the exception: its slots are
heating circuits and its `productId` says so.

What this buys is not tidiness. The CozyBox sends `productId` 63, the same as
the HUB Cozytouch above it and the same `Connectivity_Box` family, so taking
its product id would have turned issue #172's radiators back into air
conditioners -- the box was unusable as data for exactly as long as it decided
something. It decides nothing now, so 2447-2450 are read like any other
gateway and their overrides are gone.

The weekly program capabilities lose their per-type names at the same time.
196-209 were `prog_01_z1` to `prog_14_z2` by default and `prog_heating_monday`
to `prog_cooling_sunday` on an air conditioner; the vendor's app calls the two
blocks Heating and Cooling, so the second naming is simply the true one and is
now everyone's. A radiator never shows the cooling week -- no capture has one
reporting 203-209.

The device name follows: `Radiator (Chambre)` and `Air Conditioner (Chambre)`
both become `Room (Chambre)`. A rename changes what Home Assistant displays
and nothing else, since the unique ids are keyed on the capability id.

### The dump carries every device, the config flow still chooses (issue #110)

A zone was left out of both the dump and the device list on one argument: a
dump is read to find hardware that has to be mapped, and a zone is not
hardware -- it reports two ids that resolve to nothing, one of them declined
on purpose, which reads exactly like work to do.

That was right about a zone of a ducted heat pump and wrong about everything
else typed the same way. The `TESC` heating circuits of an Alfea are typed
`ZONE` too, and one of them reports a setpoint (19) and the temperature of its
own circuit (109) -- a device with something to say. Issue #110 is a household
with two circuits where only one has a room slot beside it: the other was
invisible in the device list, invisible in the dump, and therefore invisible
in the report they were asked to send, so nobody could find out what it was.

So the dump lists every device the account has. It creates no entity and costs
nothing; what it buys is that a device nobody can explain can at least be
looked at. The config flow keeps its own filter, which is a different
question -- adding a zone still makes a device with an empty page behind it.

### A circuit that holds its own setpoint is a device (issue #110)

The dump above answered the question it was written to make askable. The two
hidden devices are `TESC` slots, 1388 and 1389, and the account has one of
each kind : 1388 shares its circuit with a room slot, 1389 is alone.

Capability 106000 tells them apart, and so does the setpoint :

| circuit | a room slot for it | 106000 | setpoint |
| ------- | ------------------ | ------ | -------- |
| issue #110, `Chambres` | yes | 1 | 0.0 |
| issue #110, `Pièces de vie` | no | 0 | 20.0 |
| issue #93, `Circuit 1` | yes | 1 | 0.0 |
| gduteil i63, c88, c125 | yes | 1 | — |
| gduteil i142 | no | 0 | — |

Seven circuits over five accounts, no counter-example, and two signals that
agree without being the same signal: a circuit reads 0 for its own setpoint
exactly when something else holds it. So 106000 is named
`circuit_driven_by_room`, and a `TESC` reading 0 there is retyped from `ZONE`
to `THERMOSTAT` -- which is to say, offered as a device, since the config flow
filters on `ZONE` and nothing else.

The name is ours. The vendor's app has no capability 106000 in its enum and no
`ProductType` covering 55-57 at all, so it neither confirms nor contradicts
this; it builds an unknown device for these circuits and never polls them. The
row is `DIAG` and off by default for that reason: it is read to decide what
the device *is*, and it is nobody's control.

What the circuit gets is two readings -- its setpoint and the temperature of
its own water -- and no climate entity, since it reports no mode capability.
Read-only: capability 19 is typed as a temperature, and nothing shows it can
be written.

A device with no capabilities yet stays `ZONE`. That is the state between
setup and the first poll, and a device offered on the strength of nothing is
worse than one offered a poll later.

## `custom_components/cozytouch/climate.py`

### The mode list is the model's table, narrowed by what the unit reports

A model's `HVACModes` is the product *line*'s table, and two units off one
line differ : the Alfea Extensa S of issue #93 is sold with a cooling kit and
without, under the same model id. So `narrowed_modes()` intersects the
table with capability 100022, `supportedSystemOperatingMode`, before the
entity declares its modes.

The masks come from `HVAC_MODE_MASKS` in `capability_table.py`, derived from
the two tables already there (`_SERVICE_VALUES` maps a mode value to a name,
`_HVAC_MODE_BITS` a name to a mask) rather than written out a third time.
`auto` owns two bits, 1 and 2, which is why the test matches the vendor app's
`mask & value != 0` and not `== mask` -- 411 and 415 are the same set of
modes.

Three things it deliberately does not do.

*It reads 100022, not 166.* 166 is the same space and the same encoding, and
it is what the app actually greys by -- on the issue #93 unit it reads 21
where 100022 reads 29, and 21 is exactly the ON / OFF / AUTO the app draws.
But 166 is the *currently permitted* mask and moves with the season : a
Navizone air conditioner reads 9 = {off, cool} under a summer lock. The mode
list is built once in `__init__`, so narrowing by 166 would make `heat`
disappear from Home Assistant in July and take every automation naming it
with it. Following 166 is possible, but it means recomputing the list on each
poll and living with a mode list that moves -- a bigger change than this one,
and one nobody has asked for.

*It only removes.* A mode the model table does not declare is never added,
whatever the mask says.

The bit table is the vendor app's, and bit 7 is the one measured against real
hardware. `hub-navizone-2026-08.json` -- three room air conditioners behind a
Navizone -- reads `100022 = 285`, the only reading in the corpus with bit 7
clear where every other 557-561 reads 411 or 415. Their owner's app offers
five modes: arret general, chauffage, froid, auto, deshumidification. Five,
and no fan. So the narrowing removes exactly the sixth mode the entity was
offering and the hardware cannot do.

What the app does have is **brassage**, and it is a separate option rather
than a mode -- capabilities 102004 / 102021, household-wide across the three
rooms. Reading it as `HVACMode.FAN_ONLY` is what the model table was doing,
and it is the wrong control in the wrong place: a mode the unit switches to,
where the app has an option it leaves running underneath whatever mode is
selected.

*It never empties the list.* A mask of 0 -- which is also what
`get_capability_value` answers by default for a device that does not report
the capability -- or a mask that matches nothing leaves the table alone. A
climate entity with no mode at all is broken in Home Assistant, which is
worse than one offering a mode that does nothing. A mode value no bit names
(5 emergency heat, 6 pre-cooling, 9 sleep) is kept for the same reason.

## `custom_components/cozytouch/select.py`

### The air-circulation duration is a select on the device's own grid

Capability 102021 was a free number bounded 15-300, and the vendor app never
offers it that way: its picker (seen 2026-08-29 on a room AC) runs 00:15,
00:30, 00:45 … 05:00 -- every quarter hour and nothing between, 16 or 17
minutes not enterable. The grid is not the app's invention either: the
device itself declares it, 102025 the minimum (15), 102026 the maximum
(300), 102022 the step (15), which the corpus reads on every model that
reports the duration at all (557-559).

A number entity cannot promise that grid -- Home Assistant validates a
typed value against the bounds but not against the step -- so a value the
hardware would refuse (or worse, silently round) was one keystroke away.
`CozytouchDurationSelect` builds its options from the three grid
capabilities read live, falling back to the mapping's constants for a
device that reports the duration without its grid, and shows them the way
the app does (`HH:MM`). A reported value off the grid reads as unknown
rather than snapping to a neighbour, since a snap would misreport what the
device said. The grid capabilities stay exposed as diag entities, disabled
by default (see the entry that hid them).

The entity moves platform (number → select), so its unique_id changes and
an existing install keeps an orphan number entity to delete by hand --
same trade as every promotion, taken for the same reason: the old shape
accepted writes the hardware never did.

## What a catalogue name is worth as evidence

### `# catalogue only`, and why two thirds of the table carries it

`GET /magellan/productmodels/models/{id}` names roughly 1500 model ids, and
`model_catalogue.py` is that scrape. It was added so an unmapped device would
read as its own product rather than `Unknown product (1234)`, and it decided
nothing else -- an id in it and nowhere else stayed typed UNKNOWN.

Reading it a second way turned out to be worth more. A product line in that
catalogue is a grid the vendor fills in one figure at a time: a volume, a
coil, a finish, a brand badge, a country. `RIVA 5 ETROIT 0300W CARBONE` sits
beside the `RIVA 5 ETROIT 1300W BLC` somebody captured; `TD 200 VS ATE 1200M
TYB V5S SERP` is the tank of `TD 200 VS ATE 1200M TYB V5S` with a coil in it.
Where the rest of a line was captured, the empty cells are the same appliance,
and the branch body those captures produced is the answer for all of them.

That is how 131 of the 203 mapped ids got here. Each is marked
`# catalogue only` in `model.py`, or sits in a table whose own comment says
the whole body is catalogue-sourced.

**What the marker promises, and what it does not.** A catalogue name is
evidence of identity, never of behaviour. So a marked id may claim exactly
what its captured sibling claims -- the name, the type and the modes -- and a
test asserts that field by field. It may not carry a flag of its own, because
a flag is a statement about what hardware does and nothing here has watched
this hardware do anything. Two cases where that line was drawn against the
temptation: the Lineo volumes inherit 1957's heating modes with `prog`
missing rather than the generic three, and `LORIA 3 DUO 2C R32` was left
unmapped because `2C` is a second circuit and its sibling declares
`currentTemperatureAvailableZ2 = False`.

**What it costs.** Mapping a model is what stops the unmapped-model repair
asking its owner for a diagnostics dump. Every id taken this way is a dump
that will now never arrive. That trade is worth making for a finish or a
badge, where the guess is nearly free and the alternative is a dialog
nagging somebody about a radiator that works; it is not worth making across a
generation or a power rating, which is why the `Alfea Extensa Duo AI UE`
variants and `NAIA 2 micro 25 G20/G25` are still unmapped and a test pins
them that way.

## The capability-only derivation (tried, and dropped)

### `derive.py` existed for one release, and the dump carries its inputs now

The vendor's app is not updated when a model ships, which means it cannot
work the way `model.py` does. Decompiling it (August 2026) showed how it
does work : it has no `modelId` table at all — it displays the `longName` /
`modelFamily` the server sends — and every feature the UI offers is derived
from the capabilities the device reports. `derive.py` was that derivation
rebuilt on our side, printed in the dump as a shadow next to the declared
table (`derived` / `declaredVsDerived` in each device's `model` block).

Nothing ever wired entities from it, because the evidence covers a handful
of device families and the table carries *deliberate* suppressions the
derivation would undo — 557-561 report capability 100507 and the vendor app
still offers no eco mode for them, which is why `ecoModeAvailable` is False
there.

It was removed (August 2026, one release after it landed) rather than kept
as a read-only shadow : a derivation nothing acts on is a second mapping to
maintain, and every conclusion it printed can be recomputed offline from a
dump that carries the raw inputs. So the dump carries exactly those instead
— every capability id with its value, and the API's identity fields
(`customName`, added to `API_DECLARED_FIELDS` for this ; `longName`,
`modelFamily`, `masterDeviceId`, `isAvailable`). A future switch-over would
start from the evidence below and the dumps on the tracker, with the table
kept as the override layer for exactly those suppressions.

The entries below are what the derivation rested on ; they stay because
they document what the capabilities *mean*, which outlives the module that
read them.

### `HVAC_MODE_BITS` : capability 100022 is a bitmask over the mode values

Measured against the corpus of captures : the units that report
`100022 = 411` (bits 0,1,3,4,7,8) are the ones whose `HVACModes` table
reads {0 off, 1 auto, 3 cool, 4 heat, 7 fan_only, 8 dry} — the exact same
set — and the heating-only boilers and heat pumps (1382, 1444) read `17`
(bits 0,4) against their {0 off, 4 heat}. Two independent matches, no
counter-example seen.

166 (`systemOperatingMode`) carries masks in the same space that *shrink*
while 100022 holds steady — one capture reads `166 = 9` {off, cool} on a
unit whose 100022 says {off, cool, heat, dry, auto}, mid-summer, so 166 is
the modes *currently permitted* (a seasonal lock) against 100022's
*supported*. The derivation read only 100022 ; if the vendor app turns out
to grey modes by 166, reflecting that is a climate-entity question, not a
mapping one.

**Bit 2 was the open question and is now answered: it is part of `auto`.**
The vendor's Android app gives its HVAC enum a mask of **6** for `auto` —
bits 1 and 2 — and matches a member when *any* bit of its mask is set. So
411 and 415 are the same set of modes, 285 has no unexplained bit, and
nothing on the wire needs a name it does not have. `_HVAC_MODE_BITS` is
that enum; every value in the capture corpus decodes with no bit left
over.

### What a rename costs here, and what it does not

Every entity's unique id is `f"{DOMAIN}_{subentry_id}_{capabilityId}"` --
keyed on the capability id, never on the name. So renaming one renames what
Home Assistant displays and nothing else : the registry entry, the
entity_id and the recorded history all survive, and an automation naming
the entity_id keeps working.

The wart is that the entity_id keeps the slug it was created from. Somebody
whose sensor was called `flame` in 2026 keeps `sensor.…_flamme` showing
"Chauffe". Renaming entity_ids would fix the cosmetics and break every
automation that names one, which is the trade nobody wants.

**Changing a capability's *type* is a different matter.** The registry is
keyed on the platform as well as the unique id, so an id that moves from
`number` to `sensor` does not reuse its entry : a new one is created and
the old one stays behind, unavailable, forever. Capability 312 did exactly
that, which is what migration 2.3 is for.

### Seventeen names the iOS list got wrong

The mapping's names came from an extraction of the iOS app. The Android
enum (`research/data/capability_id_to_name_android.tsv`) disagrees on
seventeen, and where the two differ the Android one is the enum itself,
read in clear Kotlin, not a string recovered from a compiled binary.

Only the ones that said something *false* were changed; a paraphrase is not
an error, and `dhw_error_code` is a better entity name than
`ERROR_CODE_DHW`.

| id | was | is |
| -- | --- | -- |
| 344 | `linked_interfaces_count` | `ROOM_COUNT` -- a count of rooms |
| 100002, 100024 | `*_estimation_modes` | ventilation options, a `VentilationOption` mask |
| 100004, 100021 | `*_control_modes` | ventilation controls, a `VentilationControls` mask |
| 100196-100198 | `absence_schedule`, `*_target_temperature` | `PROG_ABSENCE` / `NIGHT` / `PRESENCE`, each a JSON `[temperature, offState]` pair and not a scalar |
| 100334-100341 | `new_schedule_*` | `THERMOSTAT_LIFESTYLE_HEATING_*` -- the lifestyle program, nothing new about it |
| 100078 | `identify_supported` | `VENTILATION_WINK_REQUEST`, read by `isWinkRequested` : a request, not a support flag |
| 358 | `air_circulation_scope` | `thermalAmbianceScope` -- nothing to do with air circulation |

358 is the one the Android enum does *not* carry : the app never reads it.
Its name here comes from the iOS list, which is the only source for it, and
which is wrong about every other id on this page at least once.

### Capability 153 has three states, and Atlantic never names it

`HEATING_STATUS`, read as `HeatingStatus { OFF "0", HEAT_UP "1", COOL_DOWN
"2" }`. Two things follow, and the second is the one that mattered.

**It was a binary sensor**, whose `is_on` is `value == "1"`. A device
reporting 2 read as off, silently, and the product that reports 2 is an air
conditioner while it is cooling -- including the room units this
integration is developed against. The corpus holds 23 readings of 153 and
every one is 0, so the captures could not have shown this: they were all
taken outside the cooling season. It becomes a string with `reads_as`, and
`BINARY` and `STRING` are built by the same platform, so nothing has to
migrate.

**The flame and the resistance were ours.** The app labels 153 nowhere --
its eight uses of `HeatingStatus` drive a colour and two booleans, and
there is no `R.string` near any of them. So a boiler saying "flame" and a
towel dryer saying "resistance" was an invention, defensible while the
value was a flag and incoherent once it can say "cooling": a flame that
cools is not a thing. One name for every product, which is what Atlantic
has.

The default was also wrong before that, and wrong in the way CLAUDE.md
warns about: `flame` was the shared default with the electric heaters as
the exception, so it claimed every product nobody had considered -- the air
conditioners included.

**It is off by default (2026-09-25).** On the Navizone rooms (557-559) it
reads 0 on all three and has not changed since 2026-09-07, through the
cooling season, so the entity sat at "off" on every room page while the
units cooled. Where it does move -- the radiators -- what it says already
reaches the climate entity's action, which reads the capability and not the
entity, and is unaffected. Anyone who wants the raw value turns it on.

### Seventeen names the iOS list got wrong

The mapping's names came from an extraction of the iOS app. The Android
enum (`research/data/capability_id_to_name_android.tsv`) disagrees on
seventeen, and where the two differ the Android one is the enum itself,
read in clear Kotlin, not a string recovered from a compiled binary.

Only the ones that said something *false* were changed; a paraphrase is not
an error, and `dhw_error_code` is a better entity name than
`ERROR_CODE_DHW`.

| id | was | is |
| -- | --- | -- |
| 344 | `linked_interfaces_count` | `ROOM_COUNT` -- a count of rooms |
| 100002, 100024 | `*_estimation_modes` | ventilation options, a `VentilationOption` mask |
| 100004, 100021 | `*_control_modes` | ventilation controls, a `VentilationControls` mask |
| 100196-100198 | `absence_schedule`, `*_target_temperature` | `PROG_ABSENCE` / `NIGHT` / `PRESENCE`, each a JSON `[temperature, offState]` pair and not a scalar |
| 100334-100341 | `new_schedule_*` | `THERMOSTAT_LIFESTYLE_HEATING_*` -- the lifestyle program, nothing new about it |
| 100078 | `identify_supported` | `VENTILATION_WINK_REQUEST`, read by `isWinkRequested` : a request, not a support flag |
| 358 | `air_circulation_scope` | `thermalAmbianceScope` -- nothing to do with air circulation |

358 is the one the Android enum does *not* carry : the app never reads it.
Its name here comes from the iOS list, which is the only source for it, and
which is wrong about every other id on this page at least once.

### Capability 153 is whether it is heating, not what is burning

Atlantic calls it `HEATING_STATUS` and reads it as `HeatingStatus { OFF,
HEAT_UP }`. The flame and the resistance are *how* a product makes heat,
which is a per-product detail, and the row had it as the default : anything
that was not an electric heater read `flame`, with a fire icon.

That reached the air conditioners, which report 153 and have no flame --
nine model ids in the capture corpus do, including the room units on the
household this integration is developed against. So the default becomes
`heating`, and the two products that know what is producing it say so on
their own rows.

This is the rule in CLAUDE.md the row was breaking : model-specific
behaviour goes behind a per-product entry, never into the shared default.
A default written for one product silently claims every product nobody has
thought about yet.

### 312 is the hot-water control target, and it is read-only

The placeholder name `Temp_312` was there because the iOS extraction gave
**both 306 and 312 the name `currentControlTarget`**, and 306 was already
mapped as a schedule bound. One of the two had to be wrong and nothing said
which.

The Android enum separates them : 306 is `MAX_NUMBER_OF_MILESTONES_PER_DAY`,
which is what 306 was already mapped as, and 312 is
`DHW_CURRENT_CONTROL_TARGET`. The iOS extraction was wrong about 306, and
312 keeps the name. The corpus agrees on the unit -- 45 to 65 °C across
five model ids.

It also stops being writable. The app has `String getCurrentControlTarget`
and no writer, where 231 beside it has both a getter and
`writeManualTargetSetByUser`. So it was a number entity offering a command
the vendor app never sends, and on an unbounded range at that : the row
declared no min and no max, which is the other thing a placeholder leaves
behind.

### One table, one row per id, nothing derived

`CAPABILITIES` in `capability_table.py` is the whole mapping : 225 rows, in
id order, every one an `Entity`. There is no second table and no shorthand
that expands into it -- the 86 descriptors are written out like everything
else, because a row you have to know is generated somewhere else is a row
you cannot read in place.

`enabled_by_default` has no default. Every row states it, true or false, so
whether an entity shows up on a device page is answered by reading the row
rather than by knowing what the field falls back to. A row that omits it
fails at import, which is the point.

What a dict literal of 225 rows cannot say is that an id is written twice :
Python keeps the last one silently. So a test parses this file and counts
the keys, rather than reading the table back, where the duplicate is
already gone.

### Twenty descriptors read as what they are, and the ones left alone

There was a `SELF_DESCRIBING_CAPABILITIES` table saying "the name is
everything we know", one name per id. For twenty ids that stopped being
true once the vendor app's readers were read
(`research/data/android_capability_types.tsv`), and `STRING` is still what
most of them say. They stay diag and stay **off by default**: knowing the
encoding is not a reason to put twenty more entities on everybody's device
page, and the flag is what makes the descriptor family cost nothing.

That table is gone, and so are the three decoding ones beside it
(`CAPABILITY_BIT_FIELDS`, `CAPABILITY_VALUE_SPACES`,
`CAPABILITY_SPEED_SETS`). All four folded into the `Entity` row: a
descriptor is a row saying `STRING`, `DIAG` and `enabled_by_default=False`,
and a decoding is that row's `bits` or `reads_as` -- 20 rows carry `bits`
today and 12 carry `reads_as`. The shared spaces are module-private tuples
the rows point at (`_HVAC_MODE_BITS`, `_SERVICE_VALUES`, `_SPEED_SETS`),
which is what keeps two ids in one space from drifting apart.

The type lives on the row and not in a branch of its own, and that part is
unchanged. A branch would have to restate the name, the category and the
flag for each of the twenty, and the coverage test that walks this table
and asserts "arrives switched off" would stop reaching them -- twenty
diagnostic entities silently turning themselves on breaks no test.

**The merge reversed an argument this entry used to make, and the property
it protected still holds.** The three decoding tables were kept separate
because they are read with the value at every poll while the descriptor
table is read once at setup, and capability 166 is why that matters: its
mask shrinks with the season, so a decoding settled at setup would show
last winter's modes until Home Assistant restarts. What makes the merge
safe is that `describe_capability_value` reads `bits` and `reads_as` off
the row at every call rather than resolving them when the entity is built,
so the row is read twice for different things -- once at setup for the
name, the type and the category, and again on each poll for the decoding.
Anything that pre-resolves a row's decoding puts 166 back.

`bits` and `reads_as` stay two fields rather than one, for the reason the
`Entity` docstring gives: 4 read as a sum is the third flag and looked up
whole it is the fourth member, both readings look sensible, and only the id
says which. A row setting both fails
`test_no_row_decodes_its_value_two_ways`.

- **Minutes** (296, 307, 331, 332, 333): the app reads them with
  `toIntOrNull` in its prog-in-range feature, and 331 reads 1440 on eleven
  models -- the minutes in a day, which is what named the unit.
- **Degrees** (352-357, 103199): `float getDayAbsenceTemperature` and its
  siblings, beside the setpoints the climate entity already reads. The
  corpus has 18/19/18/26/24/26 on ten models each; 103199 appears in no
  capture at all and is typed on the app's word alone.
- **Flags** (157, 381, 100078, 100102, 100103, 103150, 104050, 104051):
  each has a reader returning `boolean`. Every one of them reads 0 on
  every capture, which is why the corpus could not settle them and the app
  can: constant is not the same as false.

Left as raw strings on purpose:

- **294, 340, 295, 330** are steps (`TEMPERATURE_UPDATE_STEP`,
  `DHW_STEP_PROG_RANGE`). A step is not the quantity it steps, so 294 is
  not a temperature -- a `device_class` of temperature on it would put a
  "0.5 °C" reading into long-term statistics. `INT` would be honest but
  changes nothing: `sensor.py` builds it with the same class as a string,
  no unit and no state class. The precedent is 102022, the air-circulation
  duration step, already `INT` and already diag.
- **Counters** (93, 236, 244, 306, 329, 100000, 100301), same reason.
- **100300** is `float getProgramStartingDay`, and the app's `ProgDay`
  enum runs 1 (monday) to 7. The corpus reads 0 and 1. Two sources against
  the only one that speaks for real hardware is not enough.
- **105122** is a `long` of epoch milliseconds. No `CapabilityType`
  renders that, and adding one is its own change.
- **224 and 103034** are masks, handled above.

### Six more masks, and the two bits the corpus could not place

The vendor app's `fromBitField` classes were read whole in September 2026
(`research/data/android_bitfields_331.tsv`, app 3.31.0). The twelve tables
already here matched it member for member, which is the useful part: it is
the check that says the reverse-engineered ones were right.

Two bits were missing, and both had been seen on real hardware with no
name: **164 bit 10 (1024) is `dhw_production`**, read on 1040, 1298 and
1307, and **100013 bit 1 (2) is `boost`**, the second milestone type.

Six ids were masks read as a bare integer. 100004 and 100021
(`VentilationControls`) are the interesting pair: every value the corpus
holds -- 197, 205, 201, 49, 9, 1 -- decodes with no bit left over, which
none of the older tables can claim. 100002 and 100024
(`VentilationOption`) leave bits over. 103034 and 224 have exactly one
named member each (`antifrost` at 16, `water_flow` at 2) and the corpus
shows mostly other bits, so what they mostly report is the leftover count.

**224 is a mask, not a flag.** The app's method is
`boolean getEstimationSupport`, which reads like a boolean and is not: the
body is `fromBitField(...).contains(WATER_FLOW)`. The corpus reads 125,
113, 3 and 1. A capability is not typed by the signature that consumes it.

**188 bit 8 (256) is still unexplained.** `HomeService` has four members in
both copies of the class, and 257 is in the corpus.

### The speed sets (350, 100800) name a set, and `4` names one speed

These two ids are not a bitmask and not a member of an enum : one number
picks a whole set of speeds. The vendor's app has the mechanism as its own
method, `buildListFromValue`, next to `fromBitField` and `fromValue`. Here
the two ids read it through `reads_as`, pointing at `_SPEED_SETS` -- a
value looked up whole, which is the same shape as an enum and not the same
thing, and why `reads_as` is not called `values`.

`SpeedAirMixingState` and `VentilationSpeedMode` carry the same table, and
**`4` returns the auto speed alone** -- it used to read here as "on, auto",
which no capture contradicted because no capture has ever shown a 4. The
whole corpus reads 0 on 350 and 2 on 100800.

The app also has a fallback : a value outside 0-4 yields the full set, and
a *different* full set per id (air mixing includes the quiet speed,
ventilation does not). That is not reproduced. An unknown value is left
undescribed, so the raw number reaches the entity -- on a diagnostic
sensor whose reason to exist is investigating unknown hardware, the number
is worth more than a guessed set.

### `FAN_MODES` / `SWING_MODES` : global vocabularies, not model data

The value/label pairs `model.py` repeats per model are the vendor's own
enums, embedded once in the app : fan speeds are `low / medium / high /
quiet / auto` with the API value one above the enum index (1 low … 5 auto ;
4 is the quiet speed, which the app drives through 100802 instead), louver
positions are `position1..4` at face value. The corpus reads only values
inside those ranges. So availability is the presence of 100801 / 100803,
and the pairs themselves are constants.

### The identity fields

`modelFamily` is the API's own taxonomy — 13 values, closed list, from the
app's parser of that field — but it is only populated on the head device of
an installation : on a captured Navizone account every room unit and zone
behind the hub reads null, and their `longName` is `ROOM_n` / `---`. Hence
the two extra inputs : a child falls back to its master's family, and being
named `masterDeviceId` by anybody makes a device the hub of its line, since
the family cannot tell the head from the units. The user-facing name is
capability 154 (the room name typed in the vendor app), then `customName` ;
the commercial name is the one thing the derivation cannot produce.

## `custom_components/cozytouch/sensor.py`

### A reading of zero is a reading

`CozytouchUnitSensor.native_value` asked `if self._last_value:` and returned
None otherwise. Every way a device says zero is falsy -- `0`, `0.0`, `"0"`,
and the `"0.00000000000000000000"` the API actually sends -- so a sensor
reading zero reported *unknown*. An outside temperature at 0 C, an idle power
at 0 W and a thermostat with no probe all came out identical, and none of them
was in fact unknown.

It surfaced from the other end: the reporter on gduteil/cozytouch#69 has a
`Température Thermostat Z1` sensor reading "Inconnu" while the climate card
next to it says "Actuellement : 0 °C". Same capability, two readings, because
one goes through this property and the other does not.

The guard is now against None and the empty string. Two things it deliberately
does not change: an unparseable value still reads as 0.0 rather than as
unknown, which is inherited and which `tests/test_sensor_values.py` pins with
its reasons; and nothing here decides whether a zero is *meaningful* -- a
thermostat with no probe genuinely reports 0, and that is the mapping's
problem, not the sensor's.

The same method scaled before it looked: `float(value) * self._display_factor`
on a capability the device had stopped reporting is a TypeError, reachable by
any ENERGY capability declared in kWh. Guarded in the same place.

### Durations are minutes with a unit, not a formatted clock

Every capability the mapping types `TIME` is a duration, and none of them is
a time of day. The nine are 159 `override_remain_time_z1`, the boost
pair (232 `boost_total_time`, 233 `boost_remaining_time`), 102023
`air_circulation_remaining_time`, and the programming constraints -- 296
`schedule_minimum_interval`, 307 `heating_period_min_duration`, 331/332 the
range bounds, 333 `heating_period_max_duration`.

They were rendered by hand into `"%02d:%02d"`, with a `"Nd "` prefix past a
day. So `heating_period_min_duration`, which a boiler reports as 480, read
`08:00` on the card -- eight hours shown in exactly the notation that means
eight o'clock. `heating_period_max_duration` at 1440 read `1d 00:00`, which
is a day written as if it were not one.

mmnlfrrr/cozytouch@4783f88 found the same thing on an ACI HYB water heater
and replaced the formatter with another formatter, spelling the units out.
That fixes the misreading and costs a new module, a new test file, and a
string with `j` for *jours* baked into it -- this integration ships five
languages, so a German install would read `2 j 2 h`.

The reading is a number of minutes, so it is reported as one:
`SensorDeviceClass.DURATION`, `UnitOfTime.MINUTES`,
`SensorStateClass.MEASUREMENT`, through the `_unit` builder every other
dimensioned type already goes through. Home Assistant renders and localises
it, the recorder keeps statistics, and a template can do arithmetic on a
remaining-boost counter instead of parsing `1d 01:05`. The class it replaces
is deleted rather than rewritten.

What this gives up: nothing now prints `8 h` in a single glance -- the state
is `480 min`, which is longer to read and impossible to misread. If a card
ever wants the spelled-out form, that belongs in the card.

### The fault-code matrix is decoded, not shown raw

Capabilities 150, 290 and 303 (home, DHW and room fault codes) arrive as a
matrix the device fills with zeroes when healthy, and used to be surfaced as
that raw matrix -- a ten-row string nobody could read. Decompiling the app
(research, August 2026) named the row shape: `[system, majorCode, minorCode,
level]`, the exact key format Atlantic's own fault table uses
(`50_10_0_1`…). `decode_error_code` turns the matrix into the codes that are
active, so a healthy device reads `OK` and a faulted one reads its code list.

What counts as "not a fault" rests on the captures, and is two rules: an
all-zero row is healthy, and a row carrying `255` (`0xFF`) in any field is an
empty slot. The sentinel is well-supported -- whole accounts report the same
`[0,255,0,4]` row repeated ten times, which is one empty ten-slot list and
not ten identical faults. The `0xFF` reading is the app's, confirmed against
that repetition.

One limit is deliberate. No capture has ever shown an *active* fault row, so
the `system_major_minor_level` join is derived from the format, not from a
decoded example -- if a real fault ever legitimately carried a `255`, this
would read it as empty. `OK` is a plain, language-neutral token rather than a
translated state, matching the raw-string diagnostic sensors around it.

The other limit -- that the code was shown and never its meaning -- has since
been lifted; the entry below says how.

### The fault's meaning is fetched, not shipped

Mapping a code to its human text needs Atlantic's fault-string table, and that
table is theirs. It is now read from them at the moment it is needed rather
than copied here: `productmodels/models/{modelId}/detailederrors` answers the
whole table for one model, and `parentProductErrorCode` is the matrix row
packed one field per byte (`docs/api-surface.md`, 16/09/2026). So the lookup
is exact rather than heuristic, and nothing of theirs sits in this repository.

What it costs a household is the point of the shape. The table is read only
when a row is actually active, which on a healthy account is never, and it is
cached per model for the session -- including the empty table a failure
yields, so a route that keeps refusing is asked once rather than once a poll.
An air conditioner has no table at all (404), which is why the fetch treats
"no answer" as an ordinary outcome and not an error.

The label lands in the sensor's *attributes*, not its state. The state stays
the code: it is what automations already match on, a label runs past what a
state may reasonably hold, and a lookup that misses then degrades to exactly
the behaviour that came before. Beside it, a repair notice is raised per
device and per code, `is_fixable=False` -- nothing Home Assistant does settles
a hydraulic pressure fault, and the notice exists to say, in the vendor's
words, what the hardware is complaining about. It clears itself when the code
stops being reported.

### The last-poll sensor stays available through the failure it dates

`CozytouchLastPollSensor` overrides `available` to "a poll ever succeeded"
instead of inheriting the CoordinatorEntity reading, which follows the *last*
poll's outcome. The default would take the sensor down with everything else
the moment the API stops answering -- which is exactly when "how old is what
the entities show" is the question being asked. A 429 backoff never trips
either reading (the coordinator deliberately treats it as a skip, not a
failure), so the override only shows during a real outage: every value sensor
goes unavailable, and this one keeps naming the moment the data stopped
moving.

Two smaller choices ride along. The date is stamped by the setup-view read
itself (`CozytouchAccount._read_setup`), so `connect()` counts as the first
poll and the sensor is never born empty. And it is surfaced per device even
though one account-level request refreshes everything, so the reading sits on
the device whose values it dates -- the duplication is the account beat made
visible, not N measurements.

## `custom_components/cozytouch/__init__.py`

### Setup registers every device itself, before the platforms

A device used to exist in the registry only once some platform added entities
for it. That is a race: `async_forward_entry_setups` runs the platforms
concurrently, and a room unit's `device_info` names its gateway in
`via_device` -- so any platform that reached the room unit before one gave
the gateway an entity registered a link to a device that was not there. It
was not theoretical: calendar and climate, which build nothing for a gateway,
did exactly that on a live install (HA log, 2026-08-28, `via_device
('cozytouch', <gateway subentry>)` "non existing"), and Home Assistant
announces that 2025.12 stops honouring such a link instead of warning.

So `async_setup_entry` now walks the subentries and calls
`async_get_or_create` for each -- gateways first, since the children's links
point at them -- before forwarding a single platform. The platforms then find
the device already there and merely restate it, which is why the description
they use (`device_info_for`) moved to `hub.py`: one function serving setup
and entities keeps the two registrations identical by construction.

`get_via_device` itself is unchanged. Its check -- link only when the gateway
is a subentry of the same entry -- was always right; what it could not see is
*when* the gateway's device would appear. Registration order is the other
half, and `tests/test_topology.py` pins both.

### The gateway link is declared by registry id, not by identifiers

`via_device` names the gateway by its identifiers and lets the registry
resolve them; `via_device_id` names the registry id outright. The first is
deprecated, and on a current Home Assistant it does more than warn. The
deprecation report walks the stack for an integration frame to attribute
itself to; called from an entity's `device_info` there is none -- the call
comes from `entity_platform`, core code -- so the report raises a RuntimeError
instead of logging, and `_async_add_entity` dies with it.

Three hours of debug logging on a live install (2026-09-13, HA 2026.9) show
what that costs: `Error adding entity None for domain binary_sensor with
platform cozytouch`, once per room unit, every setup and every retry. Every
room unit's cloud-connectivity sensor was silently missing. Only
`binary_sensor` appears in the log because it was the only platform that
carried its *own* copy of the description -- the rest go through
`device_info_for`, whose device the registry already held from setup, so
their `async_get_or_create` came back with nothing to update and never
reached the report. One copy of a description is not tidiness here; it is the
difference between one platform failing and all of them.

So `device_info_for` resolves the gateway and declares `via_device_id`, and
the copy in `binary_sensor.py` is gone -- it now calls `device_info_for` and
overrides `name` alone, which was the only field it ever said differently.

The resolution is a registry lookup, which is why it is not a straight swap.
`via_device_id` naming a device the registry does not hold raises outright,
where the deprecated key merely warned; `via_device_info` answers with no link
at all in that case. Setup registering gateways first (above) is what makes
the lookup find something, so the two halves are one mechanism.

`DeviceInfo` gained `via_device_id` in **2026.8.0** -- bisected over the PyPI
wheels, since the field is a TypedDict key and no release note names it: 2026.7.0
does not have it, 2026.8.0 does. The declared floor is well below that, so both
spellings have to be reachable; `_VIA_DEVICE_ID_SUPPORTED` reads `DeviceInfo.__annotations__`
rather than comparing versions, and it is the only compatibility branch in the
integration. It goes when the floor passes 2026.8.0, which is not a floor worth
having for it -- Home Assistant removes `via_device` in 2027.8 and the branch
expires on its own.

`tests/test_topology.py` pins both spellings on whichever release the job
installed, rather than asserting whatever the installed `DeviceInfo` happens to
declare: a test that says one thing at the floor and another at the pin proves
neither.

### A timeout that stringifies to nothing named nothing

The same log carries `Error requesting Cozytouch_27906640 data: Network error
reading the setup view: , forcing reconnect`. The message is not truncated:
`asyncio.TimeoutError` -- what aiohttp raises past `REQUEST_TIMEOUT`, and the
commonest failure on this API -- carries no args, so `f"{err}"` is the empty
string. The one line that exists to name the cause named nothing, and the
traceback that does name it is behind a debug level nobody has on.

`account.why(err)` is `str(err) or type(err).__name__`, used at the five sites
that format a network error. A fallback, not a replacement: an error that says
something keeps saying it.

### The per-day program sensors give way to the calendar (issue #42)

A device that reports a whole program block gets a calendar for it, and the
seven diagnostic sensors next to it render the same days as truncated strings
-- fourteen near-identical rows per air conditioner (screenshot on the issue).
The first plan was one consolidated sensor per block, state = today and the
week as attributes; it died in review against what already exists: the
calendar *is* that view, with the setpoints as event titles and
`calendar.event` as "the setpoint in charge right now". Deleting the sensors
was considered next and dropped too -- disabling gives the same device page
with a two-click way back for whoever reads one in a template.

So there are two halves, and the whole-block rule gates both, because a
partial block builds no calendar and its per-day sensors stay its only view:

- the mapping ships a covered block's days `enabled_by_default: False`
  (`capability.py`), which Home Assistant only reads when an entity is first
  registered -- new installs and new devices;
- the 2.2 entry migration (`async_migrate_entry`, `MINOR_VERSION` in the
  config flow) disables the ones an existing install already registered.
  Exactly once, which is the point of doing it as a migration rather than at
  every setup: somebody who re-enables a sensor must never find it disabled
  again. `disabled_by=INTEGRATION`, and a sensor already disabled by the user
  keeps saying USER.

The two halves read "whole block" off different evidence, and the gap is
known: the mapping checks the ids the device *reports*
(`availableCapabilityIds`), the migration checks the ids the registry
*holds*, while the calendar checks the seven *values* are not None. A block
fully reported with a null day would be disabled here and get no calendar --
no capture has ever shown one, and a wall of unknown-valued sensors is not a
view worth keeping enabled for that case. The milestone blocks
(100320-100333) and the time ranges (245-251) have no calendar and stay
enabled; `tests/test_prog_visibility.py` pins all of it.

## `capability.py` : reading the descriptor capabilities

### Where the tables come from, and what they are not

The `supported_*` / `available_*` capabilities are bitmasks, and the ids
around them are small enumerations. Neither the API nor the iOS app says so
in any readable form -- three passes over the iOS binary logged the DHW
masks (168, 336, 105012) as unresolved. The **Android** app settles it: its
capability layer is Kotlin rather than compiled Swift, so the enums, their
masks and their API values are readable as source. The `bits` and
`reads_as` a row carries are that reading.

Two properties of it matter when editing them.

**A member can own several bits.** The app tests `mask & value != 0`, not
`mask & value == mask`, which is what lets `auto` claim bits 1 and 2 at
once. A table written as one-bit-per-member would read 415 and 411 as
different mode sets, and they are not.

**The two mode spaces are different enums.** 166 and 100022 are the HVAC
space (off / auto / cool / heat / fan / dry, plus emergency heat,
pre-cooling and sleep which are values but never appear in a mask). 217 and
100023 are the control space (basic, prog, lifestyle prog, heating
anticipation, unexpected events, auto, energy saving, absence, scheduled
absence). They carry numbers of similar size -- 411 against 3331 -- and
reading one with the other's table produces plausible nonsense. Across the
whole capture corpus, split this way, **neither space leaves a single bit
unaccounted for**.

### What was left out, and why

The app also carries ventilation control and option masks that would fit
100002 / 100004 / 100021 / 100024, and a single-bit mask for 224. They are
not in the tables: on the captures, 10 of 38 readings of 100004 and 100021
set bit 7, which is past the last member the app names, and 13 of 15
readings of 224 set bits its one member cannot explain. Either those ids
are not what the app calls them, or the enum read out of it is partial.
Naming the low bits of a mask whose top bits are unexplained is how a wrong
reading gets believed, so they stay raw.

Where a mask *is* decoded and a bit is still unclaimed -- 164 bit 10, 188
bit 8, both seen on real accounts -- the reading says so (`unknown (1024)`)
rather than dropping it. These entities exist to investigate hardware
nobody here owns, so the bit nothing names is the interesting part. The
number the device sent stays on the entity as a `raw` attribute for the
same reason.

### Five hot-water ids named off the Android enum, not off a capture

`research/data/capability_id_to_name_android.tsv` names 244, 105011, 105122,
105906 and 105907, and the mapping had nothing for the first three and the
placeholders `Target 105906` / `Target 105907` for the last two. The names
here are the app's, transliterated to the naming already in the table:

| id | The app's name | Here |
| -- | -------------- | ---- |
| 244 | `DHW_MAX_NUMBER_PROGRAMMING_RANGE_PER_DAY` | `max_schedule_ranges_per_day` |
| 105011 | `DHW_SUPPORTED_MODES_CAPABILITIES` | `supported_dhw_modes` |
| 105122 | `DHW_BOOST_END_TIMESTAMP` | `dhw_boost_end_timestamp` |
| 105906 | `DHW_V40_APPLIED_SETPOINT` | `v40_applied_setpoint` |
| 105907 | `DHW_V40_MANUALLY_FILLED_BY_USER` | `v40_setpoint_filled_by_user` |

244 is the max counterpart of 329 (`DHW_MIN_NUMBER_PROGRAMMING_RANGE_PER_DAY`,
mapped as `min_schedule_ranges_per_day`), and so takes the same shape. It is
a different bound from 236, which the app calls
`DHW_MAX_NUMBER_MILESTONE_PER_DAY` -- ranges and milestones are two things,
and a mapping that merges them reads one device's limit onto the other.

105011 carries the same `DHWMode` mask as 168, so its row's `bits` points at
`_DHW_MODE_BITS`, the table 168 already uses, the way 105012 pairs with 223.

What the enum does **not** settle is the encoding of 105122. The name says a
Unix timestamp and the fork this was compared against reads it as one, but no
capture here holds a value, so it arrives as a raw string and switched off --
the rule for any capability whose encoding is unverified. A reading turns it
into a real timestamp.

105907 is the one to be careful with. `MANUALLY_FILLED_BY_USER` is not "the
setpoint the user set": the mapping types both 105906 and 105907 as
temperatures between 15 and 65 °C, so the reading carried here is the V40
setpoint *as filled in manually*, against 105906's *applied* one. Nothing in
the corpus shows the two disagreeing, which is what would prove it.

Every id here is hot-water, and no device on hand reports one. The evidence
is the app's own enum and nothing else -- which is stronger than a guess and
weaker than a capture.

### Twelve more ids the enum names and the corpus confirms

Walking the whole of `capability_id_to_name_android.tsv` against the mapping,
rather than only the ids the fork happened to touch, left 14 named by the app
and mapped nowhere here. Eleven are taken. `9812 DEBUG` and `106 POWER` are
not, because a name that vague buys an entity nobody can read, and `100014
ROOM_TYPE` is not either: it is one of the two ids a thermal zone reports,
and a zone deliberately resolves to no entity at all. Naming it is what
`test_a_zone_maps_to_nothing_at_all` exists to catch, and it caught it.

What makes these better evidence than the five above is that
`research/capability-corpus/by-capability.md` holds values for most of them:

| id | The app's name | Here | The corpus reads |
| -- | -------------- | ---- | ---------------- |
| 352 | `ABSENCE_DAY_HEATING` | `absence_day_heating_temperature` | 18, on 10 models |
| 353 | `PRESENCE_DAY_HEATING` | `presence_day_heating_temperature` | 19, on 10 models |
| 354 | `PRESENCE_NIGHT_HEATING` | `presence_night_heating_temperature` | 18, on 10 models |
| 355 | `ABSENCE_DAY_COOLING` | `absence_day_cooling_temperature` | 26, on 10 models |
| 356 | `PRESENCE_DAY_COOLING` | `presence_day_cooling_temperature` | 24, on 10 models |
| 357 | `PRESENCE_NIGHT_COOLING` | `presence_night_cooling_temperature` | 26, on 10 models |
| 100000 | `THERMAL_ZONE_NUMBER` | `thermal_zones_count` | 1, 2, 3 |
| 100196 | `PROG_ABSENCE` | `absence_schedule` | nothing |
| 102006 | `AIR_MIXING_MODES_AVAILABLE` | `air_circulation_available_modes` | 285, on 3 models |
| 102020 | `AIR_MIXING_ACTUAL_MODE` | `system_service` | 3, on 3 models |
| 105636 | `DHW_COMFORT_MODE` | `dhw_comfort_mode` | 0 and 1 |

The six 352-357 are the find. Ten distinct models report them, fifteen
readings each, and every reading is the same number: 18/19/18 in heating and
26/24/26 in cooling. Those are °C, and they line up as a comfort grid --
absence colder than presence in heating and warmer in cooling, night
following day. The name and the number agree, which neither does alone.

They are named the way 100197 and 100198 already are (`*_temperature`, raw
string, off by default) rather than typed as temperatures. The corpus shows
what they read, not whether anything writes them, and nothing here has ever
seen one move.

102006 is the one the corpus actually decodes: 285 is
1|4|8|16|256 against `_AIR_CIRCULATION_MODE_BITS` -- off, auto season, cool,
heat, dry -- with no bit left over. So its row's `bits` points at the table
102005 already uses. 102005 is
`AIR_MIXING_MODES_SUPPORTED` and 102006 is `..._AVAILABLE`; the supported /
available pair is kept in the names because the app keeps it.

102020 reads 3, which is not one bit of that table and not obviously one
member either, so it stays raw.

### The chain reads in ascending id order

119 branches on disjoint ids, so nothing but reading order depends on where a
branch sits -- which is why it drifted. Ids were landing wherever the commit
that added them happened to be editing: 303 between 184 and 196, 150 and 290
after 102024, 312 after 105907, 100320 after 100507. Looking an id up meant
grepping for it instead of scrolling to it.

The rule is ascending by the branch's lowest id, range branches sorting on
their low bound, and `test_the_mapping_reads_in_ascending_id_order` is what
keeps it rather than anyone remembering. A new branch goes where its number
goes.

The reorder itself is provable: `tests/snapshots/` did not move a byte.

### The enum is not the catalogue

Worth recording, because it is the question this walk was meant to answer.
The app names 187 ids; the mapping now claims 206. **46 of ours are absent
from the enum**, including 1, 2 and 8 -- the base HVAC modes, which every
device on every account reports.

So the Android enum is not the capability catalogue `docs/api-surface.md`
says does not exist. It is what the *app* knows how to display, which is a
different and smaller thing. Recouping it against the corpus is worth doing
again when the app ships a new version; treating it as exhaustive is not.

### `read_setpoint` : hundredths, but not for hot water

The app divides a program slot's target temperature by 100 when it reads
above 40, so a slot storing 1950 shows as 19.5 °C. No capture here has ever
shown one -- this is the app's rule, carried because a device that did it
would otherwise put 1950 on a dashboard.

It is scoped to the thermostat blocks (196-209, 100320-100333) on purpose.
The hot-water block (237-243) reports 50, 54, 60, 62 and 65 in the corpus:
real tank setpoints, all above the threshold. Applying the rule there would
turn a 65 °C tank into 0 °C, which is why `parse_slots` takes the
capability id and does nothing without one.

## `custom_components/cozytouch/number.py`

### Four classes that were one

`TemperatureAdjustmentNumber`, `TemperaturePercentAdjustmentNumber`,
`HoursAdjustmentNumber` and `MinutesAdjustmentNumber` differed in three
things -- what they declare about themselves, how an API value becomes a
displayed one, how a displayed one goes back -- and were copies of each other
in the hundred lines around those three. The bound alone, four lines of
`if value < min ... elif value > max`, was written eight times: once per read
and once per write in each class.

They are now one base class and its subclasses carrying `_from_api`,
`_to_api` and their own declarations, which is 134 lines less. Three are left
-- `HoursAdjustmentNumber` went with the override duration below, since it was
the only row that produced it. The names survive because `async_setup_entry`
dispatches on them, and every one of them
claims the same unique id it always did (`..._number_<capabilityId>`), so no
install wakes up with a renamed entity. That is what made the merge safe, and
`tests/test_number.py` pins it -- along with what each one reads and writes,
which nothing tested at all before.

### Setting a value now asks for a refresh whatever the unit

Hours and minutes called `async_request_refresh()` after a write; the two
temperature entities did not. Nothing distinguishes them -- the same
capability write, the same cloud, the same wait -- so a setpoint typed into a
temperature box sat unreflected until the next account poll, up to
`DEFAULT_POLL_INTERVAL` later, while a duration updated at once. It reads as
an omission rather than a decision, and the base class now refreshes for all
four.

### A ceiling reported as 0 collapses the range, and is left alone

`TemperatureAdjustmentNumber` re-reads its bounds from the device on every
update, through `lowestValueCapabilityId` and `highestValueCapabilityId`. The
guard is `if highestValue:` on the string the API sends, so `None` is ignored
but `"0"` is taken -- and a ceiling of 0 leaves a number entity that cannot be
set to anything.

That is almost certainly wrong, and it is pinned as it stands
(`test_a_bound_reported_as_zero_collapses_the_range`). Nothing in any capture
says whether a device reports 0 for a bound it has not been configured with,
and the suite here is characterisation: changing the reading on a guess would
be inventing behaviour for hardware nobody has looked at. It changes when a
dump shows one.

### The device description is declared once

Five classes carried the same three-line `device_info` property and a sixth
carried its own copy of the whole description -- which is the one that broke
(above). `CozytouchDeviceEntity` in `hub.py` carries it now; a platform class
inherits it and says nothing. `CloudConnectivity` still overrides `name`,
which was always the one field it meant to say differently.

## The declared floor

### 2025.12.0, and what raising it did not buy

The floor was 2025.4.0, and it was found by running the suite against
candidates rather than by reading changelogs. Config subentries -- one entry
per account, one subentry per device, the shape this integration is built on --
are absent from 2025.2.0: `ConfigSubentryFlow` does not import, and
`tests/test_floor.py` says so. The whole 2025.3.x line, which does have them,
cannot be installed at all: it pins `aiohttp==3.11.13`, which PyPI has since
yanked for a regression. A floor nobody can install is a claim nobody can test.

It was raised to 2025.12.0 -- the first of the last 2025 line -- in September 2026,
for no reason stronger than age: nothing in the integration needed an API from
it, and supporting an April 2025 release from late 2026 costs a matrix
combination somebody has to keep green and buys nobody anything.

What it did **not** buy is worth writing down, because it was the reason the
raise was proposed. `via_device_id` arrives in 2026.8.0, not in 2025.12, so
`_VIA_DEVICE_ID_SUPPORTED` survives the raise untouched. Measuring that before
editing anything is what kept the change honest about its own value.

The candidate was validated by running the whole suite against it, which is
also how the one surprise surfaced: `pycares<5`. Home Assistant pins aiodns,
aiodns does not pin pycares, and pycares 5 renamed the result types aiodns
annotates with -- so `import aiodns` raises `AttributeError: module 'pycares'
has no attribute 'ares_query_a_result'` and all twenty-one test files fail to
collect, with nothing in the error naming pycares. A real install never sees
it; it is an artefact of resolving an old release's dependencies fresh today.
The pin lives in `requirements_test_min.txt` and nowhere else, since the
current release resolves it correctly on its own.

## `.github/workflows/release.yaml`

### It installs with pip, where tests.yaml uses uv

The job is dispatched by hand a few times a year, so the minute it spends is
not worth the change on its own. Leaving it on pip also keeps a standing
proof that the requirements install without uv, which is what a contributor
following the README has.

## `custom_components/cozytouch/hub.py`

### The poll is the account's, every 60 seconds, and a write does not wait

The setup view carries every device, so the beat is one request a minute
whatever the account holds, where the per-device poll it replaces was one per
device per minute — five for the gateway-plus-four-units account in
`docs/api-surface.md`.

It ran at 30 s for a while, on the argument that the new shape had bought the
headroom. What that bought was half the latency on a change nobody made from
Home Assistant — a schedule firing, somebody turning a dial on the wall — and
those are not events anybody is watching a dashboard for. What is watched is
the second after a write, and a shorter beat is a poor way to pay for it : it
spends every minute of every day on the one minute that matters.

A write pays for it directly instead. It refreshes the device written to, then
reads the account at once and once more at `WRITE_SETTLE_DELAY`, which is what
the other devices get : a capability can be the whole home's — air circulation
(102024) is — and the device that wrote it is not the only one whose value
changed.

The immediate read is immediate because it can be, which was measured rather
than assumed ; the entry below says what. The second is for what a device
derives from a write rather than what the write set — the remaining time, the
mode a unit locks itself into — and is the only half that needs a guard
against stacking, since the first goes through Home Assistant's own debouncer.

That is the vendor app's shape rather than its numbers — it polls every device
every five seconds, and only while somebody has it open. See the entry under
`hub.py` for what was read out of it.

### Neither plane is staler than the other, measured (22/09/2026)

`research/probe_propagation.py` writes one capability and then watches both
routes until each agrees. Air circulation (102024) on ROOM_0 of the reporting
account, three rooms behind one HUB Navizone :

    wrote '1' on 27906641, execution 18612101 -> state 3
      +0.0s  /capabilities(27906641)='1'  setupviewv2 agreeing: [27906641, 27906642, 27906643]

Both planes carried the new value on the first read after the execution
reported completion, and all three rooms flipped together. So :

- `setupviewv2` is not a cache that a write leaves behind. A write can read
  it, which is the difference between one request and one per device — seven
  on that account, against a `rateLimit` that reads 30.
- The vendor app reading `/capabilities` and never `setupviewv2` is not a
  freshness argument. The likely reason is payload size : the setup view is
  the whole account, and the app asks every five seconds over cellular.
- There is no per-device propagation to wait out. A household capability is
  already true of every room by the time the execution completes ; what the
  siblings lack is somebody to go and fetch it, which is what the write-time
  read is.

What this does *not* establish : one capability, one account, one moment. A
capability that reaches the hardware over a slower link may well behave
differently, and `PENDING_WRITE_GRACE` is still the guess it always was —
this measured the cloud agreeing, not the hardware confirming.

The account's own `rateLimit` reads 30 on the one account ever captured. It is
used as a ceiling in `poll_interval` and was never the source of a number here.

The floor of 15 s is where the requests stop buying anything. Atlantic's cloud
learns from the hardware on its own schedule, and no amount of asking makes a
radiator report sooner.

### `rateLimit` is read as requests per minute, as a ceiling only

Nobody knows what that field counts — `docs/api-surface.md` says so plainly —
but of the readings a working 60-second-per-device poll does not already
disprove, it is the strictest, and a ceiling wants the strictest. On the one
account ever captured it is 30, which permits everything down to the floor and
so never bites ; on an account that declares 1, it does.

### One coordinator on a beat, and one per device pushed to from it

This used to be a coordinator per device, each fetching
`/magellan/capabilities/?deviceId=` for its own — N requests a minute for N
devices. The setup view answers for the whole account in one request
(`account.refresh_setup`), which is why the shape was worth changing : the same
budget buys N times the frequency, and the cost stops growing with the number
of devices somebody ticked at setup.

The hubs stay coordinators with no schedule of their own, which keeps every
entity a `CoordinatorEntity` of its own device — one device failing still shows
as that device failing — and leaves `async_request_refresh()` after a write
working as it did. `Hub._async_update_data` therefore runs only when something
asks, which is after a write : re-reading the whole account to confirm one
setpoint would be the wrong trade at that one moment.

The hubs are a constructor argument of `AccountCoordinator` rather than
something attached afterwards : a coordinator that polls before it knows who to
tell would spend a request and drop the answer.

### The account coordinator subscribes to itself

Nothing else ever does : every entity listens to its hub, and Home Assistant
books a coordinator's next refresh only while it has at least one listener.
Without `async_add_listener(lambda: None)` the interval is dead letter — setup's
one refresh runs and no poll ever follows it. This was live for three releases ;
`tests/test_polling.py` covers it.

### A rate limit backs off, it does not fail

Being asked to slow down is not the same as having failed, and marking every
entity unavailable because the account is a few seconds ahead of its budget
would be a worse lie than a value that is one poll old. The values stand, and
the next tick finds the backoff still holding and skips in turn.

`ConfigEntryAuthFailed` is the opposite case and passes straight through the
coordinator, which answers it by opening a reauth dialog and by not
rescheduling itself. `UpdateFailed` would only book another attempt with the
same rejected password.

### An account failure reaches entities through their hubs

The failure belongs to the account, and no entity listens to the account
coordinator, so `_publish_error` marks every hub instead.

### The away window is staged, then committed

Editing the start or the end of the window stamps the change, and the commit
runs once that stamp is more than 20 seconds old, so both ends can be set
before either is sent. It used to hang off the hub's own 60-second poll, which
no longer exists — so it runs on every path that now stands in for it, the
account's tick and a post-write refresh alike. Hanging it off one of them would
have made the delay depend on which, and off neither would have left a staged
window sitting there for good.

### `modificationDate` reads as None rather than as 1970

Anything missing, unparsable or at or below zero comes back None. The field is
undocumented — there is no catalogue to check it against — so what it holds on
hardware nobody has captured is a guess, and a wrong timestamp on a dashboard
is worse than an empty one. A string is tolerated because `value` arrives from
this API as one.

`get_last_modification_date` takes the newest across the whole device rather
than one capability : the question it answers is whether the hardware is still
talking to Atlantic's cloud, and one capability can legitimately sit unchanged
for hours.

### The device lookup is a module function, not a method

`device_of` is read by eleven of Hub's methods and is deliberately not on the
class : the tests drive those methods unbound against a duck-typed stand-in
(`Hub.get_via_device(SimpleNamespace(...))`), which has no methods of its own.

### A write updates the local value only on a completed execution

A write that never lands has to leave the local value alone, and let the next
poll say what the device really did.

### The diagnostics dump describes the account, not the hub that was asked

Every device the setup returns is listed, whether or not somebody added it,
because what a mapping needs first is the model ids a user actually owns — with
the capability ids to go with them, since the setup view carries a capability
list for every device on the account.

Those lists are all as fresh as each other now that the setup view is the poll :
a device nobody added is refreshed on the same tick as one somebody did, where
it used to hold whatever the last reconnect said. `isConfiguredHere` therefore
says which devices have entities and no longer implies anything about freshness.

Zones are skipped. They are not hardware anybody has to map, and a dump is read
to find hardware that is ; listing them put two capability ids that resolve to
nothing — one of them declined on purpose — in front of whoever reads it, which
reads exactly like work to do.

### The gateway link, and `via_device_id`

The API declares the topology itself : every room unit and thermal zone carries
the gateway's id in `masterDeviceId`. Home Assistant can only draw the link if
the gateway was added too, since a device here is registered under the subentry
it was added as — so `get_via_device` returns None for a gateway, and for a
child whose gateway nobody added. None rather than a guess matters : HA logs a
warning when `via_device` names a device that is not in the registry. The
registry-id spelling is covered under `__init__.py` above.

### An unset absence window reads as unknown, not as a word of our own

The pair reads `[0,0]` until somebody sets a window, and the sensor answered
that with the literal string "Undefined" — untranslated, so a French install
showed an English word, and a state a template had to compare against by
spelling. `None` is what Home Assistant already has for this : the frontend
renders it in the reader's language, `states()` gives `unknown`, and the
`unknown` / `unavailable` distinction other integrations rely on starts
working. The datetime entities on the same capability already returned None.

### What the vendor app does instead of a poll interval (22/09/2026)

Read from the decompiled Android app, in
`fr/modulotech/app/domain/GacomaPollManager.java`. There is no push : no
websocket, no server-sent events, no FCM message carrying a value. The app
polls, and it polls harder than anything Home Assistant would tolerate.

`startPolling` builds `Observable.interval(0L, 5L, TimeUnit.SECONDS)`. Each
tick maps every registered device to a `GET /magellan/capabilities/?deviceId=`
and merges them with `Single.merge`, so N requests leave together and each
screen is updated from its own reply through
`Listener.onCapabilitiesUpdated`. Three rooms therefore refresh one after
another in whatever order the cloud answers, which is what somebody watching
the app sees and reports as a value "propagating" from device to device.
Nothing propagates : three replies arrive.

`setupviewv2` is not in that loop at all. `GlobalRepositoryImpl.fetchSetupView`
runs at login and after a pairing, and never again. The app's live view is
`/capabilities` per device, which is the opposite of the trade this
integration made -- and for a reason:

`DefaultActivity.onPause` calls `stopPolling`, which disposes the
subscription; `onResume` calls `initPolling`, which re-registers every device
of the account and starts a fresh interval with an initial delay of zero. The
5-second beat exists only while somebody is looking at a lit screen, for the
minute or two that lasts. Home Assistant polls for months without anybody
watching, so the app's number cannot be copied -- only its shape : fast while
somebody is acting, cheap the rest of the time.

`POST /magellan/executions/refreshcapability` is the app's other lever and is
still unused here (`docs/api-surface.md`) : it asks the cloud to re-read one
capability from the hardware rather than waiting for the hardware to report.

## `custom_components/cozytouch/calendar.py`

### The program is a calendar

The program is what these devices are scheduled by — it keeps running when Home
Assistant is off — and it could only be read as seven strings, one per day,
formatted for a dashboard. `get_schedule` made it machine-readable ; the
calendar makes it a week you can look at, and something the `calendar` triggers
can fire on : "when the program moves to its next setpoint" is an event start,
which is the shape of an automation nobody could write before.

### The calendar is where the program gets edited

It was read-only at first, because an event has a start and an end while a slot
has only a start — the next slot is what ends it — and rewriting the following
slots looked like the wrong thing to do silently. `set_schedule` was the answer,
and a service call is not an answer for somebody looking at the week in a card.

So the calendar takes the edits, and the rule that was feared is stated instead:
an event is one slot, and the slot it needs after it. Creating an event drops a
slot at its start, and a second one at its end carrying whatever the day held
there — which is exactly the block that was drawn, and leaves the rest of the
day as it was. An event ending at midnight, or running into the next day, adds
nothing: the last slot of a day already runs to the end of it.

Deleting an event removes its slot, except the one at 00:00 : `build_matrix`
refuses a day that does not begin at midnight, so that slot is retitled, never
deleted. Moving an event off its weekday deletes it on the old day and creates
it on the new one — two writes, and two capabilities, which is what a weekday
is here.

The setpoint is read from the event title, since that is the only field the
calendar dialog offers : anything that parses as a number, so "19", "19 °C" and
"19,5" all land. A title with no number is refused rather than guessed at.

The week repeats, so every edit is permanent from that weekday on ; there is no
"only this occurrence", and `recurrence_id` and `recurrence_range` are ignored
for the same reason. Writing stays gated on `WRITABLE_PROGRAM_BLOCKS`, so the
hot-water block is still read-only until a capture confirms its encoding, and
`slot_limit` still caps how many slots a day may hold.

The entity's state is not the useful part : a program that covers the whole day
means `event` is never None, so the entity sits at `on` for good. What is
useful is the current event and the next one, which is what the card shows and
what an automation reads.

### A calendar exists only for a block the device reports in full

All seven days rather than any : the mapping claims 196-209 wholesale, so a
device that has the block has every day of it, and a calendar built from a
partial one would show a gap where it should show a setpoint — which reads as
"nothing scheduled that day" rather than as missing data. The same rule gates
the per-day sensors arriving disabled, under `__init__.py` above.

### `CURRENT_EVENT_WINDOW` is a day either side of now

The last slot of a day runs into the next one, so the event in charge at 00:30
began yesterday. The window has to reach past now as well, since
`_events_between` takes a half-open range and would drop a slot starting
exactly on the boundary.

### Expansion is in Home Assistant's local time

The device stores minutes past midnight and nothing says which clock it keeps.
It reports an offset — the away-mode timestamps use it, and
`docs/architecture.md` records that path applying it twice — but no capture has
ever tied that offset to the program. Home Assistant's zone is the reading that
matches what the app shows for anyone whose house and hub agree, which is
everybody until somebody reports otherwise.

A slot runs until the next one, and the last of the day until midnight : the
next day's first slot starts at 00:00 — `set_schedule` refuses a day that does
not — so nothing is left uncovered. Events are selected by overlapping the
range rather than by being contained in it, because an event that started
before the window is the one running at its beginning.

The seven days are read once and not once per date, or a card asking for a year
would re-read and re-sort the same seven programs 365 times.

### An unusable slot is dropped, and the rest of the day still renders

A minute count past the end of the day, or a setpoint that is not a number.
Neither has been captured ; both are one bad matrix away from breaking every
event in the week. The temperature is carried as a float on purpose : the
summary formats with `%g`, and a value that arrived as a string — which this
API does — would raise there instead, taking the whole calendar with it.

`_slots_for` also sorts, though the device stores slots in order : an event list
built on that assumption without checking would put an evening setpoint in
charge of the morning.

### `heating` and `cooling` are the service's words

Kept so one vocabulary covers all three blocks. `capability.py` calls 203-209
the zone 2 program outside air conditioners, which is the same unresolved naming
`set_schedule` carries ; the program exists in both cool and heat, so nothing
here decides it either.

## `custom_components/cozytouch/account.py`

### The account owns the session, the token and the setup view

Everything a Cozytouch account declares — the token, the household, the zones,
the list of devices — is the same answer whatever device is asking, because
`setupviewv2` describes the whole account and not the device that fetched it.

This lived on `Hub`, which meant one config entry per device also bought one
session, one `POST /users/token` and one `GET setupviewv2` per device : a
gateway plus four units cost five logins for four copies of the same payload.
Worse, the state it filled in sat on the `Hub` *class* for a while, so the hubs
overwrote each other and the last one to connect won —
`tests/test_regressions.py` still pins the fix. The state was always shared ;
owning it in one object says so, and lets the shape be checked.

The per-device half stays on `Hub` : which capability ids that device reports,
what they mean for its model, and the targeted fetch that confirms a write.

The session is Home Assistant's own and not one of ours : it is closed when Home
Assistant stops, so there is nothing left to leak when a setup fails and the
account it built is discarded.

### A confirmed write outranks the setup view for a minute

Every platform writes a capability and then asks the coordinator to refresh, so
the entity shows what the device now reports rather than what it was asked for.
The two do not happen in that order. `writecapability` returns an execution id,
`_await_execution` waits for the execution to report completion — and
`setupviewv2` still answers with the old value for a while after that. The poll
replaces the capability list in one go, so the value that was just written is
overwritten by the stale one, and the entity goes back to where it started
until the next poll a poll interval later.

Toggling air circulation on a room air conditioner shows it plainly : the
switch reads on, then off, then on again thirty seconds later. Reported on
model 557 on 2026-09-13, against 2026.9.8.

So a write the cloud confirmed is held in `_pending_writes` and re-applied
after each poll, until the setup view reports the same value — at which point
the entry is dropped and the API is the source of truth again. It is a
tiebreaker, not an override : nothing is held that the API has agreed with, and
a value changed in the Cozytouch app still wins the moment the hold is gone.

`PENDING_WRITE_GRACE` is 60 seconds, which is a guess. Nothing measured how
long the propagation actually takes ; the number only has to outlast it while
staying short enough that a write the cloud accepted and then quietly ignored
stops being shown as the truth. Two default poll intervals is the reasoning,
and the only evidence is that the flicker is gone at that value.

The alternative was to drop the refresh that follows each write, which is a
smaller diff — thirteen deletions. It was not taken because the refresh is what
brings the *derived* values along : the remaining time and the mode the unit
locks itself into while air circulation runs are not what was written, and
nothing else would fetch them for a poll interval.

### `connect()` is idempotent, and a failing login is not collapsed

`online` is the whole reconnect mechanism, and every hub on the account flips it
and calls `connect()`. Re-checking it once the lock is held is what keeps a
*successful* reconnect from costing one login per device — five coordinators on
one beat make one request.

A failing one is deliberately not collapsed : a failure leaves `online` False,
so each waiter in turn takes the lock, sees that, and tries again. That is right
for a network failure and wrong for a refused password, which no number of
attempts fixes and which repeated *failed* logins could get an account locked
out for. So `InvalidAuth` is the one exception `connect()` does not fold into
`online = False` : it propagates, and `connect_or_auth_failed` turns it into
`ConfigEntryAuthFailed`, which Home Assistant answers by opening the reauth
dialog and by not rescheduling the coordinator that raised it — "ask once"
rather than "retry the rejected password every minute for as long as the
installation runs". `tests/test_reauth.py` pins the one-retry-per-waiting-hub
limitation that is left.

### A 429 backs off without dropping the connection

`_note_rate_limited` deliberately does not touch `online`. Every other failure
here drops the connection so the next poll re-authenticates, which for a 429 is
exactly backwards : the token is fine, and reconnecting spends a
`POST /users/token` and a `GET setupviewv2` on an account that just asked for
*fewer* requests. Repeated failed logins are also the one thing that can lock an
account out, so answering a throttle with a login loop is the worst move
available. The backoff is checked before the lock and before the login for the
same reason.

`RATE_LIMIT_BACKOFF` is 300 s and is a guess : Atlantic has never been observed
sending a 429, because nothing in the integration used to recognise one. It is
deliberately long — the cost of waiting five minutes too long is stale values,
the cost of waiting too little is being throttled for good. `Retry-After` is
read as seconds per RFC 9110 ; the HTTP-date form no gateway here sends falls
back to the default rather than throwing inside a poll.

`RATE_LIMIT_HEADERS` are logged rather than parsed, at warning level on purpose.
WSO2 API Manager, which `docs/api-surface.md` identifies as the gateway, is the
likely source, and those headers are what would say what the limit actually is —
the one thing no capture has ever established about `rateLimit`. The first
person to see a 429 is holding the only evidence there is.

### `invalid_grant` is the only answer that means the password is wrong

OAuth2 spells it that way and Atlantic uses the standard spelling. Anything else
malformed is a bad response, not a bad password : telling somebody their
password is wrong because the gateway hiccuped sends them off to reset a
password that was fine.

### The setup view is the poll

The same request `connect()` makes, called on a beat rather than once : it
carries a capability list for **every** device on the account, so one request
refreshes the whole account where the per-device route refreshes one device. It
also carries `absence`, which lives nowhere else — an away window set in the
Cozytouch app used to wait for a reconnect to be seen.

What it does not carry is proof of being as fresh as
`/magellan/capabilities/`. The two are the same three fields and the integration
has always built its entities from this payload at startup, but nobody has
compared their latency. `modificationDate` is in both and read by neither, so
the measurement is there to be made — `scripts/probe_api.py --cadence` makes it.

`last_poll` moves only on a success : a skipped or failed poll leaves it
standing, which is what makes it readable as "how old is what the entities
show".

### An expiring token just drops the connection

There is no separate retry loop anywhere : flipping `online` is how every
failure path here asks for a reconnect, and an expiry is another one, seen a
minute early.

### `API_DECLARED_FIELDS` are carried, not read

Nothing decides anything from them. They are carried because a diagnostics dump
is what a mapping gets built from, and the vendor's own name and family for a
model the table does not know is the first thing worth having. On the one
account these were read from, only the gateway carries a real `longName` and a
`modelFamily` — its children report an internal name or a literal `---`, and the
name the user actually typed is `customName` — so what other product families
put here is still open.

`SETUP_WRITABLE_FIELDS` is the subset the away-mode PUT has to send back :
`absence` is what the call is for and `id` addresses the resource, so neither
belongs in the body.

### The setup view refreshes every device, not just the one that asked

It carries capabilities for all of them, and this used to drop all but one —
which cost the account a per-device poll before its entities could be built, and
left a diagnostics dump describing the hardware nobody has mapped yet without
the capability ids that are the whole point of the dump. Zones and
`API_DECLARED_FIELDS` are refreshed on every view rather than set once at
creation, for the same reason : `isAvailable` moves as a device drops off its
gateway, a renamed zone has to reach the entity names it feeds, and a device
renamed in the app should not keep its old `longName`.

### A write waits for its execution

A write is not fire-and-forget : the POST answers with an execution id, and the
state of that execution is polled — once immediately, then up to five more times
a second apart — until it reports 3. Returning False means the local value must
stay as it was, and the next poll will say what actually happened.

A write is attempted even while the account is backing off from a 429, unlike
the polls : somebody just pressed a button, and refusing to send it because a
*reader* was throttled would be a worse answer than letting the server refuse
it. A 429 here still arms the backoff, so the readers learn from a write's
rejection. The execution loop is the burstiest thing the integration does — up
to six requests in five seconds for one button press — so it is the likeliest
place to meet the limit, and the last place to keep hammering after meeting it.

`fetch_capabilities` raises rather than returning a sentinel : the caller is a
coordinator, and an empty list is a legitimate answer that must not read as a
failure. Every failure but a 429 also drops `online`, which is what asks for the
reconnect.

### The absence window is a setup resource

Away mode is the one feature that is not a capability write alone : the window
lives on the setup, a resource of the account rather than of a device, which is
why it is on the account and not on the hub.

### Zones are not offered when adding devices

A THZONE is one zone of a ducted heat pump, not hardware : it reports no climate
capability, no setpoint, and two ids that resolve to nothing, so adding it would
create a device with an empty page behind it. The model comes from the table
rather than from the `modelInfos` filled in when a device first appeared — the
same lookup every other caller makes, and the name a zone is recognised *by* can
change under a cached one. The raw setup view still holds the zones, and the
`dump_json` option writes it out.

`get_unmapped_models` runs over the whole account rather than one device : the
setup view lists them all, and one report that covers everything is one issue
for the person who has to write it. It goes through the name-aware lookup too,
or a THZONE reads as an unknown product and the repair asks for a dump about it,
once per zone.

### A zone with no name reads as None, not as its id

Every caller puts the result in front of somebody — a device name, a line in a
diagnostics dump — and `Zone (1030104)` is a worse name than no name at all :
the id is ours to join on, not a room anybody recognises. The callers decide
what to show instead.

### Three exception types, because they want opposite handling

`CannotConnect` is retried until the network comes back ; `InvalidAuth` never
resolves without somebody typing a new password. `CozytouchRateLimited` is a
subclass of `CozytouchApiError` so a caller that only cares that the call failed
keeps working ; what it adds is `retry_after`, and what it does not do is touch
`online`.

## `custom_components/cozytouch/repairs.py` and `diagnostics.py`

### Why the integration asks, rather than waiting to be told

A device the model table does not know still gets entities — the generic
capabilities work — but the specifics are missing and its name reads
`Unknown product (…)`. The user has no reason to connect that string to anything
they can do about it, so the fix always depended on someone thinking to open an
issue and attach a diagnostics dump. The repair asks at the one moment it is
obvious the mapping is missing, and hands over a report that is already written.

The dump is the same information one click away from the integration page, with
the account details already taken out. Asking for it by hand cost the reporter
an option to tick, a log file to find and a JSON to redact, and that is where
most reports stopped.

### The form requires screenshots of the app

The report used to ask for two things, the ids and a diagnostics dump, and
describe what the app offers in prose. Both are what a device *reports*, and
neither says what a person can actually do with it. The mapping has to say
which raw value is which mode, and whether a capability is worth an entity at
all -- and a device reporting a capability does not mean the app exposes it.

Guessing from the numbers has been wrong more than once. Room units behind a
Navizone report an eco capability the app never shows, and were offered one
for months. A heating circuit slot shipped as a towel rack (issue #93) on a
guess nobody could check. In both cases the app's own screen would have
settled it in a glance.

So the form asks for three screenshots and makes them required: the home
screen, which is the only view of how the appliance is grouped and named --
one appliance often reports itself as several devices, and nothing in the API
says which of them a person is meant to see ; each device's own screen ; and
the screens behind it, the mode picker, the schedule, the settings.

The field itself says the three and one line of why, and nothing more. A form
nobody finishes reading is a form nobody fills in, which is the whole of what
it has to avoid ; the argument above is the reason it is required, not text to
put in front of somebody who is already reporting a bug.

The repair dialog says three things rather than two to match, in all six
translation files. It is the dialog that gets read, the form that gets filled,
and one contradicting the other costs the round trip the form exists to save.

### One report per account, covering devices nobody added

`_account_report` reads one account rather than scanning the entry store, and no
longer depends on which devices somebody added : the setup view carries a
capability list for every device on the account, so an unmapped model
contributes its capability ids whether it has a subentry or not. That used to be
the half of a report that was missing exactly when it mattered — hardware nobody
has mapped is hardware nobody has added yet. Any hub answers for any device on
its account, since the mapping is keyed on the model.

Several devices can share one unmapped model, and a silent one must not
overwrite what a talkative sibling reported.

Likewise one dump per account, covering every device the setup view returned. It
used to take one dump per device, which is a file per device to find, download
and attach for a report that needed all of them.

### The report URL carries ids and nothing else

Deliberately only the model ids and the capability ids nothing names : those are
what a mapping is built from, and they say nothing about the household. Values
stay out — among them the wifi SSID (219) and the gateway serial — and so does
the device name, which people call after a room or a child. A URL is clicked
without being read. The dump the form asks for carries all of that, stripped,
and is attached knowingly.

The query keys after `template` are the ids of that form's fields, which is how
GitHub fills them in. Renaming one in `.github/ISSUE_TEMPLATE/` breaks the link
quietly — it just arrives empty — so the two move together, and
`tests/test_repairs.py` checks that they still match.

### The issue is keyed on the model, and asked once

A pair of identical towel racks asks once, which has to be recognised while
walking the account rather than left to the issue registry to overwrite : the
second device would replace the first one's name and ask about the same mapping
twice. `REPORTED_MODELS` is written by the fix flow and read on every setup,
across every entry — the model stays unmapped until a release maps it, so
without it the issue would come back at each restart at someone who already did
their part, and one report speaks for whoever else owns the same hardware.

The issue is cleared on the way through as well as raised : a release that adds
the mapping is the expected end of it, and the setup that follows the update is
where that shows.

The report is read when the dialog opens rather than stored on the issue, so a
device that gained a capability, or an entry added since, is in what somebody is
about to send. Answering it closes the repairs raised for the other models it
covered ; the one the flow belongs to is deleted by Home Assistant.

### Thermal zones are asked about too

Nothing separates a zone from a real device nobody has mapped yet : the
gateway's id sits in `masterDeviceId` on both, and `modelFamily` is null on
both. Any rule would be a guess, and the two ways of being wrong do not cost the
same — a zone reported is an issue closed in seconds, a real device silenced is
someone never finding out why their hardware is half-supported.

## `custom_components/cozytouch/device_trigger.py`

### Two gaps, and nothing else

Home Assistant already builds device triggers out of the entity domains a device
happens to have : the connectivity binary sensor gives "connected" and
"disconnected", the away-mode switch gives "turned on", the climate entity gives
"HVAC mode changed". Nothing there reaches the weekly program, and the program is
what these devices are scheduled by — it keeps running when Home Assistant is
off, which is the whole reason the two schedule services exist.

So this module fills two gaps and no others :

- the program is seven diagnostic sensors, one per day, that no entity groups,
  so "the heating program changed" has no entity to be triggered on ;
- `climate.device_trigger` offers `hvac_mode_changed` and the two current-value
  triggers and no preset trigger at all — and the preset is where prog, override
  and basic are reported.

There is deliberately no `device_condition.py` and no `device_action.py`. The
`climate` domain already ships both for presets : "Cozytouch is set to prog" is
a condition Home Assistant writes itself, and setting one is a climate device
action. Adding ours would put two entries with the same meaning in one picker.

Both kinds are offered only when the device reports what they read : a water
heater with no cooling program gets no cooling trigger, and a device whose
climate entity has no prog preset gets none of the three. Which presets exist is
on the entity and not in the registry, so a climate entity with no state yet
answers for none of them — the same read `climate.device_trigger` makes.

The trigger list follows the programs the schedule services know : a program
nothing can read back is not one an automation should be told changed.

### Both halves fail silently, which is why they are tested

A trigger that never fires logs nothing. `tests/test_device_trigger.py` pins
which triggers a device is offered and what each one then watches.

- A schedule trigger carries no `entity_id` : a program is seven sensors, and
  which seven is a question about the device rather than about any one of them.
  It resolves to registry ids rather than entity ids, so an entity that gets
  renamed keeps working.
- A day sensor that is merely unreachable has not been reprogrammed, so the trip
  through unavailable and back is ruled out at both ends. Ruling both ends out
  also turns it into a state-value trigger : with no `to` or `from` at all, the
  state trigger fires on attribute changes too, and a renamed entity would read
  as an edited program.
- A preset trigger watches the `preset_mode` attribute and not the state : the
  state of a climate entity is its HVAC mode, and a setpoint change would fire
  it.
- `for` is offered on the preset triggers only. "Overridden for two hours" is a
  thing to automate on ; "changed for two hours" is not, since a program that
  changed does not change back.

### A sensor's capability id is the tail of its unique id

Sensors are keyed `cozytouch_{subentry_id}_{capabilityId}`, and a subentry id
carries no underscore. The two away-mode timestamps are the exception,
`{subentry_id}_0` and `{subentry_id}_1`, and 0 and 1 fall outside every program
block, so they rule themselves out.

## `custom_components/cozytouch/datetime.py`

### A room reads the absence window, it does not set it

The 2026-08-28 setup view of a Navizone has the away window on the gateway as
capability 222 — `[1786658400,1787954400]` — and the same pair, to the second,
on the room slot as 100260. 100260 had no row at all, so it fell through as an
unnamed id and only appeared with "create entities for unknown capabilities"
switched on. It is mapped now, with the same `AWAY_MODE_TIMESTAMPS` reading as
222 and 226.

What the room does not report is a switch: neither 152 nor 227, only 100261,
which reads whether the absence is on and is a binary sensor. That matters
because nothing in a datetime entity commits anything — `set_away_mode_start`
and `set_away_mode_end` stage the value on the hub, and the write happens in
`set_away_mode_timestamps`, which the away-mode *switch* calls when it is
turned on. A room would therefore have got two date pickers that accept a date,
show it, and send nothing: a control that fails silently, which is worse than
no control.

So the datetime platform builds the pair only for a device that also reports
one of the ids the table types as `AWAY_MODE_SWITCH`. The set is derived from
the table rather than listed, so an away-mode switch mapped later brings its
pickers with it and a device that reports timestamps alone keeps reading them
as two sensors.

The timezone id stays 315 on the room's row although no room reports it:
`get_capability_value` answers "0" for an id a device does not carry, which is
the offset a missing timezone should mean.

## `custom_components/cozytouch/config_flow.py`

### One entry per account, one subentry per device

The account is what the credentials buy — one login, one setup view — and the
devices are what somebody actually wants entities for, added at setup time or
later from the integration page.

That shape is also why reauth is one dialog and one write, with no loop over
sibling entries : the credentials exist in exactly one place, and reloading that
entry brings every device on the account back with it. Before the reauth path
existed, a changed Cozytouch password left the account retrying the old one for
as long as the installation ran, saying only that it could not connect. The
username is not asked for again — changing it would point the entry at a
different account, which is an entry to add and not a password to fix.

`validate_input` raises `InvalidAuth` for a refused password and `CannotConnect`
for an account that could not be asked, and the caller shows a different message
for each : "check your password" is unhelpful advice during an outage.

The device list is read once on the way into the subentry step and kept across
the submit : the step is re-entered to answer the form, and logging in again to
resolve the id somebody just picked would double the cost of adding a device for
nothing.

### Only the device id travels in a picker option

It used to be a whole dict — credentials included — serialised with `str()` and
read back with `ast.literal_eval`, which put the account password in the form
the browser posts.

### All three options are account-wide

`dump_json` always was, since there is one `Cozytouch.json`. `create_unknown`
follows it rather than earning a reconfigure flow per device for a setting used
to work out what a value means. `poll_interval` has to be : there is one poll
for the account, so a per-device interval would describe something that does not
exist.

## `custom_components/cozytouch/translations/`

### Five languages, and why these five

The catalogue says where the hardware goes. Water heater ids carry the badge in
the name — `AE` is Austria Email, `THE` and `TH` Thermor, `SA` Sauter, `ATS`,
`NEU` — and one boiler id reads `Naema Micro 25 Cuerpo Caldera`, in Spanish. A
model sold into Austria rather than Germany is its own id (2375/2376). So
Spanish, German and Italian were added next to English and French. Those are
commercial names, though : they come from the catalogue and stay verbatim in
every language, so none of this reaches `strings.json`.

The three files were generated by substituting values into `en.json`, which is
why the key order and the column alignment match it line for line. The
generation refused to write a file with an English value left in it, so the
parity the tests check was true before they ran.

What they are not is the wording of the Cozytouch app in those languages : the
glossary below is general HVAC vocabulary, picked once and applied throughout.
A native speaker who owns the hardware will have corrections, and that is the
expected way these improve.

| English | es | de | it |
| ------- | -- | -- | -- |
| DHW | ACS | Warmwasser | ACS |
| Override | Anulación | Übersteuerung | Forzatura |
| Air circulation | Circulación de aire | Luftumwälzung | Circolazione dell'aria |
| Tank | depósito | Speicher | serbatoio |
| Resistance | Resistencia | Heizstab | Resistenza |

Boost, Prog, Powerful, Eco+ and V40 are product terms and stay as they are.
`[%key:common::…%]` references are left alone : Home Assistant resolves them per
language, and rewriting one would replace a translated string with ours.

### The tests glob the directory

`strings.json` heads the list as the reference the others are compared against;
the rest is `translations/*.json`. Four test files carried the same hard-coded
triple, so a sixth language would have been complete in the UI and unchecked in
CI — which reads exactly like passing. The glob means a contributed file is
held to the same completeness on arrival, and every capability added afterwards
has to fill it.

### The air circulation is a fan, declared on its own row

Air circulation is one thing the hardware does -- blow air, at a speed -- and
was three entities: a switch on 102024, a speed select on 102004, a duration
on 102021. None of Home Assistant's fan vocabulary reached it: not the card,
not the voice assistants, not the `fan.*` services.

It is a fan now, and the ids live on the row rather than in the platform:

    102024: Entity(
        name="air_circulation",
        type=CapabilityType.FAN,
        extra={"speedCapabilityId": 102004,
               "modelList": "AirCirculationSpeeds"},
    ),

`fan.py` knows no capability id at all, so a second device whose fan is some
other pair of ids costs a row and no code. The duration is deliberately not on
that row: a Home Assistant fan has no notion of one, so 102021 stays the
`DURATION_SELECT` it was, beside the fan rather than inside it.

The speeds come from the model (`AirCirculationSpeeds`), which is what turns
the API's `1`, `2`, `3` into the 0-100 Home Assistant speaks -- 33, 66, 100.
A model naming no speeds still gets a fan; it runs or does not, rather than
being given an invented scale.

Two readings are chosen rather than inherited. A fan that is off reads 0%,
not its last speed, so a card's slider agrees with the state beside it. And a
speed asked of a stopped fan starts it, in that order, rather than storing a
setting that visibly does nothing.

Migration 2.4 is what stops the three lines being four. The switch is
**removed** from the registry -- the switch platform no longer claims 102024,
so the entry would sit unavailable forever, which is the same reasoning as 2.3
and capability 312. The select is **disabled** instead, once and not per
start, because that entity still exists and somebody who wants the dropdown
back can have it. A removed entity cannot be re-enabled; a disabled one can.

What this costs: an automation pointing at the old switch stops working, and
says nothing when it does. That is the same trade 2.2 made for the per-day
program sensors, and the reason the entity is removed rather than left to rot
is that an unavailable entity is a worse silence than a missing one.

## `custom_components/cozytouch/llm.py`

A weekly program is the thing in this integration a person is most likely to
want to say out loud -- "hold 21 in the morning", "stop heating the bedroom
after ten" -- and the least likely to want to click through seven days for.
Home Assistant's `llm` integration platform is what makes that possible
without anything registering anything : the `llm` component imports
`<integration>/llm.py` from every loaded integration and asks it for tools.

The two tools are deliberately **not** the two services.

`set_schedule` writes a whole day, because a whole day is what the device
stores : ten slots, the first at 00:00, and writing one replaces the lot.
Handing that to a language model means asking it to copy the eight slots it
was not asked about back out, unchanged, every time. It will usually manage.
The time it does not, the day that gets written is the day it remembered, and
nothing in Home Assistant can tell that apart from a day somebody meant. That
is a heating program silently losing its evening, found a week later.

So the writing tool is a *period* -- entity, program, days, start, end,
temperature -- and the merge happens in `apply_period`, in Python. The model
says what to change; what not to change is not its problem. The reading tool
stays raw, since reading cannot lose anything.

`apply_period` is in `services.py` rather than here for two reasons : it is
the same operation `calendar.async_create_event` already performs when an
event is drawn over a day, and it has to stay testable on an install too old
for the `llm` platform. It is not yet wired into the calendar -- that path
has its own pinned behaviour around overlapping events, and changing it is a
separate change with its own evidence.

Three rules it enforces that the raw service cannot :

- the slots the period covers are *replaced*, not kept, or a slot inside the
  period would take charge in the middle of it
- the slot closing the period carries what was in charge there before, which
  is what makes "21 until 17:00" leave 17:00 onwards alone
- a slot asking for what is already running is dropped, because a day holds
  ten and one that changes nothing is one fewer for a period that would

Midnight as an end means the end of the day. A person saying "22:00 to
midnight" is describing the last stretch of the day, and the last slot of a
day already runs to its end, so there is nothing to put back after it.

Days that come out identical are written in one call : the service refreshes
the device once per call, and "every day" would otherwise be seven refreshes
for one sentence.

Exercised on 2026-09-17 against a real conversation agent (OpenRouter, Home
Assistant 2026.9.2) : reading a program back and writing a period both work,
on heating and on cooling. The first call there is what produced the device
list in the prompt -- the model asked for `climate.clim_chambre_parents`, the
entity being `climate.chambre_parents_clim_chambre_parents_climatisation`.

The platform is newer than the Home Assistant version `hacs.json` declares.
Nothing guards the import, and nothing needs to : an install without the
`llm` component never imports this module. What does need saying is that
`tests/test_floor.py` imports every module, so `llm` is named as absent from
its list, and `tests/test_llm_tools.py` skips itself where the platform is
missing.


## `custom_components/cozytouch/www/cozytouch-schedule-card.js`

The calendar came first and is the wrong shape for this. Home Assistant's
calendar card draws a week as a diary : one column per day, events as boxes,
and the setpoint typed into an event's *title* because a calendar event has
nowhere else to put a number. It works, and every one of those is a
concession. Nothing stops a title being "lunch", and nothing shows Tuesday and
Wednesday differ at a glance.

A 7×24 grid came second, and was built as far as painting a span with the
pointer. It reads beautifully and it edits badly, for one reason that never
went away : a cell is an hour and a device stores slots, so every gesture had
to be translated. Painting one hour meant writing that hour *and* a second
slot to close it, a day holds ten of them, and the ceiling arrived without
warning in the middle of an edit. What the grid was good at -- seeing the
shape of a week -- is not what somebody opens the card to do.

So the card is the list the device actually holds. A day is its slots, each
one a chip carrying the two things a slot is : when it starts and what it asks
for. Ten chips is the ceiling, and ten chips is what you see. The grid is in
the history if it is ever wanted back.

Closed, the card is one line : what the program is asking for at this minute,
on today's day. That is what a dashboard is read for -- the week is what it is
opened for, so it sits behind a click. The reading is `inChargeAt` on today's
slots, which is already what the calendar and the editor agree on, and the
clock comes from the browser rather than from a timer : nothing is focused
while the card is closed, so redrawing on a Home Assistant state update keeps
the head current without the card owning an interval. A card left open on a
dirty day stays open whatever the caret says, since a hidden Save is a lost
edit.

### Why it ships inside the integration

`nielsfaber/scheduler-card` is the obvious alternative and cannot do this. It
schedules from Home Assistant : it calls `climate.set_temperature` when a
cron-ish trigger fires, so the program lives in Home Assistant's database and
stops when Home Assistant stops. This card writes capabilities 196-202 or
203-209 through `cozytouch.set_schedule`, which is the program the device runs
on its own. The distinction is not academic -- a house heats correctly through
a Home Assistant upgrade only in the second case.

That is also why the card is a file in `www/` served by the integration,
rather than a separate HACS frontend plugin. The card and the service it
writes through are one thing; shipping them apart means a version pair that
can be wrong, and a second HACS repo to keep for one file. The static path is
registered once per Home Assistant, not per config entry.

### Served, not loaded

`add_extra_js_url` would load it automatically, and is the sanctioned way to
do that -- its docstring in `frontend/__init__.py` says in as many words that
it exists for custom integrations, and no core integration calls it. It is
still not used here. It loads the file on *every* frontend page for *every*
user of the installation, and this card is for the households that edit a
program, which is not all of them. 11 KB is nothing; a script in everyone's
page that most of them will never render is not nothing.

So the integration serves the URL and stops there. Somebody who wants the
card adds `/cozytouch/cozytouch-schedule-card.js` as a dashboard resource,
once. That is one manual step at install against no cost for anyone who skips
it, and it is the step every HACS frontend plugin asks for anyway.

The card is served by a `HomeAssistantView`, not by a static path, for one
header. `async_register_static_paths(cache_headers=False)` sends *no*
`Cache-Control` at all -- `_serve_file` in `http/server.py` returns a bare
`FileResponse` -- and a browser given no instruction caches on its own
heuristic. The symptom was a card that had been replaced on disk still drawing
the old grid after a hard reload, which reads exactly like a failed copy. The
view answers with `Cache-Control: no-cache`, so the browser revalidates and
gets a 304 for the usual case.

The alternative was a `?v=` carrying the manifest version, which works only
while the integration writes the url itself -- here the user typed it, and an
update must not need them to retype it.

### The rules the list enforces

`checked` refuses what `build_matrix` refuses, on the spot rather than at
Save : two slots at the same time, and a day that no longer begins at 00:00.
The reason to duplicate the check rather than let the service answer is that
Save writes a day at a time, so a refusal on Thursday arrives with Monday to
Wednesday already written.

The 00:00 chip has no remove button at all, rather than a button that always
refuses. Its setpoint is editable like any other, which is what somebody
reaching for its remove button actually wanted.

A day holds ten slots, mirroring `MAX_SLOTS` in `services.py`, and the `+`
disables itself on the tenth with the reason in its tooltip. It does **not**
read capability 306 : the frontend has no hub, and 306 only ever tightens the
ceiling, so the worst case is the service refusing what the card allowed.

`addSlot` puts a new slot in the middle of the longest stretch the day leaves
empty, rounded to the half hour, holding whatever was already in charge
there. Adding a slot therefore changes nothing until somebody sets it to
something, which is the only behaviour that cannot surprise -- and the widest
gap is where a slot is most likely wanted.

The times are `<input type="time">` and the setpoints `<input type="number">`.
Both bring the platform's own picker and the phone's own keyboard, and the
time input displays in the browser's format while its value stays `HH:MM`,
which is the format `set_schedule` takes. The minute precision is the device's
own : the grid could only ever write on the hour.

Edits are local until *Save*, and only the touched days are written. A day
edited back to what it already was is not marked dirty. Writing on every
keystroke would be an API call per chip, against an API that answers a poll
with 429 often enough that `hub.py` has a backoff for it.

### The card's own language

`hass.language` is the language the user picked in their profile, and it
arrives with every `hass` assignment. The day names come from
`Intl.DateTimeFormat` with it. The times need no help at all : an
`<input type="time">` already displays in the browser's format, which is how
the same card reads `7:00 AM` in English and `07:00` in French without the
card knowing either.

The words that are not dates -- seven of them, plus three refusals -- sit in a
`STRINGS` table in the card, in the five languages `translations/` ships. That
duplicates a mechanism the integration already has, and the reason is that the
frontend cannot reach it : Home Assistant serves an integration's translations
to the frontend under a fixed set of sections, none of which is "a card's
buttons", and inventing one fails hassfest. A table of seven words against a
fetch and a schema fight.

The refusals `checked` and `addSlot` throw carry a `code`, since the message
they raise is written in English and the card says it in the reader's
language. Anything coming back from Home Assistant or the network is repeated
as it arrived.

### The colour scale

A chip is tinted by its setpoint, across the setpoints the program actually
uses rather than the card's `min` and `max`. A week between 19 and 21 would
otherwise be three shades of the same blue, which is exactly the week somebody
opens the card to inspect.

It interpolates between three fixed colours -- blue, sand, red -- rather than
sweeping a hue. Sweeping was the first version, and a week of five setpoints
came out as a rainbow : blue, green, yellow, orange, red, with green reading
as its own category rather than as one step warmer than blue. The middle stop
is sand and not grey because grey is what a chip with no setpoint would be
drawn in, and on most weeks the middle stop is the setpoint the week mostly
sits at.

Two setpoints, which is what most programs have, land on the two ends and the
middle never shows.

### What is not tested by CI

`tests/test_schedule_card.mjs` holds `writeSlot`, `addSlot` and `inChargeAt`
to the rules above and runs under `node --test`. CI has no javascript job and
is not getting one for three functions, so it is run by hand. The three are
exported, and the class extends a `CardBase` that falls back to a bare class
outside a browser, purely so that file can import them without a DOM.

The rendering is not covered there, and was checked instead by loading the
card into headless Chrome against a stubbed `hass`, driving the real inputs
with real events and reading back what the day became. That harness is not in
the repository : it is fifty lines of scaffolding for a check that is run when
the card changes and never otherwise.

## The service is one house's, and the write is one room's

Capability 7 is the service an air-conditioning room runs -- off, heat, cool,
auto, dry, fan -- and the climate entity wrote its mode there for as long as
there has been one. On a system with more than one room that is wrong, and
visibly so : the outdoor unit runs one service, so a mode set on one room from
Home Assistant left that room drying while the two others cooled, and ten
minutes later the house was still split. The Cozytouch app never does that.

What the app writes, captured off the iOS client on a three-room Naviclim
account, 2026-09-21 :

| Gesture | Write |
| ------- | ----- |
| the service dropdown | `{"capabilityId": 102020, "deviceId": <room>, "value": "8"}` |
| switching a room off | `{"capabilityId": 7, "deviceId": <room>, "value": "0"}` |
| switching it back on | `{"capabilityId": 7, "deviceId": <room>, "value": "3"}` |

**102020 is the system's service**, and writing it on any one room carries
every room of the system with it -- which is the propagation that could not be
found anywhere else. 7 is the room's own state, and the only value that is
genuinely the room's is `0`. Switching a room back on writes the service the
house is already running, never one of its own, which is why turning a room on
*into* a different mode is two gestures there and one write pair here.

So `async_set_hvac_mode` writes 102020 when the device reports it, 7 when the
mode is off, and both when a room that was off is asked for a mode. A device
with no 102020 -- a boiler, a towel rail -- keeps the write it always had.

### What it is not, which took the whole investigation

The app's call was assumed to differ from ours, and every way it could was
probed with `research/probe_write_service.py` before the capture settled it.
None of these is the difference, and none should be tried again :

- **The body.** `{capabilityId, deviceId, value}`, the three fields we send.
- **The route.** `/executions/writecapability`, the one we use.
- **The headers.** The app adds `X-Operation-ID`, `uniqId`,
  `appInstallNumber` and its own `User-Agent`. Sent byte for byte : the room
  changed, the house did not.
- **The device.** Only the rooms implement 7, and the backend decides that by
  `productId` : the hub answers 404 `NoCapabilityImplementationFound` on
  product 96, the thermal zone on product 65.
- **Time.** Ten minutes, unchanged.
- **A refusal we did not read.** The execution reports `state 3, execution
  Done`, and a re-read from the backend gives the room's own value back.
- **A second write in the app.** Nothing overrides `writeCapability` in the
  Android sources, and every service write goes through one call.

The Android app was the map throughout, and it is where the answer was hiding
in plain sight : its enum names 102020 `AIR_MIXING_ACTUAL_MODE`, this project
copied that as `air_circulation_current_mode` until this was found, and the
entry above about the capability corpus records it reading 3 and says *"not
obviously one member either, so it stays raw"*. Its values are the `Service` space exactly -- `0`
off, `3` cool, `4` heat, `7` fan, `8` dry. A name taken from the vendor is
still a guess about meaning.

The row is `system_service` now, in all six translation files. The vendor's
own name is kept in a comment above it, because a report quoting
`AIR_MIXING_ACTUAL_MODE` still has to lead here.

### Capability 91 is which circuit is active, named for that rather than the valve

Reported against an Alfea Extensa Duo S (September 2026): capability 91 is an
int, and the app shows 1 while the unit is heating the underfloor circuits and
3 while it is heating up the domestic hot water tank instead. It is a system
mode, not a reading of the DHW loop's own state the way capability 230
(`dhw_operating_mode`) is -- physically it tracks the 3-way valve that sends
the heat pump's output to one loop or the other, but the row is named
`active_circuit` for what the value means rather than for the part that
produces it, so it keeps reading straight whichever of the open guesses below
turns out right. The valve stays in the comment on the row, since it is
Atlantic's own word for the mechanism and the one a future search is likely
to look for. Both readings are confirmed against the app on that one report ;
0, 2 and anything above 3 are not, since nobody has caught the valve there
yet.

2 is left out on purpose rather than guessed. Two candidates were raised and
neither is confirmed : a cooling circuit, or -- since this is the Duo, sold
with two underfloor heating circuits -- the second of those rather than the
first. Nothing here picks between them ; whichever a report confirms first is
what `reads_as` gets.

Mapped as `reads_as={"1": "heating", "3": "domestic_hot_water"}` rather than
the placeholder shape (`STRING`, `DIAG`, no `reads_as`) CLAUDE.md asks for
when nothing is known, because here two members are : an unconfirmed 0 or 2
just falls through `describe_capability_value` to `None` and the entity reads
as the raw number, same as a value a `bits` row does not name. `category=DIAG`
and `enabled_by_default=False` stay the defaults for a partly-verified row,
the same shape 230 uses for the same reason.

### The override duration is a list of hours, not a slider

Capability 158 was a number entity in hours, which Home Assistant draws as a
slider: a bar with no marks, the entity name truncated to make room for it,
and a value that can be dragged to 1.4 hours. The Cozytouch app offers whole
hours from one to twenty-four and nothing between, so the slider promised a
precision the device does not have and spent a card row saying so.

It is a `DURATION_SELECT` now, on the same grid the app offers -- 60 to 1440
minutes by 60 -- which is the same control the air-circulation duration
beside it already uses, and which puts the name on its own line.

The raw value was always minutes: the old class divided by 60 to display and
multiplied back to write, and the select writes the minutes an option stands
for. So the device sees the same numbers it always did.

A name is looked up under the section of the platform that registered the
entity, so moving a capability between platforms moves its translation too :
the three `override_total_time*` keys went from `number` to `select` in all
six files, and until they did the entity read as `override_total_time_z1` on
the card. `test_every_name_is_translated_under_its_own_platform` is new for
that -- the completeness check beside it unions every section, so a key filed
under the wrong one always satisfied it. There are no bounds to read from the
device, either : the app hardcodes them, `MAX_MINUTE_VALUE = 1440` and
`MINUTE_SCROLL_STEP = 60` in `BaseCircleDeviceViewModel`, and the capability
enum has a min/max/step trio for air mixing (102022/102025/102026) and nothing
of the kind for the override.

`HoursAdjustmentNumber` had no other row, and `tests/test_capability_coverage.py`
is what said so -- it holds the types the platforms consume and the types the
mapping produces to the same set, and failed the moment 158 moved. The class
and its `CapabilityType` member are deleted rather than left waiting for a
second user.

## Capabilities 160 and 161 are bounds, not controls

`temperature_adjustment_max` (161) arrived as a writable number with a
hardcoded 19-28 range, while its counterpart `temperature_adjustment_min`
(160) was a plain sensor. The pair reads as one thing and behaved as two.

Nothing ever said 161 was writable. The Cozytouch app shows no control for
it : on a room air conditioner it reports exactly 28, which is the ceiling
the app applies to its own setpoint slider. That is what the pair is -- the
window the setpoint may move in, which the app reads and never offers. A
number entity over it writes into the void at best.

So 161 becomes a `TEMPERATURE` sensor like 160, its invented bounds go, and
its translation moves from the `number` section to `sensor` in all six
files. Both are `enabled_by_default=False` : a bound nobody reads yet is
diagnostic, and it was showing up on cards as a thermostat you could drag.

## What the Android app is willing to write

Nothing on the wire says a capability is writable. `CapabilityEntity` is
`(capabilityId, value, modificationDate)` and `WriteCapabilityInput` is
`(value, deviceId, capabilityId)` -- no flag either way, which matches what
`capability.py` receives. There is no read-only bit to read.

What the app has instead is its own call sites. `IGacomaDevice` exposes
`getCapabilityValue` and `writeCapabilitySuspend`, both taking a
`Capabilities` enum member, so every capability the app ever writes appears
as a literal next to a write call. Collecting them gives 87 ids, recorded in
`research/data/android_writable_capabilities.tsv` :

    grep -rh writeCapabilit sources/ | grep -v @Metadata |
      grep -oE 'Capabilities\.[A-Z_0-9]+'

Read it as a lower bound with one gap : jadx folds a few enum values into
unrelated constants it found with the same number (`NSType.TKEY` for 249,
`ScanQRCodeFragment.IOT_HUB_ERROR_RESULT` for 198), so six ids are recovered
from their neighbours in the enum's declaration order rather than read off.
An id absent from the list is not proved unwritable -- it is only never
written by this version of the app, 3.31.0.

Against our own mapping that leaves six capabilities we offer as controls and
the app only reads : 22, 41, 42 (`target_temperature_dhw` and the two eco
setpoints), 152 (`away_mode`), 104047 (`boost_timeout_max`) and 105907
(`v40_setpoint_filled_by_user`). None is on hardware anyone here has, so they
stay as they are until somebody reports one writing into the void. Two ids
run the other way -- 100801 and 100803, ventilation speed and shutter
position, which the app writes and our table does not name at all.

This is what settled 161 : it is read by `ITemperatureFeature` and appears at
no write call site.

## Two things the app does with capabilities we only read

The sweep of the Android app (September 2026) found no missing ids worth the
name -- of the 183 capabilities its feature interfaces read, three are absent
here. What it found instead is behaviour: ids we name, type and then use
less than the vendor does. Two of them are cheap enough to be worth taking
on their own.

### 100078 is a control, and `winkable` says where

`identify_request` was a diagnostic binary sensor everywhere.
`ISettingsFeature` both reads and *writes* it -- `writeWink(true)` makes the
unit announce itself so somebody standing in the room can tell which of three
identical boxes they are looking at. In the app's device list the button is
labelled `report` while idle and `stop` while the unit announces, and it is
the only control in that card using either string. `startWink` awaits the
write and returns `Result.isSuccess`, so the label only turns over on a
server that took it.

Which products get it is not something the device reports.
`GacomaDeviceFactory` picks a class from the pair (own `productId`,
parent's) -- the same rule the rest of this integration already lives by --
and each class carries the answer as a constant. So `model.py` grows
`winkable`, which reproduces it:

| product | class | winks |
| ------- | ----- | ----- |
| `BD0` (41) | `GacomaBD0` | yes |
| `TD1` (53) | `GacomaTD1` | yes |
| `AIR_CONDITIONER_UI` (31-40) | `GacomaAirConditionerUI` | yes |
| `TH_ZONE` (65-94) behind a Navizone, ZoniClim or Split 3S hub | `GacomaTransverseUI`, which extends the above | yes |
| `TH_ZONE` behind anything else | the factory builds none | no |
| `ROOM` (26-30, 97-111) behind a bare air conditioner | `GacomaAirConditionerRoom` | no |
| `ROOM` behind a hub | `GacomaTransverseRoom`, not a settings device at all | no |
| everything else | `GacomaAirConditioner`, `GacomaHDG2`, `GacomaZoniClimHub`, `GacomaThermostatDarwin`, `GacomaCesaV2Generator` | no |

The flag is set only where it is true, the way the other optional flags
work, so it changes 422 model ids out of 2500 and `tests/test_model.py` said
exactly which -- the towel racks, the air conditioner interfaces and the one
radiator.

Two wrong turns are worth keeping, because both are the mistake capability
161 was. The first put the switch on every product: the app hides it on
most. The second put it on `CozytouchDeviceType.ROOM`, reasoning from a
screenshot of the reporter's settings screen showing the button on three
cards named after his rooms -- but the cards in that list are the physical
boxes, `TH_ZONE` devices labelled by their place, and the `ROOM` ids are the
steering slots behind them. Reading a device type off a label is not reading
a `productId`.

The `Atlantic*` classes -- `AtlanticElectricalHeater`,
`AtlanticElectricalTowelDryer` -- also say true and are deliberately not
here. They are `Device` instances, and for those `startWink` calls
`startIdentify(120)` rather than writing anything: 100078 is not the
mechanism, so a switch over it would write into the void.

What the write *does* is a separate question, and the honest answer is that
nobody here knows. It was accepted on the reporter's account and the wall
unit in that room did nothing anybody could see or hear. Either the
indicator is somewhere he was not looking, or the vendor's own control is
decorative on this hardware. The switch ships because the vendor ships it
and the server takes the write ; it does not ship because anyone watched a
light blink. `enabled_by_default=False` is doing some work here.

It stays off either way. The read-only twin sensor.py builds for every
switch keeps the reading that was there before, so the name needs an entry
in the `switch` section *and* the `sensor` one -- which is what
`test_every_switch_key_is_also_a_sensor_key` is for.

### 103150 says whether the ambient reading means anything

`ROOM_AMBIENT_TEMPERATURE` (117) is what the climate entity shows as the
current temperature, and it was shown whenever the model declared
`currentTemperatureAvailable` -- a static flag, decided once per model id.
The app asks the device instead: `isCurrentTemperatureAvailable()` reads
capability 103150 at each poll, and shows no temperature when it is false.

The difference shows up on hardware whose sensor stops reporting. The static
flag cannot know, so the entity keeps the last good number for good, which
on a dashboard is indistinguishable from a live one. `_climate_entity` now
wires `currentAvailableCapabilityId = 103150` where the device reports it,
and `current_temperature` reads None while it says no.

Silence is not a no, deliberately, and twice : a device that does not report
103150 at all is believed, which is every device that predates it, and a
poll that carries the id with no value is believed too. Only an explicit
`"0"` hides the reading. The alternative -- treating absence as unavailable
-- would blank the temperature on every device in the fleet the day the
capability were mistyped.

### The third one, not taken

103034 `room_controls_capabilities` is a mask whose only named bit is
`ANTIFROST = 16`, and the app gates its antifrost control on it. Gating
`antifrost_temperature` (103199) the same way would add nothing: the mapping
already builds it only for a device that reports 103199, and a device
without the feature does not report it. The bit is recorded in
`research/data/android_bitfields_331.tsv` for the day something needs it.

## Atlantic named eleven capabilities, and two of ours were wrong

`gduteil/cozytouch#146` corrects two tank temperature names against a list
Atlantic itself published. We carried the same two, inherited from upstream.
The provenance and the eleven ids are in `docs/api-surface.md`; what follows
is what the table does with them.

### 264 and 267

264 was `condenser_temperature` and 267 was `tank_bottom_temperature`. There
is no condenser reading: 264 is the bottom of the tank and 267 is its
average. 265 and 266, middle and top, were already right.

Our own corpus settles it without needing to trust anybody. On model 1368,
264 reads 48.50, 267 reads 52.22 and 266 reads 53.36 -- bottom below average
below top, on one device in one poll. A condenser sitting between the middle
and the top of a tank's own water, every time, is not a reading anyone would
defend. The upstream PR adds live behaviour from a ST CUBE WIFI WM 100L: 264
falls toward inlet temperature during a draw, which is what the bottom of a
tank does and what a condenser does not.

Unique ids are built from the capability id, so an existing install keeps its
entities and its recorder history. Only the displayed name moves -- and it
moves to the truth, which means a dashboard that said "bottom" for 267 was
already reading the average and nobody could tell.

### The four that were missing

234, 278, 281 and 288 are on Atlantic's list and had no row at all. They have
one now, with the name Atlantic gave them.

Only 234 claims a type. "Consigne de temperature de l'eau en mode Boost" is a
temperature, the corpus reads 55.0 on a tank whose setpoints live in that
range, and that is enough for a `TEMPERATURE` row.

The other three arrive as the unverified-encoding row the house rule
describes -- `STRING`, `DIAG`, off by default. 278 is the one that hurts:
"puissance electrique instantanee du ballon" is obviously a power reading and
there is no `POWER` type here to give it, but the corpus holds exactly one
sample of it and that sample is `0`. Nothing in that distinguishes watts from
kilowatts from deciwatts. Naming a unit off a single zero is the failure this
project has a rule against, so the row carries the name and waits for a
reading. 281 and 288 are a demand and a state whose encodings nobody has
seen; one corpus reading each, `0` and `2`.

### What was read and not taken

Issue #129 also records that a capability which disappears from the cloud
reads as `0.0` here rather than as unavailable, because
`Hub.get_capability_value` defaults to the string `"0"` when an id is not in
the device's list. That is still true in this fork, and it is why the May
outage showed every affected tank sitting at 0 °C instead of going blank.

It is left alone here on purpose. Changing the default touches every sensor
on every platform, and telling a real zero from an absent id is exactly the
kind of change that wants its own diff and its own tests. It is the next
thing to do in this area, not a rider on this one.

## The vendor's capability catalogue

Found 2026-09-22. `docs/api-surface.md` carries what it is and which routes
answer; this is why the tables here are not simply replaced by it.

Atlantic's WSO2 devportal serves every API's OpenAPI without authenticating,
and `Magellan_ProductModels` 1.9 declares
`GET /magellan/productmodels/capabilities`. A private-person token reads it:
405 capabilities with name, description, type, unit, bounds, enum members and
an `accessType` bitmask. `capability_table.py` was reverse-engineered from one
user's dump and from the Android app, so this is the first time any of it can
be checked against what the vendor says.

### It is a check, not a replacement

Three reasons the table stays hand-written.

The catalogue names the *capability*, not the *entity*. `ROOM1_AmbientRoom` is
an internal identifier; `thermostat_temperature_z1` is a translation key with
five language files behind it and dashboards pointing at the entity id it
produces. Renaming 228 rows to match Atlantic's spelling would break every
existing install and buy nothing.

It says nothing about which device reports what. `absent_on`, `needs_flag` and
`per_type` exist because the same id means different things on different
products, and `?productid=` narrows the catalogue by product but does not say
that a radiator reads 100506 differently from an air conditioner.

And it is not complete. Three ids the integration ships -- 233, 103450 and
104047 -- are absent from it, all three seen in real dumps. A capability in a
device's report and not in the catalogue is the catalogue being behind, not
the device being wrong.

### What it is authoritative about

The encodings. A bitmask capability is declared as an enum whose Keys are the
bit values, so every `bits` tuple in the table is checkable against it, and
the first check found one inversion and eleven missing bits. Same for
`reads_as`, for units, for bounds, and for `accessType & 4`, which is the
vendor's own list of what may be written -- 217 of the 405, against the 87
inferred from the Android app's write call sites.

Where the catalogue and the table disagree on an *encoding*, the catalogue
wins. Where they disagree on a *name*, the table wins.
### The bits the catalogue filled in, and the one it did not settle

Three rows named one bit each and read the rest as `unknown (N)`, because one
bit each is what a corpus of real values happened to show. The catalogue
declares their whole sets, and on every one of the three the bit already named
agrees with it, so these are gaps and not corrections:

- **224 `dhw_estimation_supported`** -- 2 `water_flow` was right; the other six
  are water, cold water and hot water temperatures, the V40 tank, its energy
  and its power.
- **103034 `room_controls_capabilities`** -- 16 `antifrost` was right; light,
  restriction, central heating and baby care join it.
- **188 `home_services`** -- the first four were right; 256 is away mode.

**100004 and 100021 are left alone**, and that is the interesting one. The
catalogue says bit 1 is `HygroControl` and bit 2 is `TemperatureControl`. The
Android app says the opposite, and says it as literal masks rather than as a
declaration order:

    TEMPERATURE_IS_CHECKED(1),
    HYGROMETRY_IS_CHECKED(2),

Two first-party sources, flatly contradicting each other on two bits. The app
wins here for two reasons. It is what renders the screen a reporter compares
against, so matching it is what makes a bug report legible. And it knows two
bits the catalogue does not -- 64 and 128, the blade positions -- which says
the catalogue's row is the stale one on this particular capability.

Nothing is flipped until a device reports a value that tells them apart: a
unit with hygrometry and without temperature control, or the reverse. Until
then the reading stands as the app has it, and this paragraph is why.

Which qualifies the rule above. The catalogue wins on an encoding where it
is the only source. Where the app contradicts it, the disagreement is the
finding, and neither side is applied on its own authority.

## The catalogue in the diagnostics dump

A dump is what a device report is built from, and until now its capability
section was a list of bare numbers: these ids are named, these are not. The
vendor's catalogue is one request away and answers what every one of them is,
so the dump carries it.

### Every id the account reports, and only those

Two wrong versions were written before this one, and both are worth stating
because each is the obvious answer to the other's failure.

An id nobody has named produces no entity, which is visible the moment someone
looks for it. An id named **wrongly** produces an entity that looks perfectly
fine and reads the wrong thing -- a duration typed as a temperature, a setpoint
whose unit is not what the row claims, an enum member off by one. Nothing in a
dump has ever made that visible, and nothing would, unless the vendor's type,
unit and enum members sit beside ours to be compared against.

So describing only the gaps is out. But the answer to that was "describe all
405", and that is wrong in the other direction: the catalogue covers Atlantic's
whole range -- boilers, heat pumps, ventilation, tanks -- and on the account
this was measured with, 91 of the 405 are reported and the other 314 describe
hardware nobody there owns. Shipping them puts the same two hundred kilobytes
of identical rows in every report on earth, and the catalogue is one request
away for whoever reads it.

What the dump carries is the vendor's answer for **every id the account's
devices actually report**, mapped and unmapped alike. Once for the account
rather than under each device, since two rooms of one installation report the
same ids. One request per dump, never on the poll, and a failure caches empty
and moves on.

Each row is cut down to what a reader needs: the internal name, because that
is what a report can be searched for; the description, because that is what
says what the thing is; the type as a word; whether bit 4 of `accessType` is
set, because writability is the first question asked about an unmapped id and
guessing it wrong is how a control that writes into the void gets shipped; and
the unit, bounds and enum members only where the catalogue states them. A key
present and empty would read as "Atlantic says there is none", which is not
what a null field means.

An id the catalogue does not carry gets no entry, and that is a reading too:
three ids this integration ships are absent from it, all three seen in real
dumps.

### The notice that asks for the file

A dump only helps if somebody sends it, and nothing asked. `repairs.py` now
raises one notice per account when any device reports an id the mapping does
not name -- one for the account and not one per device or per id, because the
answer to all of them is the same single file.

It opens the device report form rather than the issue list. Somebody arriving
from a notice has not decided to write a report yet -- they were told by Home
Assistant -- and a bare list of issues gives them nothing to do. The form is
what says which three things an answer needs, and it now says in its first
paragraph that a notice is a legitimate way to have arrived at it, because
"some capabilities are not named yet" does not sound like "an entity you
expected is not there", which is how the form describes itself.

A second template was considered and dropped: it would have asked for the same
device, the same screenshots and the same file, and a fork in the road is one
more place for a report to end up in the wrong half.

Its text says what the *file* carries, not what the file carries about these
particular ids, and that distinction is the whole of it. The first version
said the dump holds Atlantic's name, description and unit for each id it names
-- true today, since most unmapped ids are in the catalogue, and false the
moment the mapping catches up with it. What is left unnamed then is precisely
what the catalogue does not carry either, and the notice would have been
promising a section that is empty for exactly the ids it fires about. It now
says the file holds what each device reports and what the catalogue says about
the ids it knows, which is true in both worlds.

It is not fixable: there is nothing Home Assistant can do about a missing row.
It says which ids, says plainly that this is a gap in the mapping rather than
a fault on the hardware, and points at the diagnostics download. It clears
itself the moment the mapping names the last of them, which is the whole point
of raising it.

The cost is that an account with unmapped ids now shows a notice it did not
show before, and most accounts have some. That is the trade accepted: the
alternative is the current state, where the people whose hardware is half-read
are exactly the people who never find out.


### Suppressed is not unmapped

`get_capability_infos` has two ways of declining. `None` means nothing in the
mapping knows the id. An empty `CapabilityInfos` means it is known and
deliberately not an entity *here*: a `needs_flag` the product does not have,
an `absent_on` covering its type, a `valid_above` the reading fails, an id in
`SUPPRESSED_CAPABILITIES`, or one of 1, 2, 7 and 8 on a product that reports
it without steering on it.

Both are falsy, and the split that feeds the dump read them the same way. So
a decision was filed as a gap. On the account this was found with, three of
the thirteen "unnamed" ids had rows: 171 and 172, the absence setpoints an air
conditioner reports and does not honour, and 100507, the eco mode the app does
not offer on a room. The notice then asked for a report about ids that had
already been reasoned about, in writing, in this file.

The dump now lists all three groups, and the notice counts only the last. A
suppressed id is listed rather than dropped, because "nobody has named this"
and "somebody decided this" are different answers and only one of them is a
report worth opening.

## Eight ids named from a live account and the catalogue

A dump taken on 2026-09-22, from a HUB Navizone with three room air
conditioners and three ducted zones, reported thirteen ids nothing named.
Three of them had rows and were misfiled (see above). Two are the subject of
their own entries. The remaining eight get rows here, and every one of them is
named from the vendor's catalogue rather than from a reading: the name, the
description, the type, the bounds and the enum members are all Atlantic's.

All eight are `DIAG` and off by default, because a dump proves what a device
*reports*, never what the app lets you *do* with it. None of them is written.

- **17 `ROOM1_ControlSetpoint`** -- the setpoint actually in force, which is
  not always the one asked for: 40 is what somebody set, 17 is what the
  program or an override left running. A heat pump already steers its first
  zone on this id, and there the climate entity claims it before the row is
  reached, so the row only surfaces on products that report it without being
  steered on it.
- **341 `ROOM1_ThermostatOperatingMode_AutoValue`** -- what the thermostat is
  really doing while the setpoint mode is Auto. Its `1` is `Unavailable`,
  which is what it says when the device is not in auto at all, and that is not
  the same as off.
- **347 and 348** -- how many schedule transitions the thermostat can hold,
  daily and weekly. Capability limits rather than readings, which is why they
  are diagnostics and not sensors.
- **100014 `DEVICE_DeviceType`** -- what the device calls itself. A reading
  and not a source: it answers 255 `Unknown` on the ducted zones of an account
  whose hardware `model.py` types perfectly well from its `productId`. Absent
  on zones, which keeps the rule that a zone maps to nothing at all.
- **100100 `Asked_Thermal_Comfort`** -- the mode that was asked for, beside 7
  which is the one running. Two of its eleven members are the vendor's own
  French -- `10 Arret`, `11 Marche` -- and the same account reports the
  literal string `None` on it, which is why it is read and never written.
- **103014 `ROOM_Type`** -- an integer with no enum in the catalogue, so it is
  surfaced as the number it is.

### 103026 says what drives a room, which we had written off as unknowable

`capability.py` says, above `_room_entity`, that nothing a room slot reports
tells you whether the room holds a radiator or an air conditioner, and the
class is built to let the capabilities decide. The catalogue names 103026
`ROOM_ThermalGeneratorCapabilities`: *"Indicates the type of generator linked
in the thermal zone associated to the Room"*, with nine members --
air-to-water heat pump, boiler, air-to-air split, panel heater, towel dryer,
floor heater and two I2G variants.

The account it was found on reads 8, air-to-air split, on all three rooms,
which is what its hardware is.

That is one observation, all of it one kind of gateway, so nothing is rewired
on it here. The row reads the value as a sum -- the members are powers of two
and the name is plural, so a room may sit in front of more than one generator.

And on a second look it buys less than the paragraph above `_room_entity`
makes it sound, which is worth writing down before somebody spends a day on
it. The modes are already narrowed by 100022, so a room that does not declare
cooling does not offer it. The capabilities are already asked for one by one
rather than assumed, so a room without a boost gets no boost. And a room being
called a room, with a neutral icon, is deliberate: it is what the vendor's own
client does, and a room is a room whatever heats it.

What is left is `_AC_ROOM`, which every room inherits regardless of what
drives it -- a `quietModeAvailable` that belongs to an air conditioner, and an
`ecoModeAvailable: False` decided for the rooms behind a Navizone. A room
driven by a boiler or a radiator carries both for no reason. That is the whole
of what 103026 would fix, and a report saying "there is a quiet mode that does
nothing" would find it just as well.

So it stays a diagnostic. If a dump from a room behind a radiator ever shows
16, 32 or 64 on it, the change is to skip those flags in `apply_capabilities`,
where 100022 and 106000 are already read, and nothing else moves.

### A capability the chain steers on still needs a row

`_climate_entity` wires ids onto the climate entity -- a fan speed, a louver
position, a zone's setpoint -- and `get_capability_infos` is asked about each
of those ids separately, for the reading that sits beside the entity. Three of
them had no row: 18, 100801 and 100803.

With no row the answer is `None`, which means "nothing in the mapping knows
this id". So a capability the integration understands well enough to *steer
on* was filed as one nobody had ever named: it landed in a dump's unmapped
list, and after the notice was added it would have asked its owner to report
it.

It went unseen because the account it would show up on is one with a Fujitsu
indoor unit reporting a fan speed. The rooms behind a ZONICLIM do not report
100801 or 100803 at all, and no heat pump with a second zone has sent a dump.

`tests/test_capability_coverage.py` now scrapes `capability.py` for the ids it
wires and asserts every one of them has a row. It is a scrape rather than a
list, so a new `somethingCapabilityId = N` is covered the day it is written,
and it asserts the scrape found something before asserting what it found --
a regex that silently stops matching would otherwise pass forever.

The three rows are Atlantic's own: 18 is room 2's setpoint in force as 17 is
room 1's, 100801 is one fan speed (not 350, which names a whole *set* of
speeds), and 100803 is the six flap positions of a Fujitsu indoor unit plus a
zero the vendor itself calls unknown.

## The 631 models that were past the end of the sweep

`model_catalogue.py` was built by asking
`GET /magellan/productmodels/models/{id}` for one id at a time, over
`range(1, 2500)`, because that is what a sweep can do when it has no list to
ask for. The vendor has a list: `GET /magellan/productmodels/models` answers
2299 models in one call.

Two things came out of comparing them. Every id the sweep found is in the
list, with the same name, so the sweep was right about what it reached. And
the list carries **631 models the sweep never reached**, 645 of its ids
sitting above 2500 -- the ADELIS, ATLANTIC and Saturnia ranges, id 2994 to
3652. Every one of them read as `Unknown product (…)` until now.

All of them carry `productId` 0, so nothing here types them; they are typed
from the `modelFamily` a real device sends, which is what that column is for.
What this adds is the name, which is the difference between a device page
headed `Unknown product (3117)` and one headed `ADELIS LINE 1500W BEIGE`.

The walks in `test_capability.py` and `test_snapshot.py` moved with it, from
`range(1, 2500)` to `range(1, 3700)`. Nothing above 2500 is branch-mapped
today, so the mapped set does not change -- but the bound was a sweep's reach
rather than a decision, and a branch added above it would have been walked by
nothing at all.

### The 33 product ids that are still not classified

The same run answered `GET /magellan/productmodels/products`: 123 products
with a name and a family, against the 90 ids `PRODUCT_TYPES` covers. The 33
left over are whole classes -- radiators (8, 9, 10, 23, 42, 43, 48, 116, 117),
towel dryers (11, 12), thermodynamic water heaters (13 to 17, 20, 45, 119),
electric water heaters (18, 19, 118), double-flow ventilation (22, 24), a
ventilation unit (21), and the SIF generators (50, 51, 52) and bridges (114,
115, 120).

They are deliberately left out, for the reason `MODEL_FAMILIES` already gives
about `Double_Flow_Ventilation`: a `PRODUCT_TYPES` entry needs a
`DERIVED_TYPES` row beside it, and that row is a device type *and a set of HVAC
modes*. Naming the type is easy and guessing the modes is not, and a device
that grows entities it cannot drive is worse than one that arrives typed from
its `modelFamily` -- which is what all of these do today, since the families
the products sit in are the families that column already names.

The products table is kept as the check it is: it confirmed the ROOM block
runs 97 to 111 and that there is no gateway at 98, which is its own commit.

### Four enums the catalogue decodes, and one rename

Four rows carried a name and a type and let the value through as the number it
came as, because nothing said what the number meant. The catalogue declares an
enum for each.

- **120** is the rename. It was `boiler_or_heat_pump`, which offered two
  answers to a capability Atlantic calls `ProductType` and gives twelve
  members: the whole range, from a convector to a double-flow ventilation unit
  to a zone controller. The name asserted a choice the field does not make, so
  it is now `product_type` and reads the member. It is a diagnostic and off by
  default, so the rename costs a display name and no history.
- **288** `DHW_stWaterHeaterServiceStatus` -- off, off with frost protection,
  on, on reduced. Four states where a reading of 1 used to be a 1.
- **351** is read as a *sum*, not looked up: the name is plural and the one
  member the catalogue declares sits on bit 1.
- **100300** `ROOM_idxStartOfWeek` -- which day the thermostat counts a week
  from, Sunday being 0. Worth having as a word rather than a number, since
  reading a weekly program depends on it.

## Naming the catalogue, family by family

The vendor's catalogue declares 405 capabilities and the table names 240 of
them. The rest are being added a product family at a time, from the
catalogue's own name, description, type, unit, bounds and enum members rather
than from a capture -- which is a better source than most of the existing rows
have, since those were reverse-engineered from one household's dump.

Every row added this way is `DIAG` and off by default. The catalogue says what
a capability *is*; it says nothing about whether the vendor's app lets anybody
do anything with it, and that is still the difference between a control that
works and one that writes into the void. None of them is writable here, whatever
`accessType` says.

### The units Home Assistant already had

The generated rows turned up units the mapping had no type for -- a burner's
flame current in µA, a flow rate in l/min -- and the first pass dropped them
to a plain reading, which shows a current as a number with nothing beside it.

Home Assistant covers one of the two at the version `hacs.json` declares.
`VOLUME_FLOW_RATE` has had L/min all along, so `FLOW_RATE` joins
`CapabilityType` and no custom unit is invented.

µA it does not: `UnitOfElectricCurrent` on 2025.12.0 is `mA` and `A`, and
`MICROAMPERE` arrives later. A `CURRENT` type was written, and the min-floor
job in CI refused it -- which is the job doing exactly what it is for. The
three ways out were a unit the floor does not know, a division by a thousand
that invents a reading, or raising the floor of the whole integration for one
burner's flame current. None of them is worth it, so 47 is a plain reading and
carries a pointer saying why. It becomes a current the day the floor moves for
a reason of its own.

`_unit()` in `sensor.py` now reads `displayed_unit_of_measurement` off the row
rather than fixing the unit per type, the way `_energy` already did for Wh
against kWh. One device class covers several units and the vendor picks per
capability -- kW on one power reading and W on the next -- so the unit belongs
on the row. Home Assistant rejects a unit its device class does not cover,
which is what keeps the override honest.

A type is added with the rows that produce it and not before:
`test_no_platform_waits_for_a_type_nothing_produces` fails otherwise, and it
is right to. The units with no device class at all -- dl/min, cts/kWh -- stay
plain readings.

### The Boiler family, ten ids

Two of them are the vendor's own French inside an English enum: `65 FanStatus`
declares `arret` and `marche`, where `66 DHWCirculatorStatus` beside it
declares `Off` and `On` for the same two states. The entity states read `off`
and `on` for both. An entity's state is not where a vendor's inconsistency
belongs.

`67 QGenFlowFromBurnerPump` is named `generator_flow_from_burner_pump` here.
Its unit is dl/min, which Home Assistant has no unit for, so it is a plain
reading rather than a flow rate converted on a guess.

### The Water Heater family, ten ids

Six of the ten are smart grid: the level the grid is asking for, whether a
power request is live, the power setpoint that comes with it, whether the
cloud has an API to receive requests at all, which of the five request kinds
the tank supports, and whether self-consumption is running. Atlantic spells
`SG` where it means smart grid, and the rows spell it out.

**310 `DHW_ThermalGeneratorCapabilities`** is the tank's half of 103026: what
heats this tank, as a sum -- electric heater, heat pump, boiler. A tank with a
resistor and a heat pump reports both, which is what makes it a sum rather
than a choice.

Three names were not taken from the generator that derived the rest.
`DHW_bSGAPIConnected` came out `dhw_sgapi_connected`, which reads as a word
nobody would search for. `DHW_tWaterSetpoint` is not the setpoint -- 22
already is -- it is the one that applies when no override is running, so it
says that. And `DHW_AbsMinWaterSetpointLimit` is the lowest the setpoint may
be set to, which is shorter said than spelled.

### The Heat Pump family, thirty-six ids

The largest family so far, and the first where the generator's names were all
replaced by hand: it produced `heating_power_consumption_extra1_state` and
`room_comfort_cooling_target_temperature_state_z1`, which say the same things
as `extra_heating_power_z1` and `target_temperature_comfort_cool_z1` and match
nothing else in the table. The zone suffix follows the `_z1`/`_z2` the mapping
already uses.

What they cover: the compressor and its counters, the three external inputs
and what each is wired to, the mixing valves, the backup electric heater in
its two stages, the directional valve and the boiler contact on a hybrid, the
cooling setpoints per zone and per profile, and two consumption counters.

Four value tables are the vendor's own French, and read in English here:
`Arret`/`Ouverture`/`Fermeture` on the mixing valves, `Entree EJP` and
`Entree Heures Creuses` on the external inputs. A fifth thing they do is write
an unknown reading as three dashes, `---`, which reads as `unknown` -- and it
is the *zero* on two of the tables and the last member on another, so the row
is what says which.

`27 HoursRunCompressor` uses `TIME`, which already *is*
`SensorDeviceClass.DURATION` in minutes -- a `DURATION` type was written
beside it before anybody noticed the one that existed had a different name.
The row states seconds instead, which is what the per-row unit above is for.
`58` and `60` are in kWh where the energy type's usual unit is Wh, the same
way the rows that already existed do.

**Id 8 is deliberately not here.** The catalogue calls it
`HeatingPowerConsumptionExtra2State`, a power in kW. `capability.py` treats 8
as one of the four ids that can carry an HVAC mode, and a model that steers on
it gets a climate entity from it. Both cannot be true of the same product, and
which one holds is decided per model by `HVACModesCapabilityId` rather than by
the catalogue. A row would be unreachable wherever the chain claims it and
wrong wherever it does not, so 8 waits for a device that reports it.

`180 ErrorCodeUE` is left undecoded. Its enum is forty-odd entries of the form
`11:Serial communication error`, which is a code and a sentence in one string
and belongs with the fault table in `faults.py` rather than in a `reads_as`.

### Room 2's comfort setpoint was called its eco one

Capability 42 has shipped as `target_temperature_eco_z2` since the table was
written. It is room 2's **comfort** setpoint. Two independent sources say so,
and they were both available before the mistake was made.

Atlantic's catalogue names 42 `ROOM2_ComfortHeatingTargetTemperatureState`,
against 41 `ROOM1_EcoHeatingTargetTemperatureState` which the table gets right.
And the capture corpus settles it without reading a name at all -- on model
211, across four separate captures:

    41 = 15.0    58773 = 20.0
    43 = 15.0    42    = 20.0

41 and 43 pair at the low value, 42 and 58773 at the high one. Eco is the low
one. So 41 and 43 are the eco setpoints of rooms 1 and 2, and 58773 and 42 are
their comfort ones.

The consequence for anybody with a two-zone PassAPC is that the number called
"Target Temperature Eco Z2" writes the comfort setpoint, and there has been no
eco entity for room 2 at all. Both are fixed here: 42 is renamed, 43 takes the
name it should always have had, and 58773 arrives as room 1's comfort setpoint.

What the rename does not fix is the entity id. Home Assistant builds it once
and keeps it, so an existing install goes on calling 42
`number.<device>_target_temperature_eco_z2` while the friendly name and
everything written about it say comfort. Renaming the entity is the owner's
call, and the alternative -- leaving the wrong name in place because the id
would be stale -- is how a wrong reading becomes permanent.

### The two Fluid-TES families, twenty-three ids

The generator itself and the legacy generation beside it: the DHW service type
and its comfort and eco setpoints, the circulators, the nominal heating and
DHW powers, the second zone's flow temperature and setpoint, its programme
mode and override, the away period's two dates, the fuel tank's capacity and
the RSSI quality.

`342` is the SIF generation's own comfort setpoint and says so in its name,
since 254 already holds the same idea for the rest of the range.

Ids 1 and 2 are in this family and are **not** taken, for the reason 8 was not
taken in the Heat Pump family: `capability.py` treats 1, 2, 7 and 8 as the
four ids that can carry an HVAC mode, and a model that steers on one gets a
climate entity from it rather than a row.

### Everything outside SIF, forty-three ids

The BASE and Hybrid families and the thirty-six ids no family declares at all,
which is most of this batch. Being in no family does not mean being unused --
`DEVICE_ZigbeeMacAdress`, the boost durations, the outside-temperature
compensation curves and four energy prices are all in it -- it means the
catalogue's family list is a partial index rather than a partition.

Two tables are now shared rather than repeated. **359** declares the same nine
members as 103026, the room's thermal generator, so both read
`_THERMAL_GENERATOR_BITS`; the vendor's `Reserved` on bit 1 is left out,
because naming a reserved bit promises it means something. **400** is the
interfaces a device speaks, also a sum: wifi, zigbee, io-homecontrol,
bluetooth, opentherm, modbus.

`107078 GENERATOR_BoilerSwitchType` declares three members and labels two of
them `COP`. Both read `cop` here. The catalogue cannot tell them apart and
neither can this.

The four prices are in cts/kWh, which has no device class, so they are plain
readings. The fuel consumptions are in dm³, which is a litre exactly, so they
are volumes with nothing converted.

`100340 ROOM_OccupancyScheduleSunday_` is a struct and arrives raw: it holds a
start time and an extension, and no capture here has one to check a decoding
against.

This leaves the SIF family, fifty-nine ids, which is the whole of what is left.

### The SIF family, forty-one ids, and the end of the pass

The last of the catalogue. What is left after it is 1, 2 and 8, and those are
the chain's, not the table's.

Ten of the forty-one are `HOME_FirstErrorCodeTable` through
`HOME_TenthErrorCodeTable`: a fixed ten-slot list of active faults, beside the
count in 182 and the most important one in 328. They arrive as numbers. The
fault table in `faults.py` decodes 150, and whether these ten carry the same
encoding is a question for a device that reports one, not for a row.

**210 to 216 look like a program block and are not.** Seven consecutive
capabilities, Monday first, named `DHW_ComfortScheduleMonday` and so on: the
exact shape `PROGRAM_BLOCKS` holds for 196, 203 and 237. The structures
endpoint says otherwise. The three blocks the calendar builds from use struct
1, `ScheduleTransition`, which is a time and a setpoint. These use struct 3,
`ScheduleTimetable`, which is a start and an end and carries no temperature at
all. They are comfort *windows* rather than setpoint transitions, and the
calendar platform, the program sensors and the writing services all assume the
other shape. So they are plain readings, and adding a fourth block to
`PROGRAM_BLOCKS` would need a decoding nobody has a capture for.

The heating curve comes with its two anchor points named after the outside
temperature they are measured at -- the flow temperature at -10 °C and at
20 °C, and two more for cooling at 25 °C and 35 °C -- which is how the vendor
names them and how an installer reads a curve.

### What the pass covered

Every capability in Atlantic's catalogue now has a row, 405 of them, against
the 240 the table held when it started. Nothing that was added is enabled by
default and nothing is writable: the catalogue says what a capability *is*,
and what the vendor's app lets anybody *do* with it is still only answered by
a screenshot.

Three ids are deliberately outside it. 1, 2 and 8 are among the four the chain
reads as carrying an HVAC mode, and a row for one would be unreachable wherever
the chain claims it. Three more go the other way -- 233, 103450 and 104047 are
in the table and not in the catalogue, all three seen in real dumps -- which is
what the notice about unnamed capabilities now means: not "nobody has got to
this yet" but "no source names this, Atlantic's own included".

## `accessType` answers a different question than "can this be a control"

The catalogue carries an `accessType` bitmask -- Read 1, Refresh 2, Write 4 --
and declares 217 of its 405 capabilities writable. The table exposes 63 as
something somebody can set. Nothing about that gap is going to be closed by
reading the field, and here is why.

**It is wrong in the negative.** Two capabilities this integration has written
since before any of this carry `accessType 3`, no write bit: `22
DHW_WaterSetpoint`, the hot water setpoint, and `152 HOME_AwayModeStatus`, the
away toggle. Both work. So the field does not list everything that can be
written.

**It is misleading in the positive.** `172 HOME_AwayHeating` carries
`accessType 7`, and the entry above about the absence setpoint was written
before the catalogue existed: an air conditioner reports it, stores what is
written to it, and never reads it back. The API accepted the write. The
hardware did nothing. That is the definition of a control that writes into the
void, and the field said yes to it.

What `accessType` answers is whether the *API* will take a write. What decides
whether an entity should offer one is whether the *device* acts on it, and
those are different questions. The one endpoint that would answer the second --
`GET /magellan/capabilities/{capaId}/devices/{deviceId}`, the per-device write
rule with `isReadOnly` and the bounds for that device -- is 403 on a
private-person token.

So the 157 capabilities the catalogue calls writable and the table only reads
stay read-only. Turning them on from this field would reproduce the 172 case a
hundred and fifty times over, and each one would look like a working control.

The rule does not change: a capability becomes writable when a screenshot of
the vendor's app shows the control, or when somebody reports that the one we
shipped does nothing. The dump now carries `accessType` per capability, so
that conversation starts from what Atlantic claims rather than from a guess --
which is all the field is good for.

## Issue #121 : an Hybrellia the integration could only half drive

One report, one dump, three separate causes. Nothing here is Hybrellia-only
-- all three are seams that any device of the same shape would hit.

### A weekly program is stored in one of two places

`PROGRAM_BLOCKS` named one first capability per program: 196 for heating, 203
for cooling, 237 for hot water. The Hybrellia's room slot stores its heating
week at **100320-100326** and its cooling week at **100327-100333**, and
reports nothing at 196 or 203. `_reports_the_whole_block` therefore found no
block, built no calendar, and `set_schedule`/`get_schedule` refused the
device -- so the fourteen per-day sensors were the only view, and read-only.

The rest of the machinery was already ready for these ids:
`THERMOSTAT_PROG_IDS` in `capability.py` covers `range(100320, 100334)`, and
`parse_slots` ignores the third element of the `[minute, setpoint, 0]`
triplets they carry. Only the address was missing.

A program is now a tuple of candidate runs, and `stored_in(program, reports)`
picks the one a device holds all seven days of. The runs are tried in order
and the first whole one wins: no dump has ever shown a device reporting two,
and if one ever does, the older address is the one every other reader already
assumes.

Two call sites do not need the device to answer. `hidden_by_a_calendar` and
the 2.2 migration walk every candidate, since they ask about ids rather than
about one device; `device_trigger.py` takes the union for the same reason --
a device holds exactly one run, so the union matches the sensors it has and
nothing else.

`set_schedule` is stricter than it was as a result: it used to write the
block whatever the device reported, and now refuses a device that reports
none of the runs. That is the same condition `get_schedule` already applied,
and the writes it drops were going nowhere.

### The hot-water setpoint bounds are 253 and 252

Capability 22 read its range from 160/161 and 231 from 105301/105304 -- ids a
room slot reports and a tank does not. Both fell back to the generic number
defaults, so the two hot-water sliders offered a range the tank never
claimed.

The Android app settles it. `IDHWFeature.getMinUserTarget()` and
`getMaxUserTarget()` read `DHW_MIN_USER_TARGET` and `DHW_MAX_USER_TARGET`,
which `Capabilities.java` declares as `NSType.MAILB` and `NSType.AXFR` --
jadx resolving the literals 253 and 252 against a DNS constant table that has
nothing to do with this app. `CesaV2SteeringView` feeds exactly those two
into `setMinAbsoluteTarget`/`setMaxAbsoluteTarget`. The dump agrees: 253 = 45,
252 = 65.

That was already known for one model id, 2374, through a `per_model` entry.
It is a `per_type` on `WATER_HEATER` now, which covers 2374 and every tank
after it.

`per_model` was that entry's only user, and it is gone with it. Keying a row
on a model id is the mapping this project spent PR #112 getting out of: the
vendor's app dispatches on the device class, so an id-keyed row is a list
that grows by one with every report and says nothing about why. Every
override left on a row keys on what a device *is*.

### What the app decides to show, and what we did not take

Worth recording since it was read anyway. `DHW_IHM_CAPABILITIES` (336) is a
bitfield -- `V40_STATE_OF_CHARGE = 1`, `MAIN_TEMPERATURE_SETPOINT_CURSOR = 2`,
`SECONDARY_TEMPERATURE_SETPOINT_CURSOR = 4`, `IHM_DATA_INSIDE = 8` -- and the
app gates each piece of its water-drop screen on one bit, the two cursors
additionally on 86 not reading OFF. The reporter's 336 is 10, so the app
shows one setpoint cursor and no eco cursor and no charge gauge.

Nothing was gated on it here. A capability an entity is built from is already
the condition for that entity existing, and 336 would only add a second,
weaker one. It is recorded because it explains what a reporter's screenshot
will and will not contain.

Two names in that enum resolve to id `-100`, `DHW_MODIFIABLE_SETPOINTS` and
`DHW_CHANGEABLE_TARGET`: the app knows the name and the back end never
assigned an id. There is nothing to look for.

### A write was undone by the poll it asked for

The reporter could change a setpoint and not the override duration, and the
difference was never in the capability.

`PENDING_WRITE_GRACE` holds a confirmed write for sixty seconds, so the value
a user set does not flicker back while the cloud catches up. It was applied
in `_apply_pending_writes`, called only from `update_devices_from_json_data`
-- the account-wide setup view. The targeted refresh a write triggers goes
`fetch_capabilities` -> `store_capabilities`, which replaced the device's
capabilities wholesale and never replayed the hold.

That path is the one most likely to answer with the old value, since it runs
seconds after the write. `store_capabilities` applies the hold now, which is
where it was always meant to be: whichever poll arrives first, the value the
user set is the value shown until the cloud agrees or the grace runs out.

Why a setpoint looked fine and a duration did not is not settled -- it may be
no more than how long each takes to propagate. The hold is the mechanism that
was supposed to cover both, and it was covering neither on this path.

## Consumption : the day so far, from its own endpoint

The setup view carries no consumption, and MEMORY.md recorded the one route
that does -- `GET /magellan/setups/<setupId>/consumptions?periodicity=daily`
-- as known and left alone, because no device on the account this project is
checked against reports any. `mmnlfrrr/cozytouch`, a fork of the upstream
project, implemented it from a Thermor Duralis ACI HYB (model 393), with a
proxied capture of the iOS app and the app's own tariff screen to check
against. What is here is read from that work, and from its sanitised
fixture, now `tests/fixtures/consumptions_daily.json`. Nothing in this
repository has seen the endpoint answer, which is the first thing to say
about it.

### What the answer is

A list of series, each `type`, `unit`, `currency` and `consumptionPeriods`,
each period `date`, `mode`, `consumedQuantity` and `cost` :

| type | unit | what | mode |
| ---: | ---: | --- | --- |
| 1 | 1 | electricity, kWh | 1 = peak, 2 = off-peak |
| 4 | 2 | water, litres | 0, always with a cost of 0 |

The tariff periods were settled by price in the fork, not guessed : across
four captures mode 2 divides out to 0.1436 EUR/kWh and mode 1 to 0.2157, and
the app's tariff screen shows 0.1438 and 0.2159. `currency` 101 is euros, by
the same screen, and is the only code anyone has seen. `date` is a midnight
UTC. The series also carry `serialNumber`, `deviceId`, `deviceUrl`,
`zoneId`, `category` and `profil` ; on the one account seen, `deviceId` and
`zoneId` are null, so a series says nothing about which appliance it is for.

### Why it hangs off the account, and off a device of its own

The route is the setup's, and so is its answer. The request is made by
`CozytouchAccount.refresh_consumptions`, on the account coordinator's beat,
and the sensors are `CoordinatorEntity`s of that coordinator rather than of
any hub. With `deviceId` null there is no subentry to put them under without
picking one, and picking the first would put a household's water on a
radiator. They go on one device named after the setup (`Maison`), identified
by the entry id, with no subentry -- the one device here that is not one
somebody added.

Two series of one kind -- two metered appliances -- are added together, on
the latest day either reports. The fork keyed on the kind alone, so the
second overwrote the first. Adding is the reading that loses neither ; it has
never been observed, and a setup that reports per-appliance series is the
report that would say whether they should be split instead.

### Capability 164 says whether to ask at all

`HOME_EnergyConsumptionCapabilities`, which the catalogue describes as "the
consumption available on the system", is a mask : bits 1 to 64 are gas,
electricity and fuel for heating, cooling and hot water, and the two bits
the table adds, 256 and 1024, are heat *produced* rather than a meter. Two
readings line up with what the app shows :

| device | 164 | consumption in the app |
| --- | ---: | --- |
| HUB Navizone (1758), this project's | 0 | none, per its owner |
| Duralis ACI HYB (393), the fork's | 1040 = `elec_dhw` + `dhw_production` | yes |

So a setup where every device reporting 164 sets none of bits 1-64 is not
asked at all -- the Navizone costs no request. One where some device sets
one is asked. One where no device reports 164 is left to the endpoint's
first answer, as below, since two readings do not say that 164 is always
there. The dump carries the reading as `declared`.

What counts as a meter is read off 164's own row in `capability_table.py`,
every member but the `_production` ones, the way `HVAC_MODE_MASKS` is read off
the mode bits : a bit named there later is either a meter or not, and a test
pins the mask so somebody has to say which.

164 decides whether to ask, not what to build : water is in no bit of it
and the fork's device reports water all the same.

### What is built, and when

The sensors are built from the first answer and only from it : energy, and
its peak and off-peak halves only where the series has used both ; cost only
in a currency in the table ; water. A series in a unit other than the one in
the table is left out rather than shown under the wrong one. That first
answer comes with setup's first refresh, which runs before the platforms
load.

A setup whose first answer is an empty list or a 4xx is not asked again until
the entry reloads, since nothing was built to read it : one request per
start rather than 96 a day, for a setup 164 did not already rule out. A
setup that did report keeps being asked through an
empty answer, and a sensor whose series disappears goes unavailable rather
than reading zero.

The endpoint is read every 15 minutes (`CONSUMPTION_INTERVAL`), the cadence
the fork chose : the days are aggregated in the cloud and nobody has measured
how often they move. A failure is logged at debug and changes nothing -- it
does not clear `online`, fail the poll or mark a device unavailable. A 429
arms the account's backoff like any other.

### The state class is TOTAL, with the day as `last_reset`

The fork declared the readings `total_increasing`. That is refused for the
cost : Home Assistant admits only `total` on `monetary`, and logs the pair as
an error. `total` with `last_reset` at the start of the day the reading is
for is also what a daily bucket *is* -- the recorder starts a new cycle when
`last_reset` moves, rather than reading any decrease as a meter swap, which a
cloud revising a day downwards would otherwise be. The energy dashboard
accepts both.

### What the dump carries

The whole answer, the status it came with and what 164 declared, under
`consumptions`, with `serialNumber` and `deviceUrl` redacted. A setup 164
rules out reads `declared: false` and no answer, since it was not asked ; one
that was asked and reports nothing reads `status` 200 and an empty `answer`,
or the 4xx -- the thing worth knowing if 164 ever turns out wrong. The fake
cloud in
`scripts/test_ha` serves a dump's `consumptions` back, moved so its latest day
is today ; `scripts/test_ha/water_heater.json` is a synthetic dump built from
the fork's documented capability values and its fixture, and says so.

### Left alone

- `periodicity=monthly|yearly` exist and answer the same shape. A daily
  bucket is what the energy dashboard wants ; a monthly total is a
  statistic, and Home Assistant makes its own.
- `/magellan/gateways/<id>/consumptions` is what the iOS app also calls.
  Nothing says what it adds over the setup's.
- Capability 269 (`water_consumption`) reads null on the fork's device while
  the endpoint reports the water. The fork stops building its entity when it
  is null ; that is a change to the table with its own evidence, not part of
  this one.
