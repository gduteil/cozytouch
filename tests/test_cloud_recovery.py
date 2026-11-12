"""Recovery from cloud outages must not multiply logins or hide refusals.

Scripted responses exercise the real account client without vendor credentials.
The switch cases use a real refusing Hub, since a False result is different
from the exception the existing away-mode tests already cover.
"""

import asyncio
from copy import deepcopy

import pytest
from test_away_mode import FakeAccount, hub_over, switch_over
from test_polling import (
    TOKEN_OK,
    FakeResponse,
    FakeTimeout,
    connected,
    make_account,
    setup_view,
)

from custom_components.cozytouch.account import CozytouchApiError
from custom_components.cozytouch.switch import CozytouchAwayModeSwitch
from homeassistant.exceptions import HomeAssistantError


class YieldingResponse(FakeResponse):
    """Let every reconnect queue at the lock before the first gets a 429."""

    async def __aenter__(self):
        await asyncio.sleep(0)
        return self


@pytest.mark.parametrize("endpoint", ["/users/token", "setupviewv2"])
def test_a_429_stops_reconnects_already_waiting_at_the_lock(monkeypatch, endpoint):
    account, session = make_account(
        monkeypatch,
        {
            "/users/token": YieldingResponse(TOKEN_OK),
            "setupviewv2": YieldingResponse(setup_view()),
        },
    )
    session._answers[endpoint] = YieldingResponse(
        None, status=429, headers={"Retry-After": "300"}
    )

    async def reconnect():
        return await asyncio.gather(*(account.connect() for _ in range(5)))

    assert asyncio.run(reconnect()) == [False] * 5
    assert len(session.logins()) == 1
    assert account.backoff_remaining > 290


def test_a_timeout_recovers_with_the_existing_token(monkeypatch):
    account, session = connected(monkeypatch)
    session._answers["setupviewv2"] = FakeTimeout()

    with pytest.raises(CozytouchApiError):
        asyncio.run(account.refresh_setup())

    session._answers["setupviewv2"] = FakeResponse(setup_view(value="23"))
    assert asyncio.run(account.connect()) is True
    assert session.logins() == []
    assert account.devices[0]["capabilities"][0]["value"] == "23"


@pytest.mark.parametrize("endpoint", ["setupviewv2", "/magellan/capabilities/"])
def test_a_rejected_token_is_replaced_on_reconnect(monkeypatch, endpoint):
    account, session = connected(monkeypatch)
    session._answers[endpoint] = FakeResponse(None, status=401)

    with pytest.raises(CozytouchApiError):
        asyncio.run(
            account.refresh_setup()
            if endpoint == "setupviewv2"
            else account.fetch_capabilities(1)
        )

    session._answers["setupviewv2"] = FakeResponse(setup_view())
    assert asyncio.run(account.connect()) is True
    assert len(session.logins()) == 1


def test_an_expired_token_is_replaced(monkeypatch):
    account, session = connected(monkeypatch)
    account._token_expiry = 0
    account.check_token()

    assert asyncio.run(account.connect()) is True
    assert len(session.logins()) == 1


@pytest.mark.parametrize(
    "payload",
    [
        None,
        [],
        ValueError("broken JSON"),
        {**TOKEN_OK, "access_token": None},
        {**TOKEN_OK, "expires_in": None},
        {**TOKEN_OK, "expires_in": "invalid"},
        {**TOKEN_OK, "expires_in": "nan"},
        {**TOKEN_OK, "expires_in": "inf"},
    ],
)
def test_malformed_authentication_stays_a_connection_failure(monkeypatch, payload):
    account, session = make_account(
        monkeypatch, {"/users/token": FakeResponse(payload)}
    )

    assert asyncio.run(account.connect()) is False
    assert account.online is False
    assert session.setup_views() == []


@pytest.mark.parametrize(
    "payload",
    [ValueError("broken JSON"), [None], [{}], [{"devices": [None]}]],
)
def test_a_bad_setup_preserves_the_last_complete_view(monkeypatch, payload):
    account, session = connected(monkeypatch)
    previous = deepcopy(account.devices)
    stamped = account.last_poll
    session._answers["setupviewv2"] = FakeResponse(payload)

    with pytest.raises(CozytouchApiError):
        asyncio.run(account.refresh_setup())

    assert account.devices == previous
    assert account.last_poll == stamped
    assert account.online is False


@pytest.mark.parametrize("payload", [ValueError("broken JSON"), [None]])
def test_a_bad_capability_list_is_a_reported_failure(monkeypatch, payload):
    account, session = connected(monkeypatch)
    session._answers["/magellan/capabilities/"] = FakeResponse(payload)

    with pytest.raises(CozytouchApiError):
        asyncio.run(account.fetch_capabilities(1))


@pytest.mark.parametrize("payload", [None, [], ValueError("broken JSON")])
def test_a_bad_execution_does_not_confirm_the_write(monkeypatch, payload):
    account, session = connected(monkeypatch)
    session._answers["/magellan/executions/"] = FakeResponse(payload)

    assert asyncio.run(account._await_execution(123)) is not None
    assert account._pending_writes == {}


@pytest.mark.parametrize(
    ("turn", "reported"),
    [
        (CozytouchAwayModeSwitch.async_turn_on, "0"),
        (CozytouchAwayModeSwitch.async_turn_off, "1"),
    ],
)
def test_a_refused_absence_is_reported_and_restores_the_switch(turn, reported):
    hub = hub_over(FakeAccount(accepts=False), {152: reported, 222: "[0,0]"})
    switch = switch_over(hub)

    with pytest.raises(HomeAssistantError) as raised:
        asyncio.run(turn(switch))

    assert raised.value.translation_key == "write_not_completed"
    assert switch._nb_ignore == 0
    assert hub.log == []
