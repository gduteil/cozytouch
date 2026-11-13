"""How the Pagosa hub spends Overkiz's request quota.

On one Pagosa account (2026-11-11 to 13) the full ``/setup``, read every
240 s, answered 429 once a day with a Retry-After of about 84 200 s, and the
hub then refused every command for 23 h, although Overkiz carried out a
command five minutes after a restart. These pin the answer : a poll reads the
heater's states rather than the whole setup between full reads, a 429 waits
an hour at most, and a 429 on the setup does not hold back a command (nor the
other way round). See docs/decisions.md, *The Pagosa's request quota*.

The fake session is local on purpose, like test_polling.py's.
"""

import asyncio
import copy
import json
import pathlib
import time

import pytest

from custom_components.cozytouch.pagosa import hub as hub_module
from custom_components.cozytouch.pagosa.hub import PagosaHub

CAPTURE = pathlib.Path(__file__).parent.parent / "scripts" / "test_ha" / "pagosa.json"


class FakeResponse:
    def __init__(self, payload=None, status=200, headers=None):
        self._payload = payload
        self.status = status
        self.headers = headers or {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def json(self, content_type=None):
        return self._payload

    async def text(self):
        return json.dumps(self._payload)


class FakeSession:
    """Answers by the end of the path ; records every path asked."""

    def __init__(self):
        self.answers: dict[str, FakeResponse] = {}
        self.asked: list[str] = []
        self.closed = False

    def _answer(self, url):
        self.asked.append(url)
        for suffix, response in self.answers.items():
            if url.endswith(suffix):
                return response
        raise AssertionError(f"unexpected request {url}")

    def get(self, url, **_):
        return self._answer(url)

    def post(self, url, **_):
        return self._answer(url)


def make_hub():
    capture = json.loads(CAPTURE.read_text())
    the_hub = object.__new__(PagosaHub)
    the_hub._deviceId = None
    the_hub._pagosa_optimistic_states = {}
    the_hub._setup = copy.deepcopy(capture["setupviewv2"][0])
    the_hub._is_overkiz = True
    the_hub.online = True
    the_hub._overkiz_host = hub_module.OVERKIZ_HOST
    the_hub._overkiz_retry_after = 0.0
    the_hub._overkiz_command_retry_after = 0.0
    the_hub._overkiz_last_setup_refresh = 0.0
    the_hub._overkiz_last_full_setup = time.monotonic()
    the_hub._overkiz_refresh_lock = asyncio.Lock()
    the_hub._session = FakeSession()
    the_hub._apply_overkiz_setup(capture["overkiz_setup"])
    the_hub._deviceId = the_hub._overkiz_device["deviceURL"]
    return the_hub, capture


def run(coro):
    return asyncio.run(coro)


def away_zero(the_hub):
    return the_hub.async_execute_overkiz_command(
        "setAwayModeDuration", [0], refresh=False
    )


def states_suffix(device):
    url = hub_module.quote(device["deviceURL"], safe="")
    return "/setup/devices/" + url + "/states"


def test_a_poll_reads_the_heaters_states_not_the_whole_setup():
    the_hub, _ = make_hub()
    heater = the_hub._overkiz_device
    states = [{"name": "core:OperatingModeState", "type": 11,
               "value": {"relaunch": "off", "absence": "off"}}]
    the_hub._session.answers[states_suffix(heater)] = FakeResponse(states)
    if the_hub._overkiz_energy_device:
        the_hub._session.answers[states_suffix(the_hub._overkiz_energy_device)] = (
            FakeResponse([])
        )

    assert run(the_hub._refresh_overkiz_setup()) is True
    assert not any(url.endswith("/setup") for url in the_hub._session.asked)
    assert the_hub.get_overkiz_state("core:OperatingModeState") == {
        "relaunch": "off", "absence": "off"
    }


def test_the_whole_setup_is_read_again_after_an_hour():
    the_hub, capture = make_hub()
    the_hub._overkiz_last_full_setup -= hub_module.OVERKIZ_FULL_SETUP_INTERVAL + 1
    the_hub._session.answers["/setup"] = FakeResponse(capture["overkiz_setup"])

    assert run(the_hub._refresh_overkiz_setup()) is True
    assert the_hub._session.asked[-1].endswith("/setup")


def test_a_states_endpoint_that_fails_falls_back_to_the_setup():
    the_hub, capture = make_hub()
    the_hub._session.answers[states_suffix(the_hub._overkiz_device)] = FakeResponse(
        None, status=404
    )
    the_hub._session.answers["/setup"] = FakeResponse(capture["overkiz_setup"])

    assert run(the_hub._refresh_overkiz_setup()) is True
    assert the_hub._session.asked[-1].endswith("/setup")


def test_a_day_long_retry_after_waits_an_hour_at_most():
    the_hub, _ = make_hub()
    the_hub._overkiz_last_full_setup -= hub_module.OVERKIZ_FULL_SETUP_INTERVAL + 1
    the_hub._session.answers["/setup"] = FakeResponse(
        None, status=429, headers={"Retry-After": "84204"}
    )

    assert run(the_hub._refresh_overkiz_setup()) is False
    remaining = the_hub._overkiz_rate_limit_remaining()
    assert 0 < remaining <= hub_module.OVERKIZ_MAX_RETRY_DELAY


def test_a_setup_429_does_not_hold_back_a_command():
    the_hub, _ = make_hub()
    the_hub._overkiz_last_full_setup -= hub_module.OVERKIZ_FULL_SETUP_INTERVAL + 1
    the_hub._session.answers["/setup"] = FakeResponse(
        None, status=429, headers={"Retry-After": "84204"}
    )
    run(the_hub._refresh_overkiz_setup())
    the_hub._session.answers["/exec/apply"] = FakeResponse({"execId": "1"})

    run(away_zero(the_hub))
    assert the_hub._session.asked[-1].endswith("/exec/apply")


def test_a_command_429_does_not_hold_back_the_polls():
    the_hub, _ = make_hub()
    the_hub._session.answers["/exec/apply"] = FakeResponse(
        None, status=429, headers={"Retry-After": "600"}
    )

    with pytest.raises(hub_module.exceptions.HomeAssistantError):
        run(away_zero(the_hub))
    assert the_hub._overkiz_command_rate_limit_remaining() > 0
    assert the_hub._overkiz_rate_limit_remaining() == 0
