#!/usr/bin/env python3
"""Pull (modelId, capabilityId, value) out of every capture in a directory.

    python3 extract.py <outdir> <dump dir or file>...

Writes readings.tsv, devices.tsv and by-capability.md. The Navizone fixture,
scripts/test_ha/navizone.json, is always read as well: it stands for the one
capture that is not on any tracker. docs/research/corpus.md has the rest.

Why a regex and not json.load: most captures in the tracker were anonymised by
hand before posting, and the edits break the syntax -- `"id": xxxxxxxxxx`,
`"id": redacted`, a trailing comma, an unbalanced quote. Only 7 of 29 parse.
The tolerant reader below gets the same triples out of the other 22, and
self-checks: on every file that does parse, its output is compared to the strict
parse and must match exactly.

Values for a few ids are replaced by <text>. They are free-form and personal --
room names carry first names, 219 is the wifi SSID, 88/94/98/335 are serials --
and nothing about typing a capability needs the string itself, only that it is
one.
"""

import json
import pathlib
import re
import sys

VALUE = r'"value"\s*:\s*("(?:[^"\\]|\\.)*"|null|-?[\d.]+)'
CAP = re.compile(r'"capabilityId"\s*:\s*(\d+)')
MODEL = re.compile(r'"modelId"\s*:\s*(\d+)')
FIELDS = ("longName", "modelFamily", "productRange")

REDACT = {88, 94, 98, 154, 155, 219, 335}
LOCAL = pathlib.Path(__file__).resolve().parents[1] / "test_ha" / "navizone.json"


def clean(cid, value):
    return "<text>" if cid in REDACT and value not in (None, "") else value


def tolerant(text):
    """Triples, without needing the file to be valid JSON."""
    models = [(m.start(), int(m.group(1))) for m in MODEL.finditer(text)]
    out = []
    for m in CAP.finditer(text):
        v = re.search(VALUE, text[m.end() : m.end() + 2000])
        if not v:
            continue
        raw = v.group(1)
        value = json.loads(raw) if raw.startswith('"') else (
            None if raw == "null" else raw
        )
        model = None
        for pos, mid in models:
            if pos < m.start():
                model = mid
            else:
                break
        out.append((model, int(m.group(1)), value))
    return out


def strict(text):
    out = []
    for setup in json.loads(text):
        # Some reporters paste the device list rather than the setups.
        for dev in setup.get("devices", [setup] if "capabilities" in setup else []):
            out.extend(
                (dev.get("modelId"), c["capabilityId"], c.get("value"))
                for c in dev.get("capabilities", [])
            )
    return out


def _payload(text):
    """The dump as a dict, or an empty one for anything else in the directory."""
    try:
        payload = json.loads(text)
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def diagnostics(text):
    """Triples out of one of our own diagnostics dumps.

    The captures on the old tracker are raw `setupviewv2`, a list of
    `{capabilityId, value}` per device, which is what the two readers above
    understand. What a reporter attaches to *our* tracker is the file
    `diagnostics.py` writes: the same facts under `data.devices[].capabilities`,
    where `values` is a `{id: value}` map. Nothing in the regex readers matches
    it, so without this every report on our own tracker counted for nothing.
    """
    payload = _payload(text)
    out = []
    for dev in payload.get("data", {}).get("devices", []):
        model = dev.get("modelId")
        for cid, value in dev.get("capabilities", {}).get("values", {}).items():
            out.append((model, int(cid), value))
    return out


def diagnostics_devices(payload_text):
    """The descriptive fields, from a diagnostics dump."""
    payload = _payload(payload_text)
    return [
        {"modelId": dev.get("modelId")}
        | {field: dev.get(field) or "" for field in FIELDS}
        for dev in payload.get("data", {}).get("devices", [])
    ]


def devices(text):
    """The modelId and three descriptive fields, for context.

    No address, no serial, no coordinates, no setup id.
    """
    out = []
    for m in MODEL.finditer(text):
        window = text[max(0, m.start() - 1200) : m.start() + 1200]
        row = {"modelId": int(m.group(1))}
        for field in FIELDS:
            f = re.search(rf'"{field}"\s*:\s*("(?:[^"\\]|\\.)*"|null)', window)
            row[field] = json.loads(f.group(1)) if f and f.group(1) != "null" else ""
        out.append(row)
    return out


def main(outdir, *dumpdirs):
    out = pathlib.Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    files = []
    for d in (*dumpdirs, LOCAL):
        p = pathlib.Path(d)
        files += sorted(p.glob("*.json")) if p.is_dir() else [p]

    readings, devs, checked = [], [], []
    for f in files:
        text = f.read_text(errors="replace")
        t = diagnostics(text)
        if t:
            readings += [(f.name, *r) for r in t]
            devs += [(f.name, d) for d in diagnostics_devices(text)]
            continue

        t = tolerant(text)
        if not t:
            continue
        try:
            s = strict(text)
        except (ValueError, KeyError, TypeError, AttributeError):
            s = None
        if s is not None:
            checked.append((f.name, sorted(s) == sorted(t)))
        readings += [(f.name, *r) for r in t]
        devs += [(f.name, d) for d in devices(text)]

    bad = [name for name, same in checked if not same]
    if bad:
        sys.exit(f"the tolerant reader disagrees with the strict parse on {bad}")

    with (out / "readings.tsv").open("w") as h:
        h.write("source\tmodelId\tcapabilityId\tvalue\n")
        for src, model, cid, val in readings:
            h.write(f"{src}\t{model}\t{cid}\t{clean(cid, val)}\n")

    seen = set()
    with (out / "devices.tsv").open("w") as h:
        h.write("source\tmodelId\t" + "\t".join(FIELDS) + "\n")
        for src, d in devs:
            key = (src, d["modelId"], d["longName"])
            if key in seen:
                continue
            seen.add(key)
            fields = "\t".join(str(d[f]) for f in FIELDS)
            h.write(f"{src}\t{d['modelId']}\t{fields}\n")

    aggregate(readings, out / "by-capability.md")
    print(
        f"{len(readings)} readings, {len({r[1] for r in readings})} modelIds, "
        f"{len({r[2] for r in readings})} capabilityIds, "
        f"{len(checked)} files checked against the strict parse"
    )


def aggregate(readings, path):
    import collections

    by_id = collections.defaultdict(
        lambda: {"vals": collections.Counter(), "models": set()}
    )
    for model, cid, val in (r[1:] for r in readings):
        by_id[cid]["vals"][str(clean(cid, val))] += 1
        by_id[cid]["models"].add(model)

    lines = [
        "# What the captures read, per capabilityId",
        "",
        "`models` = how many distinct modelIds report this id.",
        "Values are sorted by frequency, `(n)` = number of readings.",
        "",
        "| id | models | values |",
        "| --- | --- | --- |",
    ]
    for cid in sorted(by_id):
        d = by_id[cid]
        vals = " ".join(f"`{v}`({n})" for v, n in d["vals"].most_common(8))
        if len(d["vals"]) > 8:
            vals += f" +{len(d['vals']) - 8}"
        lines.append(f"| {cid} | {len(d['models'])} | {vals[:220]} |")
    path.write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main(sys.argv[1], *sys.argv[2:])
