r"""Probe the Cozytouch API and print the shape of what each route returns.

A discovery tool, not part of the integration. Read-only: it authenticates,
GETs, and prints keys rather than a full dump, so the output can be pasted
into an issue without leaking an address or a serial number.

What this has already established -- and what is still worth trying -- is
written down in docs/api-surface.md. Read that before adding routes here, so
the ~90 paths already ruled out are not probed again.

Run from the repository root:

    umask 077
    pbpaste > ~/.cozytouch-pass          # keeps the password out of the
    COZYTOUCH_USER=you@example.com \     # shell history
      COZYTOUCH_PASS_FILE=~/.cozytouch-pass \
      python3 scripts/probe_api.py [--new-routes] [--explore] [--cadence]
                                   [--errors [modelId]]
    rm -f ~/.cozytouch-pass

`--errors` asks whether the vendor will name a fault code. The fault-code
matrix is decoded but never translated (docs/decisions.md), because the
string table is Atlantic's. `productmodels/models/{id}/detailederrors` answers
400 naming `ParentErrorCode` and `ChildErrorCode` -- which are the matrix row's
`majorCode` and `minorCode` -- so their server may name the one code a device
is actually reporting, with nothing redistributed. It needs no fault of your
own: the model catalogue is not scoped to the account asking.

`--cadence` answers a different question from the rest: not what a route
returns but how *fresh* it is. It compares `modificationDate` between the setup
view and the per-device capability route for ten minutes, which is what says
whether one account-wide poll can stand in for one poll per device. Change a
setpoint in the app while it runs.

Reads are cheap: the integration itself polls the setup view twice a minute. A
*refused login* is the one thing not to repeat -- it is what could lock an
account -- so a rejected token stops the script instead of retrying.
"""

import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import _atlantic
from _atlantic import COZYTOUCH_ATLANTIC_API as API, password

# The device fields model.py hardcodes or derives today. Printed per device so
# a dump from another product family can be compared against the table in
# docs/api-surface.md, which so far only covers air conditioning.
DEVICE_FIELDS = (
    "name",
    "customName",
    "longName",
    "modelFamily",
    "productRange",
    "productId",
    "isAvailable",
    "masterDeviceId",
    "zoneId",
)

# Routes the integration already polls, so running without --new-routes adds
# nothing an account does not do to itself every minute.
ROUTES_KNOWN = ("/magellan/refs/countries",)

# Routes that exist but which the integration never calls. Add candidates
# here; a 404 means the gateway does not route the path at all.
ROUTES_NEW = (
    "/magellan/devices",
    "/magellan/setups",
    "/magellan/gateways",
    "/magellan/zones",
)

# Routes not yet tried at all. setupview is the v1 the integration replaced;
# an older version sometimes carries a field a newer one dropped. The rest ask
# whether an item returns more than its collection listing.
ROUTES_EXPLORE = (
    "/magellan/cozytouch/setupview",
)


def token() -> str:
    """Authenticate, or exit saying why."""
    try:
        return _atlantic.token(password() or "", timeout=20)
    except urllib.error.HTTPError as err:
        sys.exit(
            f"login refused ({err.code}): {err.read().decode()[:200]}\n"
            "Check the credentials before running this again; repeated failed "
            "logins are what could lock the account."
        )


def get(url: str, access_token: str, language: str | None = None):
    """GET a route, returning (status, parsed body or error text)."""
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    if language:
        headers["Accept-Language"] = language
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as err:
        # A route the gateway accepts can still 404 with an HTML page at the
        # backend, which is how refs/countries turned out to be dead.
        return err.code, err.read().decode()[:200]
    except Exception as err:  # noqa: BLE001
        return None, repr(err)


def shape(value, depth: int = 0) -> str:
    """Describe a payload by its keys, keeping one sample item per list."""
    pad = "  " * depth
    if isinstance(value, dict):
        lines = []
        for key, item in value.items():
            if isinstance(item, (dict, list)):
                lines.append(f"{pad}{key}:")
                lines.append(shape(item, depth + 1))
            else:
                lines.append(f"{pad}{key} = {json.dumps(item)[:80]}")
        return "\n".join(lines)
    if isinstance(value, list):
        if not value:
            return f"{pad}[] (empty)"
        return f"{pad}[{len(value)} items], first:\n" + shape(value[0], depth + 1)
    return f"{pad}{json.dumps(value)[:80]}"


def capability_dates(payload) -> dict:
    """Map each capabilityId to its modificationDate, from either route.

    The two routes return the same three-field item (docs/api-surface.md), so
    one reader serves both and any difference in what comes back is a
    difference in the answer rather than in the parsing.
    """
    if isinstance(payload, dict):
        payload = payload.get("capabilities") or []
    if not isinstance(payload, list):
        return {}

    return {
        item["capabilityId"]: item.get("modificationDate")
        for item in payload
        if isinstance(item, dict) and "capabilityId" in item
    }


def cadence(access_token: str, deviceId: int, rounds: int, every: int) -> None:
    """Ask whether the setup view is as fresh as the per-device route.

    The one thing that decides whether the account poll can replace the
    per-device one, and the one thing no capture has ever established. The two
    carry the same fields and the integration has always built its entities
    from the setup view at startup -- but nobody has compared their *latency*,
    and a setup view served from an aggregated cache would look identical while
    being minutes behind.

    `modificationDate` is what settles it: a per-capability epoch of the last
    change, present in both answers and read by neither. Change something in
    the Cozytouch app while this runs and watch which route notices first.

    Reads only, and roughly what the integration itself spends: two requests
    per round against an interval of its own.
    """
    print(
        f"=== cadence: device {deviceId}, {rounds} rounds every {every}s\n"
        "  Change a setpoint in the app while this runs.\n"
        "  'lag' is per-device minus setup-view; a column of zeroes means the\n"
        "  setup view is as fresh as the route it would replace.\n"
    )

    previous = {}
    for round_number in range(rounds):
        if round_number:
            time.sleep(every)

        _, setup = get(API + "/magellan/cozytouch/setupviewv2", access_token)
        embedded = {}
        if isinstance(setup, list) and setup:
            for dev in setup[0].get("devices", []):
                if dev.get("deviceId") == deviceId:
                    embedded = capability_dates(dev.get("capabilities"))
                    break

        _, direct_payload = get(
            API + f"/magellan/capabilities/?deviceId={deviceId}", access_token
        )
        direct = capability_dates(direct_payload)

        disagree = {
            capabilityId: (embedded.get(capabilityId), stamp)
            for capabilityId, stamp in direct.items()
            if embedded.get(capabilityId) != stamp
        }
        moved = sorted(
            capabilityId
            for capabilityId, stamp in direct.items()
            if previous.get(capabilityId, stamp) != stamp
        )
        previous = direct

        print(
            f"  round {round_number + 1:>3}"
            f"  capabilities: {len(direct):>3} direct / {len(embedded):>3} embedded"
            f"  disagreeing: {len(disagree):>3}"
            f"  changed since last round: {moved if moved else '-'}"
        )
        for capabilityId, (embedded_at, direct_at) in sorted(disagree.items())[:5]:
            lag = (
                direct_at - embedded_at
                if isinstance(direct_at, int) and isinstance(embedded_at, int)
                else "?"
            )
            print(
                f"      capability {capabilityId}: setup view {embedded_at},"
                f" per-device {direct_at}, lag {lag}s"
            )

    print(
        "\n  A disagreeing count that stays at 0 says the account poll loses"
        "\n  nothing. A capability that changes and shows a positive lag every"
        "\n  round says the setup view is cached, and the per-device poll has"
        "\n  to stay the beat.\n"
    )


# One of each family the account or the table can speak for: a gas boiler, a
# heat pump, a room air conditioner, a hub. Overridden by the ids after
# --errors.
ERRORS_MODELS = (56, 76, 557, 1758)

_ERRORS_BASE = "/magellan/productmodels/models/{model}/detailederrors"

# The pair a matrix row would be looked up by, twice over: the vendor ships a
# product code and an IHM code and nothing yet says which one the fault-code
# capability carries.
ERRORS_CODE_FIELDS = (
    "parentProductErrorCode",
    "parentIhmErrorCode",
    "childProductErrorCode",
    "childIhmErrorCode",
)


def detailed_errors(access_token: str, models: tuple[int, ...]) -> None:
    """Dump the vendor's fault table for each model, and ask what language.

    The route takes no parameters -- it answers the whole table -- so this is
    one read per model. What it has to settle is which of the two code fields
    a matrix row's majorCode/minorCode matches, and whether the labels follow
    Accept-Language or the account's own country.
    """
    for model in models:
        route = API + _ERRORS_BASE.format(model=model)
        status, body = get(route, access_token)
        print(f"=== detailederrors: model {model} -> {status}")

        if not isinstance(body, list):
            print(f"  {str(body)[:200]}\n")
            continue

        print(f"  {len(body)} rows")
        for row in body:
            codes = " ".join(
                f"{field.replace('ErrorCode', '')}={row.get(field)}"
                for field in ERRORS_CODE_FIELDS
            )
            label = (row.get("parentErrorLabel") or "").strip()
            child = (row.get("childErrorLabel") or "").strip()
            print(f"    {codes} | {label}" + (f" / {child}" if child else ""))

        # Same table in English, or the same French either way.
        _, english = get(route, access_token, language="en-GB")
        if isinstance(english, list) and english:
            print(f"  en-GB first label: {english[0].get('parentErrorLabel')!r}")
        print()


def main() -> None:
    """Probe the setup view, then each route in turn."""
    if not os.environ.get("COZYTOUCH_USER"):
        sys.exit("set COZYTOUCH_USER")
    if not password():
        sys.exit("password is empty -- check COZYTOUCH_PASS_FILE")

    access_token = token()
    print("authenticated\n")

    # The setup view is what the integration builds every device from, and it
    # embeds each device's capabilities, so it answers most questions alone.
    status, setup = get(API + "/magellan/cozytouch/setupviewv2", access_token)
    print(f"=== /magellan/cozytouch/setupviewv2 -> {status}")
    device_ids = []
    if isinstance(setup, list) and setup:
        # Everything the integration reads lives in devices[]; the other
        # top-level keys have never been looked at.
        print(f"  top-level keys: {sorted(setup[0].keys())}")
        for key, val in setup[0].items():
            if key == "devices":
                continue
            if isinstance(val, list):
                sample = f"[{len(val)} items]" + (
                    f", first keys {sorted(val[0].keys())}"
                    if val and isinstance(val[0], dict) else ""
                )
                print(f"    {key} = {sample}")
            elif isinstance(val, dict):
                print(f"    {key} = keys {sorted(val.keys())}")
            else:
                print(f"    {key} = {json.dumps(val)[:80]}")
        for device in setup[0].get("devices", []):
            device_ids.append(device["deviceId"])
            print(f"  device {device['deviceId']} modelId={device.get('modelId')}")
            for field in DEVICE_FIELDS:
                print(f"    {field} = {json.dumps(device.get(field))}")
            capabilities = device.get("capabilities") or []
            if capabilities:
                print(f"    capability item keys: {sorted(capabilities[0].keys())}")
                print(f"    sample: {json.dumps(capabilities[0])[:200]}")
    else:
        print(f"  unexpected payload: {str(setup)[:200]}")
    print()

    if "--errors" in sys.argv:
        after = [arg for arg in sys.argv[sys.argv.index("--errors") + 1:]
                 if arg.isdigit()]
        models = tuple(int(arg) for arg in after) or ERRORS_MODELS
        detailed_errors(access_token, models)
        return

    if "--cadence" in sys.argv and device_ids:
        cadence(access_token, device_ids[0], rounds=40, every=15)
        return

    routes = list(ROUTES_KNOWN)
    routes += [f"/magellan/capabilities/?deviceId={d}" for d in device_ids[:1]]
    if "--new-routes" in sys.argv:
        routes += list(ROUTES_NEW)
    if "--explore" in sys.argv:
        routes += list(ROUTES_EXPLORE)
        # An item endpoint may say more than the collection did.
        _, setups = get(API + "/magellan/setups", access_token)
        if isinstance(setups, list) and setups:
            routes.append(f"/magellan/setups/{setups[0].get('id')}")

    for route in routes:
        status, body = get(API + route, access_token)
        print(f"=== {route} -> {status}")
        print(shape(body, 1) if isinstance(body, (dict, list)) else f"  {body}")
        print()


if __name__ == "__main__":
    main()
