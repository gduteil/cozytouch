"""Telling a wrong password apart from a server that is not answering.

Both used to end the same way: `online = False`, then ConfigEntryNotReady, then
retry forever with the credentials that were already refused. Somebody who
changed their Cozytouch password saw an integration that could not connect and
was never asked for the new one -- and, because retrying is all that path knew
how to do, one refused login per device per minute for as long as the
installation ran. Repeated failed logins are the one thing that could get an
Atlantic account locked out (docs/api-surface.md).

These cover the whole path: what the token endpoint said, what the account
raises, what setup and the poll turn it into, and what the dialog does with the
password somebody types. `FakeSession` is the first stand-in in this suite that
reaches the HTTP layer at all -- the rest of the account's calls are still
untested, and it is the thing to extend when closing that.
"""

import asyncio
from types import SimpleNamespace

import pytest

from custom_components.cozytouch import account as account_module, config_flow as cf
from custom_components.cozytouch.account import (
    CannotConnect,
    CozytouchAccount,
    InvalidAuth,
)
from custom_components.cozytouch.hub import Hub
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

TOKEN_OK = {"token_type": "Bearer", "access_token": "a-token", "expires_in": 3600}
SETUP_VIEW = [{"id": 1, "name": "Home", "devices": [], "zones": []}]

REFUSED = {"error": "invalid_grant"}


class FakeResponse:
    """One answer: a status, and either a JSON body or an exception."""

    def __init__(self, payload, status=200):
        self._payload = payload
        self.status = status

    async def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    """An aiohttp session answering from a script instead of a network.

    Requests match on the tail of the URL, so a case says what the token
    endpoint replies without restating the whole route. Every request is
    recorded, which is how the login count is checked rather than assumed.
    """

    def __init__(self, answers, raises=None):
        self._answers = answers
        self._raises = raises
        self.requests = []

    def _answer(self, url):
        self.requests.append(url)
        if self._raises is not None:
            raise self._raises
        for tail, answer in self._answers.items():
            if tail in url:
                return answer
        raise AssertionError(f"no scripted answer for {url}")

    def post(self, url, **kwargs):
        return self._answer(url)

    def get(self, url, **kwargs):
        return self._answer(url)

    def put(self, url, **kwargs):
        return self._answer(url)

    def logins(self):
        return [url for url in self.requests if "/users/token" in url]


def make_account(monkeypatch, answers=None, raises=None):
    """A real account over a scripted session."""
    session = FakeSession(answers or {}, raises)
    monkeypatch.setattr(account_module, "async_get_clientsession", lambda hass: session)
    account = CozytouchAccount(SimpleNamespace(), "someone@example.test", "old")

    return account, session


def refused(monkeypatch):
    return make_account(monkeypatch, {"/users/token": FakeResponse(REFUSED)})


# --- what the account makes of the answer ---------------------------------


def test_a_refused_password_is_not_a_connection_problem(monkeypatch):
    """invalid_grant is OAuth2's way of saying the credentials are wrong, and
    it is the one answer that must not be folded into "retry later".
    """
    account, _ = refused(monkeypatch)

    with pytest.raises(InvalidAuth):
        asyncio.run(account.connect())

    assert account.online is False


def test_a_malformed_token_response_is_a_connection_problem(monkeypatch):
    """A body with no token in it is the gateway misbehaving, not proof about
    the password. Saying "invalid auth" here sends somebody to reset a
    password that was fine.
    """
    account, _ = make_account(
        monkeypatch, {"/users/token": FakeResponse({"unexpected": "shape"})}
    )

    assert asyncio.run(account.connect()) is False
    assert account.online is False


def test_a_network_failure_stays_a_connection_problem(monkeypatch):
    account, _ = make_account(monkeypatch, raises=TimeoutError())

    assert asyncio.run(account.connect()) is False
    assert account.online is False


def test_a_good_password_connects(monkeypatch):
    account, _ = make_account(
        monkeypatch,
        {
            "/users/token": FakeResponse(TOKEN_OK),
            "setupviewv2": FakeResponse(SETUP_VIEW),
        },
    )

    assert asyncio.run(account.connect()) is True
    assert account.online is True


def test_a_good_login_is_made_once_for_the_whole_account(monkeypatch):
    """The lock, counted at the HTTP layer rather than at the method call."""
    account, session = make_account(
        monkeypatch,
        {
            "/users/token": FakeResponse(TOKEN_OK),
            "setupviewv2": FakeResponse(SETUP_VIEW),
        },
    )

    async def everyone():
        return await asyncio.gather(*(account.connect() for _ in range(5)))

    assert all(asyncio.run(everyone()))
    assert len(session.logins()) == 1


def test_a_refused_login_is_retried_by_each_waiter(monkeypatch):
    """Pinned because it is the limitation, not the feature.

    A failure leaves `online` False, so every waiter takes the lock, sees
    that, and tries again -- five devices, five refused logins on that tick.
    That is right for a network failure and wrong for a password, and the
    answer is not a cooldown here: it is ConfigEntryAuthFailed stopping the
    coordinators from ever asking again, which the next cases cover. If this
    number ever drops, something added a cooldown and this case should say so.
    """
    account, session = refused(monkeypatch)

    async def everyone():
        for _ in range(5):
            with pytest.raises(InvalidAuth):
                await account.connect()

    asyncio.run(everyone())

    assert len(session.logins()) == 5


# --- what setup and the poll turn it into ---------------------------------


def test_setup_asks_for_a_new_password_rather_than_retrying_the_old_one(monkeypatch):
    """ConfigEntryAuthFailed is what opens the reauth dialog. It also stops the
    coordinator rescheduling itself, which is what ends the retry loop.
    """
    account, _ = refused(monkeypatch)

    with pytest.raises(ConfigEntryAuthFailed):
        asyncio.run(account.connect_or_auth_failed())


def test_setup_still_reports_an_outage_as_an_outage(monkeypatch):
    """False, not an exception: the caller decides that means retry."""
    account, _ = make_account(monkeypatch, raises=TimeoutError())

    assert asyncio.run(account.connect_or_auth_failed()) is False


def test_a_refresh_that_finds_the_password_refused_raises_for_reauth(monkeypatch):
    """The path a password changed while Home Assistant was running takes.

    This is the hub's own fetch, which is the post-write refresh now that the
    account owns the beat -- the same case on the beat is in
    tests/test_polling.py. Both have to raise it: whichever call is the first
    to meet the refused password is the one that has to ask for a new one.
    """
    account, _ = refused(monkeypatch)
    hub = hub_over(account)

    with pytest.raises(ConfigEntryAuthFailed):
        asyncio.run(hub._async_update_data())


def test_a_refresh_that_cannot_reach_the_servers_only_fails_the_update(monkeypatch):
    """UpdateFailed keeps its meaning: try the same credentials again later."""
    account, _ = make_account(monkeypatch, raises=TimeoutError())
    hub = hub_over(account)

    with pytest.raises(UpdateFailed):
        asyncio.run(hub._async_update_data())


def hub_over(account):
    """A hub with nothing but what _async_update_data reads."""
    hub = object.__new__(Hub)
    hub._account = account
    hub._deviceId = 1
    hub._timestamp_away_mode_start = None
    hub._timestamp_away_mode_end = None

    return hub


# --- the dialog -----------------------------------------------------------


class FakeEntry:
    def __init__(self, username="someone@example.test", password="old"):
        self.entry_id = "one"
        self.data = {"username": username, "password": password}
        self.options = {}


def make_flow(entry):
    """A reauth flow pointed at one entry, with the abort recorded."""
    flow = cf.ConfigFlow()
    flow.hass = SimpleNamespace()
    flow._get_reauth_entry = lambda: entry

    recorded = {}

    def async_update_reload_and_abort(target, data_updates):
        target.data = {**target.data, **data_updates}
        recorded["data_updates"] = data_updates
        return {"type": "abort", "reason": "reauth_successful"}

    flow.async_update_reload_and_abort = async_update_reload_and_abort
    flow.async_show_form = lambda **kwargs: {"type": "form", **kwargs}

    return flow, recorded


def submit(monkeypatch, flow, password):
    """Answer the dialog, with the network stubbed out."""

    async def validate_input(hass, data):
        if data["password"] == "correct":
            return SimpleNamespace()
        if data["password"] == "offline":
            raise CannotConnect
        raise InvalidAuth

    monkeypatch.setattr(cf, "validate_input", validate_input)

    return asyncio.run(flow.async_step_reauth_confirm({"password": password}))


def test_the_dialog_opens_on_the_password_step():
    flow, _ = make_flow(FakeEntry())

    result = asyncio.run(flow.async_step_reauth({}))

    assert result["type"] == "form"
    assert result["step_id"] == "reauth_confirm"


def test_the_dialog_names_the_account_it_is_asking_about():
    """Somebody with two Cozytouch accounts needs to know which one is being
    refused before typing a password at it.
    """
    flow, _ = make_flow(FakeEntry())

    result = asyncio.run(flow.async_step_reauth_confirm())

    assert result["description_placeholders"] == {"username": "someone@example.test"}


def test_a_correct_password_is_stored(monkeypatch):
    entry = FakeEntry()
    flow, recorded = make_flow(entry)

    result = submit(monkeypatch, flow, "correct")

    assert result["reason"] == "reauth_successful"
    assert recorded["data_updates"] == {"password": "correct"}
    assert entry.data["password"] == "correct"


def test_a_wrong_password_is_not_stored_and_says_so(monkeypatch):
    entry = FakeEntry()
    flow, recorded = make_flow(entry)

    result = submit(monkeypatch, flow, "still wrong")

    assert result["errors"] == {"base": "invalid_auth"}
    assert entry.data["password"] == "old"
    assert recorded == {}


def test_an_outage_during_reauth_does_not_blame_the_password(monkeypatch):
    """The whole point of the split: a server that is not answering must not
    tell somebody the password they just typed correctly is wrong.
    """
    entry = FakeEntry()
    flow, _ = make_flow(entry)

    result = submit(monkeypatch, flow, "offline")

    assert result["errors"] == {"base": "cannot_connect"}
    assert entry.data["password"] == "old"


def test_the_username_is_not_up_for_editing():
    """Changing it would point the entry at a different account, where the
    deviceId of every subentry means nothing -- or, worse, something else.
    """
    flow, _ = make_flow(FakeEntry())

    result = asyncio.run(flow.async_step_reauth_confirm())

    assert list(result["data_schema"].schema) == ["password"]


def test_one_dialog_settles_the_whole_account(monkeypatch):
    """One entry per account, so the credentials exist in exactly one place.

    This is the loop that is absent : with an entry per device, fixing the one
    whose dialog was answered left the others retrying the old password and
    raising a prompt each, so the password had to be copied to every sibling.
    """
    entry = FakeEntry()
    flow, recorded = make_flow(entry)

    submit(monkeypatch, flow, "correct")

    # No hass.config_entries on the stand-in: touching another entry would
    # raise here rather than pass quietly.
    assert recorded["data_updates"] == {"password": "correct"}
    assert not hasattr(flow.hass, "config_entries")
