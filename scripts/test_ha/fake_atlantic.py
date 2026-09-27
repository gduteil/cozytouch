"""A stand-in for Atlantic's cloud, built from a diagnostics dump.

Serves the endpoints `account.py` calls, from what a real account reported,
so Home Assistant can be run, restarted and driven against it without a
login to anybody's account. Writes land in memory and are read back by the
next poll.

What the real cloud does beyond storing a write is guessed, and only where
a capture showed the effect :

- 102020 written on any device reaches every room of the account
  (MEMORY.md, settled by capturing the iOS app).
- 152 and 222 on a gateway are mirrored onto its rooms as 100261 and
  100260, which is how the 2026-09-25 Navizone dump reads : the same values,
  changed within the same second.

The consumption endpoint answers with what the dump's `consumptions`
carries, moved forward whole so its latest day is today : a dump taken last
month would otherwise show last month's day as today's. A dump without it
answers an empty list, which is what a setup with no meter is assumed to get.

Anything else -- a programmed absence turning on at its start, a 429 --
is not simulated. This tests the integration's reading of the API, not the
cloud.

    python scripts/test_ha/fake_atlantic.py DUMP.json [--port 8765]
"""

import argparse
import copy
import itertools
import json
import pathlib
import time

from aiohttp import web

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent

# What a gateway write is mirrored onto, on every device it is master of.
MIRRORED_ON_ROOMS = {152: 100261, 222: 100260}

# What reaches every room whichever device it was written on.
HOUSEHOLD_WIDE = (102020,)


def setup_from_dump(dump: dict) -> dict:
    """The one setup setupviewv2 returns, rebuilt from a diagnostics dump."""
    data = dump["data"]
    setup = copy.deepcopy(data["setup"])
    setup["zones"] = copy.deepcopy(data["zones"])
    setup["devices"] = []

    for device in data["devices"]:
        values = device["capabilities"]["values"]
        dates = device["capabilities"].get("modificationDates", {})
        setup["devices"].append(
            {
                "deviceId": device["deviceId"],
                "name": device["name"],
                "gatewaySerialNumber": f"FAKE-{device['deviceId']}",
                "modelId": device["modelId"],
                "productId": device["productId"],
                "zoneId": device["zoneId"],
                "tags": copy.deepcopy(device.get("tags") or []),
                "customName": device.get("customName"),
                "longName": device.get("longName"),
                "modelFamily": device.get("modelFamily"),
                "productRange": device.get("productRange"),
                "masterDeviceId": device.get("masterDeviceId"),
                "isAvailable": device.get("isAvailable", True),
                "capabilities": [
                    {
                        "capabilityId": int(capabilityId),
                        "value": value,
                        "modificationDate": dates.get(capabilityId),
                    }
                    for capabilityId, value in values.items()
                ],
            }
        )

    return setup


def consumptions_from_dump(dump: dict) -> tuple[int, list]:
    """The status and answer the dump says the consumption endpoint gave."""
    carried = dump["data"].get("consumptions") or {}
    return carried.get("status") or 200, carried.get("answer") or []


def as_of_today(answer: list, now: float) -> list:
    """The same days, shifted so the latest one starts today at 00:00 UTC."""
    dates = [
        period["date"]
        for series in answer
        for period in series.get("consumptionPeriods", [])
    ]
    if not dates:
        return answer

    shift = int(now) // 86400 * 86400 - max(dates)
    moved = copy.deepcopy(answer)
    for series in moved:
        for period in series.get("consumptionPeriods", []):
            period["date"] += shift
    return moved


class FakeAtlantic:
    """The account's state, and the handlers that read and write it."""

    def __init__(self, setup: dict, consumptions: tuple[int, list] = (200, [])) -> None:
        self.setup = setup
        self.consumptions = consumptions
        self.executions = itertools.count(1)
        self.log: list[str] = []

    def device(self, deviceId: int) -> dict | None:
        return next(
            (d for d in self.setup["devices"] if d["deviceId"] == deviceId), None
        )

    def store(self, device: dict, capabilityId: int, value: str) -> bool:
        """Set one capability, if the device reports it."""
        for capability in device["capabilities"]:
            if capability["capabilityId"] == capabilityId:
                capability["value"] = value
                capability["modificationDate"] = int(time.time())
                return True
        return False

    def write(self, deviceId: int, capabilityId: int, value: str) -> bool:
        device = self.device(deviceId)
        if device is None or not self.store(device, capabilityId, value):
            return False

        for other in self.setup["devices"]:
            if other.get("masterDeviceId") == deviceId and (
                mirrored := MIRRORED_ON_ROOMS.get(capabilityId)
            ):
                self.store(other, mirrored, value)
            if capabilityId in HOUSEHOLD_WIDE and other is not device:
                self.store(other, capabilityId, value)

        return True

    async def token(self, request: web.Request) -> web.Response:
        form = await request.post()
        self.log.append(f"login {form.get('username')}")
        return web.json_response(
            {"access_token": "fake", "token_type": "Bearer", "expires_in": 3600}
        )

    async def setup_view(self, request: web.Request) -> web.Response:
        return web.json_response([self.setup])

    async def capabilities(self, request: web.Request) -> web.Response:
        device = self.device(int(request.query.get("deviceId", 0)))
        return web.json_response(device["capabilities"] if device else [])

    async def write_capability(self, request: web.Request) -> web.Response:
        body = await request.json()
        ok = self.write(body["deviceId"], body["capabilityId"], str(body["value"]))
        self.log.append(
            f"write {body['deviceId']} {body['capabilityId']}={body['value']}"
            + ("" if ok else " (not reported, ignored)")
        )
        return web.json_response(next(self.executions), status=201)

    async def execution(self, request: web.Request) -> web.Response:
        return web.json_response({"state": 3})

    async def put_setup(self, request: web.Request) -> web.Response:
        body = await request.json()
        self.setup["absence"] = body.get("absence", {})
        self.log.append(f"absence {self.setup['absence']}")
        return web.Response(status=204)

    async def consumption(self, request: web.Request) -> web.Response:
        status, answer = self.consumptions
        self.log.append(f"consumptions {request.query.get('periodicity')} ({status})")
        if status != 200:
            return web.json_response({"error": "fake"}, status=status)
        return web.json_response(as_of_today(answer, time.time()))

    async def fault_table(self, request: web.Request) -> web.Response:
        return web.json_response([])

    async def catalogue(self, request: web.Request) -> web.Response:
        path = ROOT / "scripts" / "capability_catalogue.jsonl"
        rows = [json.loads(line) for line in path.read_text().splitlines() if line]
        return web.json_response(rows)

    async def journal(self, request: web.Request) -> web.Response:
        """What the integration has done, for whoever drives the test."""
        return web.json_response(self.log)


def application(setup: dict, consumptions=(200, [])) -> web.Application:
    fake = FakeAtlantic(setup, consumptions)
    app = web.Application()
    app.add_routes(
        [
            web.post("/users/token", fake.token),
            web.get("/magellan/cozytouch/setupviewv2", fake.setup_view),
            web.get("/magellan/capabilities/", fake.capabilities),
            web.post("/magellan/executions/writecapability", fake.write_capability),
            web.get("/magellan/executions/{id}", fake.execution),
            web.put("/magellan/v2/setups/{id}", fake.put_setup),
            web.get("/magellan/setups/{id}/consumptions", fake.consumption),
            web.get(
                "/magellan/productmodels/models/{id}/detailederrors", fake.fault_table
            ),
            web.get("/magellan/productmodels/capabilities", fake.catalogue),
            web.get("/fake/journal", fake.journal),
        ]
    )
    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("dump", type=pathlib.Path)
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    dump = json.loads(args.dump.read_text())
    web.run_app(
        application(setup_from_dump(dump), consumptions_from_dump(dump)),
        host="127.0.0.1",
        port=args.port,
    )


if __name__ == "__main__":
    main()
