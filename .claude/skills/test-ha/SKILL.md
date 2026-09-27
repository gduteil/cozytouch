---
name: test-ha
description: Run a throwaway Home Assistant with this integration against a fake Cozytouch cloud, drive it, and take screenshots of its pages for the maintainer. Use to launch or run the app, to see a change working in Home Assistant rather than only in tests, when asked for a screenshot, "le HA de test", "montre-moi la card", or before and after comparing a branch with main.
---

# test-ha

A Home Assistant that runs in this session, with the working tree's
integration, talking to `scripts/test_ha/fake_atlantic.py` instead of
Atlantic. No login to anybody's account, ever : that is the point of it, and
MEMORY.md is why.

The maintainer cannot open it : it listens on 127.0.0.1 inside the session.
What they see is the screenshots you send them.

## The flow

```bash
R="python3 scripts/test_ha/run.py"
$R setup          # once per session : .venv-ha, the HA that tests pin
$R start          # fresh instance, owner onboarded, account added
```

`start` takes a diagnostics dump as argument ; without one it serves
`scripts/test_ha/navizone.json`, a HUB Navizone (1758) and its three rooms
(557-559) with no absence set. `scripts/test_ha/water_heater.json` is the
other one : a synthetic Duralis ACI HYB (393) whose setup reports
consumption, for the sensors on the `Maison` device. A first start takes a
few minutes while Home Assistant installs the frontend ; after that, seconds.

Then, as often as needed :

1. **Change the code**, then `$R restart`. It recopies
   `custom_components/cozytouch` and restarts the process. A reload is not
   enough, for the same reason it is not on a real install.
2. **Act** : `$R call DOMAIN.SERVICE '{"entity_id": "..."}'`. A write goes to
   the fake ; the entities follow at the next poll, so allow up to a minute
   before reading them.
3. **Read** : `$R states TEXT` for the entities matching TEXT, with the
   climate attributes worth checking ; `$R journal` for what the fake
   received, in order -- logins, absence PUTs, capability writes.
4. **Look** : take a screenshot (below), open it with Read to check it shows
   what you meant, then send it with SendUserFile, `display: render`.
5. `$R stop` when done.

Logs are in `.test-ha/hass.log` and `.test-ha/fake.log`.

## Screenshots

```bash
export NODE_PATH=$(npm root -g)
S=scripts/test_ha/screenshot.cjs
PAGE=$($R device climate.room_chambre_parentale_piece)

node $S "$PAGE" out.png --full              # a device page, whole
node $S "$PAGE" out.png --click "Pièce"     # its climate card, opened
node $S /lovelace/0 out.png --full          # the default dashboard
```

- `--click TEXT` clicks the first element showing exactly that text, and
  may be repeated to go further : an entity's name on its device page opens
  its more-info dialog. Leave `--full` off with a dialog open.
- The page is 430 px wide, French, Paris time -- a phone, which is how the
  maintainer looks at Home Assistant. `--width` and `--height` change it.
- Entity ids are built from the French names (`absence_debut`, `piece`) ;
  `$R states` gives them.
- Write screenshots into the scratchpad, not the repository.

## Before and after

`restart` copies whatever the working tree holds, so a comparison is two
checkouts and two restarts : screenshot on `main`, `git checkout` the
branch, `$R restart`, the same screenshot again. Send the pair together and
say which is which.

## What the fake does not know

It stores writes and serves them back. The only cloud behaviour it plays is
what a capture showed : 102020 reaches every room, and a gateway's 152 and
222 are mirrored onto its rooms as 100261 and 100260. The consumption
endpoint serves the dump's `consumptions` moved so its latest day is today,
and an empty list for a dump without one. Anything else -- a
programmed absence turning itself on, a 429, a refused login -- does not
happen here, so a screenshot proves how the integration reads the API, never
how Atlantic answers. Say so when the question is about the cloud.

## Dumps

A reporter's dump can be served as it is (`$R start path/to/dump.json`),
from the scratchpad. Never commit one : it names their rooms and their ids.
A fixture worth keeping gets the treatment `navizone.json` got -- names,
device ids, zone ids and the setup id replaced -- and is checked for the
originals before it is added.
