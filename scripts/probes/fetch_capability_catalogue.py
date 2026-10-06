r"""Fetch the vendor's own catalogue of capabilities, models and products.

`Magellan_ProductModels` 1.9 declares `GET /magellan/productmodels/capabilities`
-- every capability id with its name, description, type, unit, bounds, enum
members and an `accessType` bitmask (Read=1, Refresh=2, Write=4). The spec came
from Atlantic's own WSO2 devportal, which serves each API's Swagger without
authenticating; `docs/api-surface.md` had ruled this namespace out after ~90
probes that never reached it.

Every read-only route of the same three APIs is here, not only the catalogue,
because the spec saying a route exists is not the same as a private-person
token being allowed to read it. A run on 2026-09-22 answered 200 on fourteen of
the twenty, 403 on the four that are partner or admin scope, and 400 on the two
that want a query parameter nothing here knows. `docs/api-surface.md` has the
table; re-running this is how to find out whether it still holds.

Read-only throughout -- every route here is a GET, and the PATCH, PUT, POST and
DELETE the same APIs declare are deliberately absent.

Every answer is saved under `.endpoints/` at the repository root, one file per
route and the refusals with them, because a 403 on the per-device write rule is
a finding and not a blank. That directory is git-ignored: it is half a megabyte
of vendor JSON re-fetched in one call, and what the project keeps is what was
*concluded* from it, in `docs/decisions.md` -- and, for the three catalogue
routes, `scripts/*_catalogue.jsonl`. Only the maintainer runs it (MEMORY.md).
Run from the repository root:

    umask 077
    pbpaste > ~/.cozytouch-pass
    COZYTOUCH_USER=you@example.com \
      COZYTOUCH_PASS_FILE=~/.cozytouch-pass \
      python3 scripts/probes/fetch_capability_catalogue.py
    rm -f ~/.cozytouch-pass
"""

import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
import probe_api

OUT = pathlib.Path(__file__).resolve().parents[2] / ".endpoints"

# Routes that need nothing but a token.
FIXED = (
    "/magellan/productmodels/capabilities",
    "/magellan/productmodels/structures",
    "/magellan/productmodels/families",
    # The list, against which fetch_model_catalogue.py sweeps 2500 ids one at
    # a time. If this answers, that sweep is one call.
    "/magellan/productmodels/models",
    # productId is what model.py classifies on, and the vendor's own table of
    # them has never been seen.
    "/magellan/productmodels/products",
    "/magellan/productmodels/productnames",
    "/magellan/productmodels/connectivitydiagnosis",
    "/magellan/devices",
    # Expected to refuse: admin scope. A 403 and a 200 are different answers.
    "/magellan-admin/referentials/capabilities-enums",
)

# Routes taking an id, filled from the account's own first device. The pair
# (capability, device) is the vendor's "write rule": bounds, enum members and
# isReadOnly for that capability *on that device*.
TEMPLATED = (
    "/magellan/productmodels/capabilities/{capabilityId}",
    "/magellan/productmodels/capabilities?productid={productId}",
    "/magellan/productmodels/families/{familyId}",
    "/magellan/productmodels/products/{productId}",
    "/magellan/productmodels/models/{modelId}/errors",
    "/magellan/productmodels/models/{modelId}/documentations",
    "/magellan/capabilities/{capabilityId}/devices/{deviceId}",
    "/magellan/devices/{deviceId}/details",
    "/magellan/devices/{deviceId}/consumptions",
    "/magellan/devices/{deviceId}/thermal-programming/available",
    "/magellan/devices/{deviceId}/domestic-hot-water-programming/available",
)


def filename(route: str) -> str:
    """One file per route, named after the route itself."""
    slug = route.strip("/").replace("/", "_").replace("?", "_").replace("=", "-")
    return slug + ".json"


def report(route: str, status, body) -> None:
    """Print what a route answered, and save it whole."""
    print(f"=== {route} -> {status}")

    OUT.mkdir(parents=True, exist_ok=True)
    # The status travels with the body: a file holding
    # `{"code": "900908", ...}` and nothing else does not say whether that was
    # a refusal or a route answering 200 with a complaint in it.
    (OUT / filename(route)).write_text(
        json.dumps(
            {"route": route, "status": status, "body": body},
            indent=1,
            ensure_ascii=False,
        )
    )

    if status != 200 or not isinstance(body, (list, dict)):
        print(f"    {str(body)[:200]}")
        print(f"    saved -> {filename(route)}\n")
        return

    count = len(body) if isinstance(body, list) else 1
    head = body[0] if isinstance(body, list) and body else body
    print(f"    {count} items -> {filename(route)}")
    if isinstance(head, dict):
        print(f"    keys: {sorted(head.keys())}")
        print(f"    sample: {json.dumps(head, ensure_ascii=False)[:300]}")
    print()


def main() -> None:
    """Ask for each route in turn, and save what answers."""
    access_token = probe_api.token()
    print("authenticated\n")

    for route in FIXED:
        report(route, *probe_api.get(probe_api.API + route, access_token))

    status, setup = probe_api.get(
        probe_api.API + "/magellan/cozytouch/setupviewv2", access_token
    )
    devices = setup[0].get("devices", []) if isinstance(setup, list) and setup else []
    if not devices:
        print(f"no device to fill the templated routes with (setup view {status})")
        return

    device = devices[0]
    ids = {
        "deviceId": device["deviceId"],
        "modelId": device.get("modelId"),
        "productId": device.get("productId"),
        "familyId": device.get("modelFamily"),
        # A capability the device actually reports, so the write rule has
        # something to answer about.
        "capabilityId": (device.get("capabilities") or [{}])[0].get("capabilityId"),
    }
    print(f"filling templated routes from {json.dumps(ids)}\n")

    for template in TEMPLATED:
        route = template.format(**ids)
        report(route, *probe_api.get(probe_api.API + route, access_token))


if __name__ == "__main__":
    main()
