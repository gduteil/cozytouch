# Atlantic Cozytouch — Home Assistant integration

A custom integration talking to Atlantic's Cozytouch cloud. It is not the
official `overkiz` integration : Atlantic runs several protocols, and this one
covers the boilers, water heaters, towel racks and air conditioners that speak
the Cozytouch API rather than Overkiz.

## Where to read first

This file says what to do and where. Three documents say how the thing works,
and are worth reading before a change rather than after :

| Document | What it answers |
| -------- | --------------- |
| `docs/architecture.md` | How a capability id becomes an entity, what the account owns and what the Hub owns, which invariants hold, and the rough edges that are real and inherited. |
| `docs/api-surface.md` | What the API does and does not expose. Read it before probing anything : ~90 paths are already ruled out, and there is no capability catalogue to fetch. |
| `docs/decisions.md` | Why a setting is the value it is — which run was measured, what was tried and dropped. This is where the reasoning lives that used to sit in comment blocks above the setting. |
| `MEMORY.md` | What past sessions settled, rejected or parked — one line each. Imported below, so it is always loaded ; update it when a finding is overturned. |

@MEMORY.md

## Repository topology

This repo started as a fork of `gduteil/cozytouch` and now stands on its own :
it is no longer tied to that project or to `mathieuletyrant/cozytouch`, and
nothing here pushes to either. `origin` is `mathieuletyrant/cozytouch-hacs`,
the only remote ; its `main` is what HACS installs, and every pull request
targets it.

## Tests

Python 3.14.2 — the system `python3` on this machine is too old. Build the
venv with `uv venv --python 3.14.2`, install with
`uv pip install -r requirements_test.txt`, run `.venv/bin/pytest tests/ -q`.
`uv pip` and not `pip`, because a uv venv ships no pip of its own.
In a Claude Code on the web session, `.claude/hooks/session-start.sh` builds
that venv at startup, lint tools included.
The patch version matters: `requirements_test.txt`
pins Home Assistant exactly, and that release declares Python 3.14.2 as its
floor, so an older interpreter makes the install fail rather than resolve
backwards to an HA nobody runs.

The requirements are pinned, not `>=`, for that reason — see the comment at
the top of the file for what the unpinned version did. There are two of them :

| File | What it is |
| ---- | ---------- |
| `requirements_test.txt` | the environment to develop in, and CI's main job |
| `requirements_test_min.txt` | the oldest HA `hacs.json` claims to support, so the claim is tested |

Raising the floor means editing `requirements_test_min.txt` and `hacs.json`
together, and the Python it is paired with in `.github/workflows/tests.yaml`.
`tests/test_floor.py` fails if the first two disagree, and is what says whether
a candidate floor can run this at all.

## Lint

`uv pip install -r requirements_lint.txt`, then `.venv/bin/ruff check .`. CI
runs the same check and it has to come back clean.

CI runs on pull requests based on `main` **or** on a `claude/**` branch. That
second one is not decoration: the trigger filters on the *base* branch, so
before it was added a pull request stacked on another one got no checks at all
-- which is not the same as passing, and reads exactly like it.

The configuration is `pyproject.toml`, and it is worth reading before arguing
with a finding : the rules that are off are off for a stated reason, and two of
them matter here. Naming rules (`N803`/`N806`) are not enabled because the
camelCase locals mirror the field names the Atlantic API itself uses, and
`PLR2004` is not enabled because the numeric capability ids *are* the domain.
Do not "fix" code to satisfy a rule the config deliberately drops.

Types are checked by pyright, but only on the typed core — `infos.py`,
`model.py`, `capability.py` — as `pyproject.toml` scopes it ; CI runs it in
the pinned test venv (`.venv/bin/pyright`), and the scope's reasons are in
`docs/decisions.md`.

`scripts/check.sh` runs all three in the order that fails fastest ; extra
arguments go to pytest.

`ruff format` is **not** run, by CI or otherwise. The tree is not
formatter-clean; reformatting it is its own change, not something to slip into
another one.

The suite is **characterisation tests**. They pin the mapping as it stands, not
as it ought to be : most entries were reverse-engineered from one user's
capture, so a test going green says "nobody changed this by accident", never
"this is correct".

Every test file opens with a docstring saying what it pins and why ; read
that rather than a list here, which went stale the moment a file was added.
The rules the docstrings do not repeat :

- `tests/test_snapshot.py` holds both tables against `tests/snapshots/`. If
  those files do not change, no answer did -- that is what proves a refactor.
  Regenerate only in the commit whose diff shows why :
  `UPDATE_SNAPSHOTS=1 .venv/bin/pytest tests/test_snapshot.py`.
- `tests/test_sensor_values.py` pins the strings a dashboard shows **as they
  are, not as they should be**. Changing an output means changing its test in
  the same commit.
- `tests/test_floor.py` is how the supported HA floor is found : run it, do not
  read a changelog.
- `tests/test_capability.py` walks `range(1, 2500)` ; a model id outside it
  needs the range widened.
- `tests/test_polling.py`'s `FakeSession` is a deliberate copy of
  `tests/test_reauth.py`'s. Do not merge them.

## Seeing it in Home Assistant

The tests say a mapping did not move ; they do not say what a page looks
like. `scripts/test_ha/run.py` starts a Home Assistant in the session with
the working tree's integration, served by a fake Cozytouch cloud built from
a diagnostics dump -- no account involved -- and
`scripts/test_ha/screenshot.cjs` photographs its pages. The `test-ha` skill
is the walk-through, and says what the fake does not simulate.

## Entries, subentries, identity

An account is one config entry; each of its devices is a subentry of it. The
subentry id is the identity a device is registered under and the prefix of
every unique id built from it, so a device added twice or a subentry recreated
is a new set of entities. `account.py` owns everything the account declares —
the session, the token, the setup view, the device list — and `hub.py` is one
coordinator per device on top of it.

## Answering a device report

A device is no longer *added*. `model.py` works out what one is from what the
API sends — its `productId` against the vendor's own ranges, the `productId`
of the interface it hangs off, and `modelFamily` where Atlantic assigns no
product id — so hardware nobody has reported still arrives typed, named and
with the modes capability 100022 says it has. What a report brings is almost
always the other half : **what the capabilities mean**.

1. `custom_components/cozytouch/capability_table.py` — a row per capability id
   the dump lists as unmapped. A device that reads an id differently says so
   on its row (`absent_on`, `needs_flag`, `per_type`), never by changing the
   shared default and never keyed on a model id. An id the row cannot decide
   — it depends on the value, or on what else the device reports — belongs
   in the chain in `capability.py` instead. A capability whose encoding is unverified still
   gets a row: named, `type=STRING`, `category=DIAG` and
   `enabled_by_default=False`, with neither `bits` nor `reads_as`, so it costs
   nobody anything until someone turns it on to investigate. Claim a type only
   where the unit is actually known.
2. Translations — a new capability name needs an entry in **every** one of
   `strings.json` and the files under `translations/` (en, fr, es, de, it),
   kept in the alphabetical order and column alignment already in the file.
   The tests glob that directory, so a language added later is held to the
   same completeness without anyone editing them.
3. Tests — the snapshots regenerated in the same commit
   (`UPDATE_SNAPSHOTS=1 pytest tests/test_snapshot.py`) so the diff shows what
   the change did and nothing else.

`model.py` is edited only when the device is genuinely wrong about itself, and
then through `OVERRIDES` — nineteen ids, each one a measured difference
between what a branch used to answer and what the device declares, not a
backlog of missing rows. `model_product_ids.py` holds `LEARNED_FROM_DUMPS`,
where a `productId` the vendor's catalogue leaves at 0 is recorded from a live
payload; that is data, and it is how an override comes down.

`scripts/dump_capability_map.py` prints what the two tables now resolve to, per
device type. Nothing has to be regenerated — run it when you want the answer.
A new device *type* needs a probe model id added to it, which is the same edit
as adding the type to `model.py`.

A device nothing can type still falls through to `Unknown product (…)`, and
that is now rare enough to be a report in itself. Everything is built from the
diagnostics dump (`diagnostics.py`, backed by `Hub.get_diagnostics`) : every
device on the account with what the API says about it and the capability ids
nothing names yet. Ask a reporter for that file before anything else, and for
screenshots of their app beside it — the dump says what a device *reports*,
and only the app says what it lets you *do*, which is the difference between a
control that works and one that writes into the void.
`.github/ISSUE_TEMPLATE/device_report.yml` asks for both.

The `Create entities for unknown capabilities` option turns each unnamed
capability into an entity, which is for working out what a value means rather
than for reporting.

## Commit messages

Subject is a sentence saying what changed for the user, in the present tense,
no prefix and no ticket number : *"Stop offering an eco mode the room air
conditioners do not have"*, not *"fix(ac): eco mode"*.

The body leads with **why** — the observed behaviour, what the Cozytouch app
does, what a capture showed — and only then what the change does. State the
evidence and its limits : which model ids a finding covers, which it does not,
what was left alone for lack of a report. Wrap at 76 columns.

## Watching the vendor catalogue

`GET /magellan/productmodels/capabilities` is where `capability_table.py` came
from, and nothing announces an edit to it. `scripts/capability_catalogue.jsonl`
is what it said last time, one capability per line, sorted ; the `Catalogue`
workflow re-reads it on the 1st and the 15th and opens an issue with the diff
when the two differ. It needs `COZYTOUCH_USER` and `COZYTOUCH_PASS` as
repository secrets.

One login per run and no retry, deliberately -- repeated failed logins are
what could lock the account, and an unattended job that retries is how that
would happen. A run that reads fewer than 300 capabilities refuses to write
rather than record a truncated answer as a mass deletion.

The diff is a worklist, not a change : a new id still needs its row and its
translations, decided the way the section above describes.

## House style

Reasoning goes in `docs/decisions.md`, not in a comment block above the thing
it explains. Which run was measured, what the app shows, what a capture
proved, what was tried and dropped : all of it belongs in a named entry that
can be read end to end, rather than scattered across the files it happens to
touch.

What stays in the code is a pointer, where the line would otherwise read as a
mistake — `# see docs/decisions.md` on the setting that looks wrong, one line,
no argument restated. A `noqa` still says which rule and why on the spot,
because that one is about the line and nothing else.

Comments never restate the code.

The older files predate this and still carry their reasoning inline :
`pyproject.toml`, the requirements files, and the modules under
`custom_components/`. Do not migrate them wholesale. A file moves to
`docs/decisions.md` when it is being edited for some other reason anyway.

## Releasing

The release job reads `release_notes/<version>.md` and puts it above the
commit list, which it folds away. Write that file in the same pull request
as the `manifest.json` bump -- the job refuses to run until the manifest
carries the version being released, so it is one pull request either way.

`/release-notes <version>` writes that file : it reads the commits since the
last tag and turns them into the four or so themes somebody actually cares
about. The notes are for somebody deciding whether to update : what their
devices now do, what stopped being broken. The commit subjects already say what
changed one at a time, and that is what the folded list is for. Without the
file the release is that list alone, which is what every release before
2026.9.21 was.
