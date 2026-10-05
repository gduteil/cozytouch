# The capture corpus

A capability is `{capabilityId, value}`: no unit, no encoding, no bounds.
The only way to learn something about one from the wire is to look at what
many devices put in it. The corpus is that: every capture reporters have
posted on the two trackers, reduced to `(modelId, capabilityId, value)`.

Built in October 2026 it held 8220 readings over 53 model ids and 381
capability ids, from `mathieuletyrant/cozytouch-hacs` and
`gduteil/cozytouch` (the project this one forked, which holds the first 29
captures and nowhere else), plus the Navizone fixture.

## Rebuilding it

Nothing of it is committed: it is regenerated in a minute from public
issues. `fetch.py` needs `gh` authenticated (any account; the trackers are
public).

```sh
python3 scripts/corpus/fetch.py /tmp/cozy-dumps
python3 scripts/corpus/extract.py /tmp/cozy-corpus /tmp/cozy-dumps
```

`extract.py` writes three files into its first argument:

| File | What it is |
| ---- | ---------- |
| `by-capability.md` | **Read this one.** Per capability id: how many models report it, and its values by frequency. |
| `readings.tsv` | The raw readings: source, modelId, capabilityId, value. |
| `devices.tsv` | Per capture: modelId, `longName`, `modelFamily`, `productRange`. |

`scripts/test_ha/navizone.json` is always read too. It stands in for the
maintainer's own Navizone capture, which is on no tracker; any other local
dump can be passed as an extra argument, file or directory.

The raw dumps stay out of the repository and out of the output: those on
the trackers are public and re-downloadable, and they carry addresses and
serial numbers there is no reason to copy.

## Two precautions in `extract.py`

**It does not need valid JSON.** Most captures were anonymised by hand
before posting, and the edits break the syntax (`"id": xxxxxxxxxx`, a
trailing comma, a missing quote). A regex reader gets the triples out
anyway, and checks itself: on every file that does parse, its output must
equal the strict parse, or the run stops. That check is what makes the
others credible. Our own diagnostics dumps (`data.devices[]`) are read
directly.

**Personal values are masked.** Ids 88, 94, 98, 154, 155, 219 and 335 read
as `<text>`: room names (which carry first names), the Wi-Fi SSID (219) and
serial numbers. Typing a capability never needs the string, only knowing
that it is one.

## What it is good for

What one capture cannot show and many can. 164 read 1040, 1298, 18, 9 and 2
across models, which is what proved it a mask and not a flag. 331 reads
1440 everywhere: minutes in a day. 306 and 100301 are always in a ratio of
7 (10/70, 8/56, 6/42): slots per day and per week.

## Limits

- A value constant across the corpus does not prove a unit; it proves no
  household changed it. 350 reads 0 everywhere and its name speaks of
  speeds.
- An id absent from the corpus says nothing at all.
- An id that only ever reads 0 has never shown its high state; typing it a
  boolean from the corpus alone is a bet.
- Captures are dated, and a model may have changed firmware since.
- Seasonal values (166, the service masks) move with the time of year the
  capture was taken.
