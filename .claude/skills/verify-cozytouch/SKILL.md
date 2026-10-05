---
name: verify-cozytouch
description: Prove a change to the Cozytouch Home Assistant integration in a real Home Assistant — a throwaway instance against a fake Atlantic cloud served from a diagnostics dump (a fixture or a reporter's), driven over its REST API and photographed with Playwright. Use to see a change working rather than only tested, to reproduce an issue from a reporter's dump, for before/after screenshots on a pull request, or when asked for "le HA de test" or a screenshot.
---

# verify-cozytouch

A Home Assistant that runs on this machine with the working tree's
integration, talking to `scripts/test_ha/fake_atlantic.py` instead of
Atlantic. **No login to anybody's real account, ever** : MEMORY.md says why.
It listens on 127.0.0.1 ; the maintainer sees only the screenshots you send.

What to drive, feature by feature, is in [`features/`](features/README.md).
Read its index before driving anything.

Every command below runs from the repository root. `R` is the driver ; define
it as a function, since zsh does not split a string variable into words :

```bash
R() { python3 scripts/test_ha/run.py "$@"; }
```

and call it as `R start`, `R doctor`, and so on.

## Launch

In a Claude Code on the web session, install the browser first ; the
session-start hook builds only the test venv :

```bash
npm install -g playwright && npx playwright install --with-deps chromium
```

1. **Pick the Home Assistant.** By default it runs from `.venv-ha`, the
   version `requirements_test.txt` pins ; build it once with `R setup`.
   To reproduce an issue, run the reporter's version instead -- their dump
   says it (`home_assistant.version`) -- in a venv in the scratchpad :

   ```bash
   V=<scratchpad>/venv-ha-<version>
   uv venv -q --python 3.14.2 $V && uv pip install -q --python $V/bin/python homeassistant==<version>
   ```

2. **Pick a free port.** 8123 is often held by another test HA on this
   machine (another project's). Check, and never kill what holds it :

   ```bash
   lsof -nP -iTCP:8123 -sTCP:LISTEN    # anything here: use TEST_HA_PORT=8124
   ```

3. **Pick the data.** `start` takes a diagnostics dump :
   - nothing : `scripts/test_ha/navizone.json`, a HUB Navizone (1758) and
     its three rooms (557-559), no absence set ;
   - `scripts/test_ha/water_heater.json` : a Duralis ACI HYB (393) whose
     setup reports consumption ;
   - a reporter's full diagnostics file, as it is, from the scratchpad ;
   - a reporter's **partial** dump (a hand-trimmed `devices` list, no setup
     or zones) : lay it over a fixture first --

     ```bash
     python3 scripts/test_ha/overlay_dump.py PARTIAL.json <scratchpad>/full.json
     ```

     Each of its devices becomes a room of the fixture's gateway, named
     `Room N (<modelId>)`, carrying the reporter's values and the fixture's
     for every capability they left out. Say so wherever you show the
     result.

4. **Start** :

   ```bash
   TEST_HA_PORT=8124 HA_PYTHON=$V/bin/python R start [DUMP]
   ```

   Ready when it prints `Home Assistant is up on http://127.0.0.1:<port>`.
   A first start of a given HA version takes minutes (it installs the
   frontend) ; run it with `run_in_background`. Later ones take seconds.
   The port and interpreter are kept in `.test-ha/instance.json`, so every
   later `R` command and the screenshot helper find them without the
   environment variables.

## Doctor

Run first, and whenever anything looks off :

```bash
R doctor
```

It must show both processes running, the Home Assistant version you meant,
`cozytouch entry: loaded`, and the dump you meant. It answers with this
instance's own owner token, so a reply proves the port is ours. Anything
else : `R stop`, read `.test-ha/hass.log` and `.test-ha/fake.log`, start
again.

## Drive

- **Read** : `R states TEXT` lists the entities whose id contains TEXT.
  For an attribute it does not print, ask the API :

  ```bash
  T=$(R token)
  curl -s -H "Authorization: Bearer $T" http://127.0.0.1:<port>/api/states/<entity_id>
  ```

- **Act** : `R call DOMAIN.SERVICE '{"entity_id": "..."}'`, the same call a
  dashboard makes. Entities follow at the next poll : allow up to a minute.
- **Side effects** : `R journal` lists what the fake received, in order --
  logins, absence PUTs, capability writes. A write proven only by an
  entity's state is not proven ; find it here.
- **Change the code** : edit, then `R restart`. It recopies
  `custom_components/cozytouch` and restarts the process ; a reload is not
  enough, as on a real install.

Entity ids come from the French names (`climate.room_chambre_parentale_piece`,
`datetime.hub_away_mode_start`) ; `R states` gives them, and each feature
file names the ones it uses.

## Evidence

Screenshots, with Playwright (`npm install -g playwright` and
`npx playwright install chromium` once per machine) :

```bash
export NODE_PATH=$(npm root -g)
PAGE=$(R device climate.room_chambre_parentale_piece)
node scripts/test_ha/screenshot.cjs "$PAGE" OUT.png --full            # a device page
node scripts/test_ha/screenshot.cjs "$PAGE" OUT.png --click "Pièce"   # its climate dialog
```

- `--click TEXT` clicks the first element showing exactly TEXT, repeatable ;
  an entity's name on its device page opens its more-info dialog. Leave
  `--full` off with a dialog open.
- The page is 430 px wide, French, Paris time : a phone, which is how the
  maintainer looks at Home Assistant. `--width` and `--height` change it.
- `/lovelace/0` can still read "Loading…" right after a start : prefer
  device pages, and open every screenshot with Read before sending it.

Proof standards :

- Drive the user's path (a service call, a click), never an internal setter.
- Capture the action and the resulting state, plus the side effect in
  `R journal` when there is one.
- State what the fake does not do (below) wherever the question is about
  the cloud.

Evidence lives in `<scratchpad>/shots/`, never in the repository, and
survives cleanup.

### Before and after, on a pull request

When a pull request changes what a page shows -- and always when it answers
a reporter's issue -- photograph the same page on `main` and on the branch,
against the reporter's dump and HA version when there is one :

1. Start on `main`'s integration, take the "before" shots.
2. `git checkout <branch> -- custom_components/` (or check the branch out),
   `R restart`, the same shots as "after".
3. `git checkout main -- custom_components/` to put the tree back.
4. Comment on the pull request with the shots attached -- `gh` 2.99 or
   later uploads them as GitHub attachments, nothing is committed. Write the
   body in a file, reference each shot by its relative path, and run it from
   the directory holding them ; `gh` rewrites each reference to the uploaded
   asset :

   ```bash
   cd <scratchpad>/shots
   gh pr comment <n> --repo mathieuletyrant/cozytouch-hacs -F body.md \
       --attach before.png --attach after.png
   ```

   with, in `body.md`, a table such as
   `| ![Before: ...](./before.png) | ![After: ...](./after.png) |`, the HA
   version, the dump used and how it was adapted. `--edit-last` replaces
   your previous comment instead of adding one.

   **In a Claude Code on the web session** this cannot work : its GitHub
   proxy refuses every way to upload an image (GraphQL, Git Data writes,
   any ref but a branch). Verify there, describe what the shots show in the
   pull request, and leave the shots themselves to a local session.

## What the fake does not know

It stores writes and serves them back. The only cloud behaviour it plays is
what a capture showed : 102020 reaches every room, a gateway's 152 and 222
are mirrored onto its rooms as 100261 and 100260, and a general stop sets
every room to 7 = 0, 181 = 0, 166 = 1. The consumption endpoint serves the
dump's `consumptions`, moved so the latest day is today. Anything else -- a
programmed absence starting on its own, a 403 on a mirror write, a 429, a
refused login -- does not happen here : a screenshot proves how the
integration reads the API, never how Atlantic answers.

## Cleanup

```bash
R stop
```

It stops the two processes this instance started, by the pids in
`.test-ha/`, never by name. `.test-ha/` itself is wiped by the next
`start`. The scratchpad shots and venvs stay. Never commit a reporter's
dump : it names their rooms and their ids. A fixture worth keeping gets
the treatment `navizone.json` got -- names and ids replaced -- and is
checked for the originals before it is added.

## Helpers

| Helper | What it does |
| ------ | ------------ |
| `scripts/test_ha/run.py` | `setup`, `start [DUMP]`, `restart`, `stop`, `doctor`, `states [TEXT]`, `call DOMAIN.SERVICE [JSON]`, `device ENTITY_ID`, `journal`, `token` |
| `scripts/test_ha/overlay_dump.py` | `PARTIAL.json OUT.json [--base FIXTURE]` : a partial dump made servable |
| `scripts/test_ha/screenshot.cjs` | `PATH OUT.png [--click TEXT]... [--full] [--width N] [--height N]` |
| `scripts/test_ha/fake_atlantic.py` | the fake cloud ; `run.py` starts it, nothing else should |
