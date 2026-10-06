r"""Write one capability and watch how far the backend carries it.

**This WRITES to the live account**: it changes what the hardware is doing.
Like every script here that logs in, only the maintainer runs it, never an
agent (MEMORY.md) -- a refused login is what can lock the account.

Capability 7 is the service an air-conditioning system runs. The Cozytouch app
writes it once, on one device, through the same route and the same body this
integration uses -- and all the rooms of the account follow. The integration's
own write stops at the room it was sent to.

So the difference is not the body. This probes the two things that are left :

  --device       which device the write is addressed to. The app's room page
                 writes on the room ; `AirConditioner`, the hub, implements the
                 same service feature, and `GacomaDevice.writeCapabilitySuspend`
                 never checks that the device lists the capability before
                 writing it. So the hub is writable in principle and untried.

  --app-headers  the headers the app sends on every call and this integration
                 sends on none : `X-Operation-ID`, `uniqId`, `appInstallNumber`
                 and its `User-Agent`. A WCF backend routing on the operation
                 id is not far-fetched.

It writes, waits, then prints capability 7 for every device that reports it,
so one run answers whether the write travelled.

    umask 077
    pbpaste > ~/.cozytouch-pass
    COZYTOUCH_USER=you@example.com COZYTOUCH_PASS_FILE=~/.cozytouch-pass \
      python3 scripts/probes/probe_write_service.py --device 12345 --value 3
    rm -f ~/.cozytouch-pass

Run it on a service the system already offers, and read the `before` line it
prints before deciding the run said anything.
"""

import argparse
import importlib.util
import json
import pathlib
import time
import urllib.error
import urllib.request
import uuid

PROBE = importlib.util.spec_from_file_location(
    "probe_api", pathlib.Path(__file__).resolve().parents[1] / "probe_api.py"
)
probe_api = importlib.util.module_from_spec(PROBE)
PROBE.loader.exec_module(probe_api)

API = probe_api.API
SERVICE = 7

# fr/atlantic/middleware/network/interceptor/HeaderInterceptor.java, plus the
# per-route operation id GacomaExecutionApi.java declares on the write.
APP_VERSION = "3.31.0"
APP_HEADERS = {
    "X-Operation-ID": "GacomaWcfService.ExecutionService.Write",
    "uniqId": f"CT{APP_VERSION}AND{uuid.uuid4()}",
    "appInstallNumber": str(uuid.uuid4()),
    "User-Agent": f"cozytouch-android-v{APP_VERSION}",
}


def post(url, access_token, body, extra_headers=None):
    """POST a body, returning (status, parsed body or error text)."""
    req = urllib.request.Request(
        url,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
            **(extra_headers or {}),
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode()[:300]


def patch(url, access_token):
    """PATCH a route with no body, returning (status, parsed body or text)."""
    req = urllib.request.Request(url, method="PATCH")
    req.add_header("Authorization", f"Bearer {access_token}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as err:
        return err.code, err.read().decode()[:300]


def services(access_token, capabilityId):
    """What every device on the account reads as, for one capability."""
    status, body = probe_api.get(
        API + "/magellan/cozytouch/setupviewv2", access_token
    )
    if status != 200:
        return f"setup view said {status}"

    # setupviewv2 answers with a list of setups, one per gateway.
    setups = body if isinstance(body, list) else [body]
    found = {}
    for setup in setups:
        for dev in setup.get("devices", []):
            for capability in dev.get("capabilities", []):
                if capability.get("capabilityId") == capabilityId:
                    found[dev.get("name")] = capability.get("value")
    return found


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", type=int)
    parser.add_argument("--capability", type=int, default=SERVICE)
    parser.add_argument("--value")
    parser.add_argument("--app-headers", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--recalculate", action="store_true")
    parser.add_argument("--wait", type=int, default=15)
    args = parser.parse_args()

    print("login  : ...", flush=True)
    access_token = probe_api.token()
    print("before :", services(access_token, args.capability), flush=True)

    # Two routes the app declares and never calls, and neither does the
    # integration : whether either makes a device re-read a capability the
    # backend holds is the whole question. See docs/api-surface.md.
    if args.refresh:
        print(
            "refresh:",
            *post(
                API + "/magellan/executions/refreshcapability",
                access_token,
                {"deviceId": args.device, "capabilityId": args.capability},
            ),
            flush=True,
        )
    if args.recalculate:
        print(
            "recalc :",
            *patch(
                f"{API}/magellan/capabilities/{args.capability}"
                f"?deviceId={args.device}",
                access_token,
            ),
            flush=True,
        )
    if args.refresh or args.recalculate:
        time.sleep(args.wait)
        print("after  :", services(access_token, args.capability), flush=True)
        return

    # No write asked for : the run was a reading, and it has been printed.
    if args.device is None or args.value is None:
        return

    status, body = post(
        API + "/magellan/executions/writecapability",
        access_token,
        {
            "capabilityId": args.capability,
            "deviceId": args.device,
            "value": args.value,
        },
        APP_HEADERS if args.app_headers else None,
    )
    print(f"write  : {status} {body}", flush=True)
    if status != 201:
        return

    # A 201 only says the execution was created. What it then reports is the
    # difference between a write that happened and one that was refused, and
    # `account.py` waits for it -- so the probe has to as well.
    for _ in range(10):
        time.sleep(3)
        state, execution = probe_api.get(
            API + "/magellan/executions/" + str(body), access_token
        )
        print(f"exec   : {state} {execution}", flush=True)
        if not isinstance(execution, dict) or execution.get("executionState") not in (
            0,
            1,
            6,
            7,
        ):
            break

    time.sleep(args.wait)
    print(f"+{args.wait:>3}s  :", services(access_token, args.capability), flush=True)


if __name__ == "__main__":
    main()
