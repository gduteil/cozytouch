"""Turn a partial dump into one `run.py start` can serve.

Some reporters send a hand-trimmed or anonymised subset of the diagnostics
file : a `devices` list with a modelId, a productId and only the capability
values they thought relevant, and no setup or zones. The fake needs a whole
account, so this lays those values over a fixture that has one :

    python scripts/test_ha/overlay_dump.py PARTIAL.json OUT.json \
        [--base scripts/test_ha/navizone.json]

Every device of the partial dump becomes a device of the base's first
gateway, cloned from the base device of the same modelId when there is one
and from its first room otherwise, with its own zone. The partial dump's
values win ; every capability it leaves out keeps the base's value, so a
screenshot of the result shows the reporter's numbers on a fixture's
device, not the reporter's device. Write OUT into the scratchpad : it
carries the reporter's values, and is never committed.
"""

import argparse
import copy
import json
import pathlib

HERE = pathlib.Path(__file__).resolve().parent


def overlay(partial: dict, base: dict) -> dict:
    full = copy.deepcopy(base)
    data = full["data"]
    gateway = next(d for d in data["devices"] if d.get("masterDeviceId") is None)
    by_model = {d["modelId"]: d for d in data["devices"] if d is not gateway}
    first_room = next(iter(by_model.values()))
    gateway_zone = next(z for z in data["zones"] if z["id"] == gateway["zoneId"])
    zone_template = next(z for z in data["zones"] if z is not gateway_zone)

    devices, zones = [gateway], [gateway_zone]
    for index, reported in enumerate(partial["devices"]):
        model = reported["modelId"]
        device = copy.deepcopy(by_model.get(model, first_room))
        name = f"Room {index + 1} ({model})"
        zone_id = gateway["zoneId"] + 1 + index
        device.update(
            deviceId=gateway["deviceId"] + 1 + index,
            modelId=model,
            productId=reported.get("productId", device["productId"]),
            name=name,
            customName=name,
            longName=name,
            zoneId=zone_id,
            masterDeviceId=gateway["deviceId"],
            tags=[],
        )
        values = reported.get("capabilities", {}).get("values", {})
        device["capabilities"]["values"].update(
            {str(k): v for k, v in values.items()}
        )
        devices.append(device)
        zones.append({**copy.deepcopy(zone_template), "id": zone_id, "name": name})

    data["devices"], data["zones"] = devices, zones
    return full


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("partial", type=pathlib.Path)
    parser.add_argument("out", type=pathlib.Path)
    parser.add_argument("--base", type=pathlib.Path, default=HERE / "navizone.json")
    args = parser.parse_args()

    partial = json.loads(args.partial.read_text())
    full = overlay(partial, json.loads(args.base.read_text()))
    args.out.write_text(json.dumps(full, indent=1))
    print(f"{len(full['data']['devices'])} devices -> {args.out}")


if __name__ == "__main__":
    main()
