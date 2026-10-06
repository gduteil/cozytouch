r"""Measure how long a write takes to show up, on each of the two planes.

**This WRITES to the live account**: it changes what the hardware is doing.
Like every script here that logs in, only the maintainer runs it, never an
agent (MEMORY.md) -- a refused login is what can lock the account.

Three numbers in this repository are guesses, and one measurement settles all
of them : `PENDING_WRITE_GRACE` (60 s, documented as a guess),
`WRITE_BURST_DELAYS` (3, 10, 25), and whether the burst should read
`setupviewv2` once or `/capabilities` once per device.

The question is whether `/magellan/capabilities/?deviceId=` reports a write
before `setupviewv2` does. The vendor app reads only the first and never polls
the second, which looks like an answer but is not one : it may be a shape
choice and nothing more. `docs/decisions.md` records the targeted refresh
answering stale too, which points at the cloud rather than at either route.

This WRITES. It sets one capability on one device of your own account, then
watches both planes until each agrees. Nothing is defaulted : the device, the
capability and the value are all required, so it cannot be run by accident.
Pick something harmless and reversible -- a setpoint you then set back.

Run from the repository root:

    umask 077
    pbpaste > ~/.cozytouch-pass
    COZYTOUCH_USER=you@example.com \
      COZYTOUCH_PASS_FILE=~/.cozytouch-pass \
      python3 scripts/probes/probe_propagation.py \
        --device 12345 --capability 100 --value 20
    rm -f ~/.cozytouch-pass
"""

import argparse
import json
import pathlib
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from probe_api import API, get, token

# Two requests a round. `rateLimit` reads 30 on this account and nobody knows
# what it counts, so this stays under it rather than finding out during a
# measurement. See docs/api-surface.md.
POLL_EVERY = 5.0


def post(path: str, body: dict, access_token: str):
    """POST a route, returning (status, parsed body or error text)."""
    req = urllib.request.Request(
        API + path,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode()[:200]


def value_in(capabilities, capabilityId: int):
    """The value of one capability in a list, or None when it is absent."""
    for capability in capabilities or []:
        if capability.get("capabilityId") == capabilityId:
            return capability.get("value")
    return None


def from_capabilities(access_token: str, deviceId: int, capabilityId: int):
    """What the per-device route says, which is the one the app polls."""
    status, body = get(
        f"{API}/magellan/capabilities/?deviceId={deviceId}", access_token
    )
    if status != 200 or not isinstance(body, list):
        return f"HTTP {status}"
    return value_in(body, capabilityId)


def from_setup_view(access_token: str, capabilityId: int) -> dict[int, str]:
    """What the account-wide route says, for every device that carries the id.

    One request answers for the whole account, which is the property the burst
    is built on -- and it is what makes watching the siblings cost nothing
    here. See docs/decisions.md.
    """
    status, body = get(API + "/magellan/cozytouch/setupviewv2", access_token)
    if status != 200 or not isinstance(body, list) or not body:
        return {}

    found = {}
    for device in body[0].get("devices", []):
        value = value_in(device.get("capabilities"), capabilityId)
        if value is not None:
            found[device["deviceId"]] = value
    return found


def await_execution(executionId: int, access_token: str) -> None:
    """Wait for the write's execution to report completion, as account.py does."""
    for _ in range(30):
        _, body = get(f"{API}/magellan/executions/{executionId}", access_token)
        state = body.get("state") if isinstance(body, dict) else None
        if state in (1, 2, 3, 4, 5):
            print(f"  execution {executionId} -> state {state}")
        if state in (3, 4, 5):
            return
        time.sleep(1.0)
    print("  execution never reported completion; watching anyway")


def main() -> None:
    """Write one capability, then watch both planes until each agrees."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", type=int, required=True)
    parser.add_argument("--capability", type=int, required=True)
    parser.add_argument("--value", required=True)
    parser.add_argument("--seconds", type=float, default=180.0)
    args = parser.parse_args()

    access_token = token()
    deviceId, capabilityId, wanted = args.device, args.capability, args.value

    before_caps = from_capabilities(access_token, deviceId, capabilityId)
    before_view = from_setup_view(access_token, capabilityId)
    print(f"the written device, /capabilities : {before_caps!r}")
    print(f"every device carrying {capabilityId}, setupviewv2 : {before_view}")
    if before_caps == wanted:
        sys.exit(
            "the capability already reads the value you asked for, so nothing "
            "would be measured. Pick a different value."
        )

    status, executionId = post(
        "/magellan/executions/writecapability",
        {"deviceId": deviceId, "capabilityId": capabilityId, "value": wanted},
        access_token,
    )
    if status != 201:
        sys.exit(f"write refused (HTTP {status}): {executionId}")

    print(f"\nwrote {wanted!r} on {deviceId}, execution {executionId}")
    await_execution(executionId, access_token)

    # The clock starts when the cloud said the write was done, which is what
    # the integration's own delays are measured from.
    started = time.monotonic()
    first_caps = None
    first_view: dict[int, float] = {}

    while (elapsed := time.monotonic() - started) < args.seconds:
        caps = from_capabilities(access_token, deviceId, capabilityId)
        view = from_setup_view(access_token, capabilityId)

        if first_caps is None and caps == wanted:
            first_caps = elapsed
        for otherId, value in view.items():
            if value == wanted and otherId not in first_view:
                first_view[otherId] = elapsed

        agreed = sorted(k for k, v in view.items() if v == wanted)
        print(
            f"  +{elapsed:5.1f}s  /capabilities({deviceId})={caps!r}"
            f"  setupviewv2 agreeing: {agreed}"
        )
        if first_caps is not None and len(first_view) == len(view):
            break

        time.sleep(POLL_EVERY)

    print()
    print(f"/capabilities on {deviceId} agreed after : {first_caps}")
    for otherId in sorted(before_view):
        when = first_view.get(otherId)
        which = "written" if otherId == deviceId else "sibling"
        print(f"setupviewv2 on {otherId} ({which}) agreed after : {when}")
    print()
    print("Set the capability back when you are done.")


if __name__ == "__main__":
    main()
