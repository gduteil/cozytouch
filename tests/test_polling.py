"""One poll for the account, and what happens when Atlantic says slow down.

Two changes are pinned here. The first is that the beat moved: it used to be
one `GET /magellan/capabilities/?deviceId=` per device per minute, and it is
now one `GET setupviewv2` for the whole account -- which carries a capability
list for every device, so the cost stopped growing with the number of devices
somebody ticked at setup.

The second is the reason the first is safe to make. Nothing recognised a 429:
it fell into the generic non-200 branch, which drops `online`, so the next poll
answered a complaint about too many requests with a `POST /users/token` and a
`GET setupviewv2` -- two more requests, one of them a login, and
docs/api-surface.md says repeated failed logins are the one thing that can lock
an account out. Polling faster without fixing that would have made the failure
mode worse in exact proportion to the improvement.

`FakeSession` is the same stand-in `tests/test_reauth.py` introduced, kept
separate rather than imported so a change there cannot quietly rewrite what
these say.
"""

import asyncio
from types import SimpleNamespace

import pytest

from custom_components.cozytouch import account as account_module, hub as hub_module
from custom_components.cozytouch.account import (
    RATE_LIMIT_BACKOFF,
    CozytouchAccount,
    CozytouchRateLimited,
)
from custom_components.cozytouch.hub import (
    DEFAULT_POLL_INTERVAL,
    MAX_POLL_INTERVAL,
    MIN_POLL_INTERVAL,
    AccountCoordinator,
    Hub,
    poll_interval,
)
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed

TOKEN_OK = {"token_type": "Bearer", "access_token": "a-token", "expires_in": 3600}

REFUSED = {"error": "invalid_grant"}


def device(deviceId, value="18"):
    """A device as the setup view reports it, capabilities included.

    The point of the whole change is in this fixture: the setup view answers
    for every device, so what a per-device poll used to fetch one at a time is
    already here.
    """
    return {
        "deviceId": deviceId,
        "name": f"ROOM_{deviceId}",
        "gatewaySerialNumber": "3022-6760-8541",
        "modelId": 557,
        "productId": 65,
        "zoneId": 991904,
        "capabilities": [{"capabilityId": 100, "value": value}],
    }


def setup_view(devices=(1, 2, 3), value="18", rateLimit=30):
    return [
        {
            "id": 1,
            "name": "Home",
            "rateLimit": rateLimit,
            "devices": [device(deviceId, value) for deviceId in devices],
            "zones": [],
        }
    ]


class FakeResponse:
    """One answer: a status, a JSON body, and whatever headers came with it."""

    def __init__(self, payload, status=200, headers=None):
        self._payload = payload
        self.status = status
        self.headers = headers or {}

    async def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class FakeTimeout:
    """A request that never answers: TimeoutError, and no message with it."""

    async def __aenter__(self):
        raise TimeoutError

    async def __aexit__(self, *exc):
        return False


class FakeSession:
    """An aiohttp session answering from a script, and counting the calls."""

    def __init__(self, answers):
        self._answers = answers
        self.requests = []

    def _answer(self, url):
        self.requests.append(url)
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

    def setup_views(self):
        return [url for url in self.requests if "setupviewv2" in url]

    def capability_polls(self):
        return [url for url in self.requests if "/magellan/capabilities/" in url]


def make_account(monkeypatch, answers):
    """A real account over a scripted session, already connected."""
    session = FakeSession(answers)
    monkeypatch.setattr(account_module, "async_get_clientsession", lambda hass: session)
    account = CozytouchAccount(SimpleNamespace(), "someone@example.test", "pw")

    return account, session


def connected(monkeypatch, answers=None):
    """An account that has logged in, so a poll is the next thing it does."""
    account, session = make_account(
        monkeypatch,
        {
            "/users/token": FakeResponse(TOKEN_OK),
            "setupviewv2": FakeResponse(setup_view()),
            # A setup with no meter, which is told once and never asked again:
            # what a poll costs is counted from here on, not from the start.
            "/consumptions": FakeResponse([]),
            **(answers or {}),
        },
    )
    assert asyncio.run(account.connect()) is True
    asyncio.run(account.refresh_consumptions())
    session.requests.clear()

    return account, session


class FakeHub:
    """A hub that records being told, without a coordinator underneath it."""

    def __init__(self):
        self.updates = 0
        self.errors = []

    async def async_account_updated(self):
        self.updates += 1

    def async_set_update_error(self, err):
        self.errors.append(err)


def coordinator_over(account, hubs):
    """An AccountCoordinator with nothing but what a poll reads."""
    coordinator = object.__new__(AccountCoordinator)
    coordinator._account = account
    coordinator._hubs = hubs
    coordinator._settle_unsubs = []
    coordinator.hass = None
    # No entry, so the poll publishes without looking for faults to report.
    coordinator._entry = None

    return coordinator


# --- one request, every device --------------------------------------------


def test_one_poll_refreshes_every_device(monkeypatch):
    """The whole point: N devices, one request.

    This used to be N requests -- a coordinator per device, each asking for its
    own capability list on its own 60-second timer -- for a payload that
    describes all of them at once.
    """
    account, session = connected(monkeypatch)
    hubs = {"a": FakeHub(), "b": FakeHub(), "c": FakeHub()}
    coordinator = coordinator_over(account, hubs)

    asyncio.run(coordinator._async_update_data())

    assert len(session.setup_views()) == 1
    assert session.capability_polls() == []
    assert [hub.updates for hub in hubs.values()] == [1, 1, 1]


def test_the_poll_costs_the_same_whatever_the_account_holds(monkeypatch):
    """Ticking more devices at setup no longer buys more traffic.

    Every device on the account is in the answer whether or not somebody added
    it, so the request count is a property of the account and not of the
    selection made in the config flow.
    """
    account, session = connected(monkeypatch)

    for hubs in ({"a": FakeHub()}, {chr(97 + i): FakeHub() for i in range(7)}):
        session.requests.clear()
        asyncio.run(coordinator_over(account, hubs)._async_update_data())

        assert len(session.requests) == 1


def test_a_poll_brings_new_values_to_every_device(monkeypatch):
    """The values the entities read, not just the notification, come along."""
    account, session = connected(monkeypatch)
    session._answers["setupviewv2"] = FakeResponse(setup_view(value="21"))

    asyncio.run(coordinator_over(account, {"a": FakeHub()})._async_update_data())

    assert [dev["capabilities"][0]["value"] for dev in account.devices] == [
        "21",
        "21",
        "21",
    ]


def test_a_failed_poll_takes_every_device_with_it(monkeypatch):
    """The failure belongs to the account, so it has to reach every entity.

    Each hub is still the coordinator its own entities listen to, and none of
    them listens to the account -- so the account's failure is announced
    through all of them or through none.
    """
    account, session = connected(monkeypatch)
    session._answers["setupviewv2"] = FakeResponse([], status=200)
    hubs = {"a": FakeHub(), "b": FakeHub()}

    with pytest.raises(UpdateFailed):
        asyncio.run(coordinator_over(account, hubs)._async_update_data())

    assert [len(hub.errors) for hub in hubs.values()] == [1, 1]


def test_a_timed_out_poll_says_what_timed_out(monkeypatch):
    """This logged "...setup view: , forcing reconnect" for three hours."""
    account, session = connected(monkeypatch)
    session._answers["setupviewv2"] = FakeTimeout()

    with pytest.raises(UpdateFailed) as raised:
        asyncio.run(coordinator_over(account, {"a": FakeHub()})._async_update_data())

    assert "TimeoutError" in str(raised.value)
    assert ": ," not in str(raised.value)


def test_a_message_that_is_there_is_the_one_that_is_printed(monkeypatch):
    """`why` is a fallback, not a replacement."""
    assert account_module.why(TimeoutError("took too long")) == "took too long"
    assert account_module.why(TimeoutError()) == "TimeoutError"


def test_a_poll_that_finds_the_password_refused_raises_for_reauth(monkeypatch):
    """The reauth path followed the beat when the beat moved.

    ConfigEntryAuthFailed has to come out of whatever polls, or a password
    changed while Home Assistant is running is retried forever instead of being
    asked for once.
    """
    account, session = connected(monkeypatch)
    account.online = False
    session._answers["/users/token"] = FakeResponse(REFUSED)

    with pytest.raises(ConfigEntryAuthFailed):
        asyncio.run(coordinator_over(account, {"a": FakeHub()})._async_update_data())


def test_a_reconnect_publishes_without_asking_twice(monkeypatch):
    """connect() reads the setup view itself, so the poll must not read it again."""
    account, session = connected(monkeypatch)
    account.online = False
    hubs = {"a": FakeHub()}

    asyncio.run(coordinator_over(account, hubs)._async_update_data())

    assert len(session.setup_views()) == 1
    assert hubs["a"].updates == 1


# --- the poll stamps its own date ------------------------------------------


def test_a_successful_poll_stamps_when_the_data_arrived(monkeypatch):
    """`last_poll` is what the per-device Last Poll sensor reads.

    Stamped by the setup-view read itself, so connect() -- which reads it
    too -- already leaves a date before the first scheduled poll.
    """
    account, _ = connected(monkeypatch)
    stamped_at_connect = account.last_poll
    assert stamped_at_connect is not None
    assert stamped_at_connect.tzinfo is not None

    asyncio.run(coordinator_over(account, {"a": FakeHub()})._async_update_data())

    assert account.last_poll >= stamped_at_connect


def test_a_rate_limited_poll_keeps_the_old_stamp(monkeypatch):
    """A skipped poll fetched nothing, so the values are as old as the last one.

    This is the reading the stamp exists for : during a backoff the entities
    keep showing the last known values, and the stamp is what says how old
    those are.
    """
    account, session = connected(monkeypatch)
    stamped = account.last_poll
    session._answers["setupviewv2"] = FakeResponse(None, status=429)

    asyncio.run(coordinator_over(account, {"a": FakeHub()})._async_update_data())

    assert account.last_poll == stamped


def test_a_failed_poll_keeps_the_old_stamp(monkeypatch):
    """A failure is not a fetch, so it must not read as one."""
    account, session = connected(monkeypatch)
    stamped = account.last_poll
    session._answers["setupviewv2"] = FakeResponse([], status=200)

    with pytest.raises(UpdateFailed):
        asyncio.run(coordinator_over(account, {"a": FakeHub()})._async_update_data())

    assert account.last_poll == stamped


# --- what a 429 must not cost ---------------------------------------------


def test_a_rate_limited_poll_does_not_spend_a_login(monkeypatch):
    """The regression the whole change rests on.

    A 429 used to land in the generic non-200 branch, which sets
    `online = False`; the next poll then re-authenticated, so being told to
    make fewer requests produced two more of them -- including the failed-login
    kind that can get an account locked out.
    """
    account, session = connected(monkeypatch)
    session._answers["setupviewv2"] = FakeResponse(None, status=429)

    asyncio.run(coordinator_over(account, {"a": FakeHub()})._async_update_data())

    assert session.logins() == []
    assert account.online is True


def test_a_rate_limited_poll_leaves_the_devices_alone(monkeypatch):
    """Being asked to slow down is not the same as having failed.

    Marking every entity unavailable because the account is a few seconds ahead
    of its budget would be a worse lie than showing a value one poll old.
    """
    account, session = connected(monkeypatch)
    session._answers["setupviewv2"] = FakeResponse(None, status=429)
    hubs = {"a": FakeHub()}

    asyncio.run(coordinator_over(account, hubs)._async_update_data())

    assert hubs["a"].errors == []


def test_the_backoff_lasts_as_long_as_the_server_asked(monkeypatch):
    """Retry-After is honoured, and honoured by not sending anything."""
    account, session = connected(monkeypatch)
    session._answers["setupviewv2"] = FakeResponse(
        None, status=429, headers={"Retry-After": "120"}
    )

    asyncio.run(coordinator_over(account, {"a": FakeHub()})._async_update_data())
    assert 115 < account.backoff_remaining <= 120

    session.requests.clear()
    asyncio.run(coordinator_over(account, {"a": FakeHub()})._async_update_data())
    assert session.requests == []


def test_a_429_that_says_nothing_still_backs_off(monkeypatch):
    """No Retry-After is the common case, and the least informative one.

    The default is deliberately long: waiting too long costs stale values,
    waiting too little costs the throttle.
    """
    account, session = connected(monkeypatch)
    session._answers["setupviewv2"] = FakeResponse(None, status=429)

    asyncio.run(coordinator_over(account, {"a": FakeHub()})._async_update_data())

    assert RATE_LIMIT_BACKOFF - 5 < account.backoff_remaining <= RATE_LIMIT_BACKOFF


def test_an_unparsable_retry_after_does_not_break_the_poll(monkeypatch):
    """An HTTP-date, or anything else, falls back rather than throwing."""
    account, session = connected(monkeypatch)
    session._answers["setupviewv2"] = FakeResponse(
        None, status=429, headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"}
    )

    asyncio.run(coordinator_over(account, {"a": FakeHub()})._async_update_data())

    assert RATE_LIMIT_BACKOFF - 5 < account.backoff_remaining <= RATE_LIMIT_BACKOFF


def test_a_targeted_refresh_is_throttled_too(monkeypatch):
    """The per-device route shares the account's budget, so it shares its backoff."""
    account, session = connected(monkeypatch)
    session._answers["/magellan/capabilities/"] = FakeResponse(None, status=429)

    with pytest.raises(CozytouchRateLimited):
        asyncio.run(account.fetch_capabilities(1))

    session.requests.clear()
    with pytest.raises(CozytouchRateLimited):
        asyncio.run(account.fetch_capabilities(1))

    assert session.requests == []
    assert account.online is True


def test_a_write_is_still_attempted_while_throttled(monkeypatch):
    """Somebody pressed a button; a throttled *reader* must not swallow it.

    The polls back off because they can afford to. A write cannot be deferred
    without the press appearing to do nothing, so it is sent and the server is
    left to refuse it.
    """
    account, session = connected(monkeypatch)
    session._answers["setupviewv2"] = FakeResponse(None, status=429)
    asyncio.run(coordinator_over(account, {"a": FakeHub()})._async_update_data())

    session._answers["writecapability"] = FakeResponse(42, status=201)
    session._answers["/magellan/executions/"] = FakeResponse({"state": 3})
    session.requests.clear()

    assert asyncio.run(account.write_capability(1, 100, "21")) is True
    assert any("writecapability" in url for url in session.requests)


# --- the consumption endpoint ---------------------------------------------

METERED = [{"type": 1, "unit": 1, "currency": 101, "consumptionPeriods": []}]


def before_consumptions(monkeypatch, answer, declared=None):
    """A connected account the consumption endpoint has not answered yet.

    `declared` is what its first device reports in 164, if it reports it.
    """
    view = setup_view()
    if declared is not None:
        view[0]["devices"][0]["capabilities"].append(
            {"capabilityId": 164, "value": declared}
        )
    account, session = make_account(
        monkeypatch,
        {
            "/users/token": FakeResponse(TOKEN_OK),
            "setupviewv2": FakeResponse(view),
            "/consumptions": answer,
        },
    )
    assert asyncio.run(account.connect()) is True
    session.requests.clear()

    return account, session


def consumption_reads(session):
    return [url for url in session.requests if "/consumptions" in url]


def test_the_consumptions_are_read_with_the_first_poll(monkeypatch):
    """The sensors are built from that answer, so it has to be in before the
    platforms load -- which is what setup's first refresh is.
    """
    account, session = before_consumptions(monkeypatch, FakeResponse(METERED))

    asyncio.run(coordinator_over(account, {"a": FakeHub()})._async_update_data())

    assert consumption_reads(session) == [
        "https://apis.groupe-atlantic.com/magellan/setups/1/consumptions"
        "?periodicity=daily"
    ]
    assert account.consumptions == METERED


def test_the_consumptions_are_read_once_a_quarter_of_an_hour(monkeypatch):
    """Not once a poll : a day aggregated in the cloud does not move at the
    setup view's pace, and one request every 60 seconds would double what an
    account costs for nothing.
    """
    account, session = before_consumptions(monkeypatch, FakeResponse(METERED))
    coordinator = coordinator_over(account, {"a": FakeHub()})

    for _ in range(3):
        asyncio.run(coordinator._async_update_data())
    assert len(consumption_reads(session)) == 1

    account._consumptions_due = 0
    asyncio.run(coordinator._async_update_data())
    assert len(consumption_reads(session)) == 2


@pytest.mark.parametrize(
    "answer", [FakeResponse([]), FakeResponse(None, status=404)], ids=["empty", "404"]
)
def test_a_setup_without_a_meter_is_asked_once(monkeypatch, answer):
    """No sensor was built for it, so asking again only spends a request."""
    account, session = before_consumptions(monkeypatch, answer)

    asyncio.run(account.refresh_consumptions())
    account._consumptions_due = 0
    asyncio.run(account.refresh_consumptions())

    assert len(consumption_reads(session)) == 1


@pytest.mark.parametrize(
    "declared", ["0", "1024"], ids=["nothing", "production-only"]
)
def test_a_setup_that_declares_no_consumption_is_never_asked(monkeypatch, declared):
    """The Navizone's 164 reads 0, and its app shows no consumption. 1024 is
    `dhw_production`, heat made rather than a meter read, so it declares
    nothing either.
    """
    account, session = before_consumptions(
        monkeypatch, FakeResponse(METERED), declared=declared
    )

    for _ in range(2):
        account._consumptions_due = 0
        asyncio.run(coordinator_over(account, {"a": FakeHub()})._async_update_data())

    assert consumption_reads(session) == []
    assert account.consumption_declared() is False


def test_what_counts_as_a_meter_is_read_off_164s_own_row():
    """The seven consumption members, and not the three that are heat made.

    Pinned as a number so a bit added to the row shows up here, where
    somebody has to say whether it is a meter.
    """
    assert account_module.CONSUMPTION_BITS == 1 | 2 | 4 | 8 | 16 | 32 | 64


def test_a_setup_that_declares_a_consumption_is_asked(monkeypatch):
    """1040 is what the fork's Duralis reports : elec_dhw and dhw_production."""
    account, session = before_consumptions(
        monkeypatch, FakeResponse(METERED), declared="1040"
    )

    asyncio.run(account.refresh_consumptions())

    assert len(consumption_reads(session)) == 1
    assert account.consumption_declared() is True


def test_a_setup_that_says_nothing_in_164_is_left_to_the_endpoint(monkeypatch):
    account, session = before_consumptions(monkeypatch, FakeResponse(METERED))

    asyncio.run(account.refresh_consumptions())

    assert account.consumption_declared() is None
    assert len(consumption_reads(session)) == 1


def test_a_metered_setup_is_still_asked_after_an_empty_answer(monkeypatch):
    """A setup that reported once has sensors waiting on it ; an empty day is
    an answer for them, not a reason to stop.
    """
    account, session = before_consumptions(monkeypatch, FakeResponse(METERED))
    asyncio.run(account.refresh_consumptions())

    session._answers["/consumptions"] = FakeResponse([])
    for _ in range(2):
        account._consumptions_due = 0
        asyncio.run(account.refresh_consumptions())

    assert len(consumption_reads(session)) == 3
    assert account.consumptions == []


def test_a_consumption_failure_costs_neither_the_poll_nor_the_session(monkeypatch):
    """A meter reading is not worth a reconnect, nor an unavailable device."""
    account, session = before_consumptions(monkeypatch, FakeTimeout())
    hubs = {"a": FakeHub()}

    asyncio.run(coordinator_over(account, hubs)._async_update_data())

    assert account.online is True
    assert hubs["a"].updates == 1
    assert hubs["a"].errors == []
    assert session.logins() == []


def test_a_consumption_429_backs_the_whole_account_off(monkeypatch):
    """Same budget, same backoff, and still no reconnect."""
    account, _ = before_consumptions(
        monkeypatch, FakeResponse(None, status=429, headers={"Retry-After": "120"})
    )

    asyncio.run(account.refresh_consumptions())

    assert 115 < account.backoff_remaining <= 120
    assert account.online is True


# --- the interval ---------------------------------------------------------


def entry(options=None, data=None):
    return SimpleNamespace(options=options or {}, data=data or {})


def test_the_default_is_the_one_the_account_gets():
    assert poll_interval(entry(), None).total_seconds() == DEFAULT_POLL_INTERVAL


def test_the_option_wins_over_the_default():
    assert poll_interval(entry({"poll_interval": 45}), None).total_seconds() == 45


def test_an_interval_below_the_floor_is_raised_to_it():
    """Below the floor the requests stop buying anything.

    Atlantic's cloud learns from the hardware on its own schedule, and no
    amount of asking makes a radiator report sooner.
    """
    assert (
        poll_interval(entry({"poll_interval": 1}), None).total_seconds()
        == MIN_POLL_INTERVAL
    )


def test_an_interval_above_the_ceiling_is_lowered_to_it():
    assert (
        poll_interval(entry({"poll_interval": 99999}), None).total_seconds()
        == MAX_POLL_INTERVAL
    )


def test_a_junk_interval_falls_back_rather_than_throwing():
    """The number selector returns a float, an edited .storage returns anything.

    Neither may take the account down at setup.
    """
    assert poll_interval(entry({"poll_interval": 30.0}), None).total_seconds() == 30
    assert (
        poll_interval(entry({"poll_interval": "soon"}), None).total_seconds()
        == DEFAULT_POLL_INTERVAL
    )


def test_the_declared_rate_limit_is_a_ceiling():
    """Read as requests per minute, which is the strictest reading left.

    A 60-second-per-device poll has worked for years, so anything stricter than
    per-minute is already disproved, and a ceiling wants the strictest of what
    remains.

    At the 30 the one captured account declares, it permits everything down to
    the floor and never bites. At 1, it does.
    """
    assert poll_interval(entry({"poll_interval": 15}), 30).total_seconds() == 15
    assert poll_interval(entry({"poll_interval": 15}), 1).total_seconds() == 61


def test_a_rate_limit_that_says_nothing_useful_is_ignored():
    assert poll_interval(entry({"poll_interval": 20}), None).total_seconds() == 20
    assert poll_interval(entry({"poll_interval": 20}), 0).total_seconds() == 20


def test_the_account_reads_its_own_declared_limit(monkeypatch):
    account, _ = connected(monkeypatch)

    assert account.rate_limit == 30


def test_a_setup_view_without_a_rate_limit_declares_nothing(monkeypatch):
    account, _ = make_account(
        monkeypatch,
        {
            "/users/token": FakeResponse(TOKEN_OK),
            "setupviewv2": FakeResponse([{"id": 1, "devices": [], "zones": []}]),
        },
    )
    asyncio.run(account.connect())

    assert account.rate_limit is None


# --- the beat is booked -----------------------------------------------------


def test_a_built_coordinator_has_its_next_poll_booked(monkeypatch):
    """Built, the coordinator already holds a tick with the event loop.

    Home Assistant books a coordinator's next refresh only while at least one
    listener is subscribed (`async_add_listener`, and again at the end of every
    `_async_refresh`) -- and every entity of this integration listens to a hub,
    none to the account. So the coordinator subscribes to itself. Before it
    did, the one refresh setup runs was the last poll the account ever made :
    every value froze at whatever time Home Assistant last started, whatever
    the configured interval said, and only the `last_poll` sensor was there to
    show it.

    The rest of this file drives `_async_update_data` by hand, which is why
    none of it could have caught this. `_unsub_refresh` is Home Assistant's
    own handle on the booked tick ; None means no poll is ever coming.
    """
    account, _ = connected(monkeypatch)

    async def build():
        hass = SimpleNamespace(loop=asyncio.get_running_loop())
        config_entry = SimpleNamespace(
            options={},
            data={},
            entry_id="an-entry",
            pref_disable_polling=False,
            async_on_unload=lambda cb: None,
        )
        return AccountCoordinator(hass, account, config_entry, {"a": FakeHub()})

    coordinator = asyncio.run(build())

    assert coordinator._unsub_refresh is not None


# --- what the hub kept ----------------------------------------------------


def hub_over(account, deviceId=1):
    """A hub with nothing but what the update paths read."""
    hub = object.__new__(Hub)
    hub._account = account
    hub._deviceId = deviceId
    hub._entry = None
    hub._timestamp_away_mode_last_change = None
    hub._timestamps_away_mode_capability_id = None
    hub._timestamp_away_mode_start = None
    hub._timestamp_away_mode_end = None

    return hub


def test_a_targeted_refresh_asks_for_one_device(monkeypatch):
    """The per-device route was demoted, not deleted.

    It is what confirms a write on the device that was written to, where
    re-reading the whole household to check one setpoint would be absurd.
    """
    account, session = connected(monkeypatch)
    session._answers["/magellan/capabilities/"] = FakeResponse(
        [{"capabilityId": 100, "value": "23"}]
    )

    asyncio.run(hub_over(account)._async_update_data())

    assert len(session.capability_polls()) == 1
    assert session.setup_views() == []
    assert account.devices[0]["capabilities"] == [{"capabilityId": 100, "value": "23"}]


def test_a_throttled_targeted_refresh_keeps_the_device_available(monkeypatch):
    """A backoff is not an outage, on this path either."""
    account, session = connected(monkeypatch)
    session._answers["/magellan/capabilities/"] = FakeResponse(None, status=429)

    asyncio.run(hub_over(account)._async_update_data())

    assert account.online is True


def test_the_staged_away_window_still_goes_out(monkeypatch):
    """It used to hang off the hub's own 60-second poll, which is gone.

    Editing the start or the end of the window stages it and stamps it; the
    send happens once the stamp is more than 20 seconds old, so both ends can
    be set first. With the hub off the clock, the account's tick is what has to
    carry it -- otherwise a staged window would sit there for good.
    """
    account, _ = connected(monkeypatch)
    hub = hub_over(account)
    sent = []

    async def record(*args):
        sent.append(args)

    hub.set_away_mode_timestamps = record
    hub.async_set_updated_data = lambda data: None
    hub._timestamps_away_mode_capability_id = 40
    hub._timestamp_away_mode_start = 1000
    hub._timestamp_away_mode_end = 2000
    hub._timestamp_away_mode_last_change = 0  # 1970, so comfortably over 20s

    asyncio.run(hub.async_account_updated())

    assert sent == [(None, None, 40, 1000, 2000)]


def test_a_window_still_being_edited_is_not_sent_yet(monkeypatch):
    """The 20-second delay is the feature: it lets somebody set both ends."""
    import time

    account, _ = connected(monkeypatch)
    hub = hub_over(account)
    sent = []

    async def record(*args):
        sent.append(args)

    hub.set_away_mode_timestamps = record
    hub.async_set_updated_data = lambda data: None
    hub._timestamps_away_mode_capability_id = 40
    hub._timestamp_away_mode_start = 1000
    hub._timestamp_away_mode_end = 2000
    hub._timestamp_away_mode_last_change = time.time()

    asyncio.run(hub.async_account_updated())

    assert sent == []


# --- a write against a setup view that has not caught up -------------------


def write_and_poll(monkeypatch, account, session, *, value="1", polls=1):
    """Write one capability, then poll a setup view that still says "18"."""
    session._answers["writecapability"] = FakeResponse(42, status=201)
    session._answers["/magellan/executions/"] = FakeResponse({"state": 3})
    assert asyncio.run(account.write_capability(1, 100, value)) is True

    for _ in range(polls):
        asyncio.run(coordinator_over(account, {"a": FakeHub()})._async_update_data())

    return account.devices[0]["capabilities"][0]["value"]


def test_a_poll_right_after_a_write_does_not_undo_it(monkeypatch):
    """The flicker: toggle a switch, and the next poll answers with the old
    value because the cloud has not propagated the write yet. Holding the
    confirmed value is what stops the entity going back and forth.
    """
    account, session = connected(monkeypatch)
    assert write_and_poll(monkeypatch, account, session) == "1"


def test_the_setup_view_takes_over_once_it_agrees(monkeypatch):
    """The hold is not a local override: the API stays the source of truth."""
    account, session = connected(monkeypatch)
    write_and_poll(monkeypatch, account, session)

    session._answers["setupviewv2"] = FakeResponse(setup_view(value="1"))
    asyncio.run(coordinator_over(account, {"a": FakeHub()})._async_update_data())
    session._answers["setupviewv2"] = FakeResponse(setup_view(value="25"))
    asyncio.run(coordinator_over(account, {"a": FakeHub()})._async_update_data())

    assert account.devices[0]["capabilities"][0]["value"] == "25"


def test_the_refresh_a_write_asks_for_does_not_undo_it(monkeypatch):
    """Issue #121 : the targeted poll is the one most likely to answer stale.

    It runs seconds after the write, through `store_capabilities` rather than
    the setup view -- the path the hold used to skip, which made a write look
    refused when it had been accepted.
    """
    account, session = connected(monkeypatch)
    session._answers["writecapability"] = FakeResponse(42, status=201)
    session._answers["/magellan/executions/"] = FakeResponse({"state": 3})
    assert asyncio.run(account.write_capability(1, 100, "1")) is True

    account.store_capabilities(1, [{"capabilityId": 100, "value": "18"}])

    assert account.devices[0]["capabilities"][0]["value"] == "1"


def test_a_write_nothing_ever_reports_stops_being_held(monkeypatch):
    """A value the cloud accepted and then ignored must not be held forever."""
    account, session = connected(monkeypatch)
    monkeypatch.setattr(account_module, "PENDING_WRITE_GRACE", -1.0)

    assert write_and_poll(monkeypatch, account, session) == "18"


# --- what a write leaves behind --------------------------------------------


def scheduled(monkeypatch):
    """Record what `async_call_later` was asked for, and hand back cancels."""
    calls: list[tuple[float, object]] = []
    cancelled: list[int] = []

    def fake_call_later(hass, delay, action):
        index = len(calls)
        calls.append((delay, action))
        return lambda: cancelled.append(index)

    monkeypatch.setattr(hub_module, "async_call_later", fake_call_later)

    return calls, cancelled


def test_a_write_reads_the_account_at_once_and_again_once_it_settles(monkeypatch):
    """A capability can be the whole home's, and only one device wrote it.

    The device written to refreshes itself through `fetch_capabilities`. Its
    siblings would otherwise wait for the beat, which is a minute by default --
    the vendor app hides this by polling every device every five seconds while
    it is open.

    The first read is immediate because it can be : both planes carry the value
    the moment the execution completes, measured on three rooms on 2026-09-22.
    The booked one is for what the device derives afterwards. See
    docs/decisions.md.
    """
    account, _ = connected(monkeypatch)
    calls, _ = scheduled(monkeypatch)
    coordinator = coordinator_over(account, {})
    refreshed = []
    coordinator.async_request_refresh = lambda: _noop(refreshed)

    asyncio.run(coordinator.async_after_write())

    assert refreshed == [True]
    assert [delay for delay, _ in calls] == [hub_module.WRITE_SETTLE_DELAY]


async def _noop(recorded):
    """Stand in for the coordinator's own debounced refresh."""
    recorded.append(True)


def test_a_second_write_replaces_the_settling_read_rather_than_stacking_it(
    monkeypatch,
):
    """Ten entities written in a row must not book ten settling reads.

    The immediate half needs no guard of its own : it goes through Home
    Assistant's own debouncer, which is what collapses a burst of writes.
    """
    account, _ = connected(monkeypatch)
    calls, cancelled = scheduled(monkeypatch)

    coordinator = coordinator_over(account, {})
    refreshed = []
    coordinator.async_request_refresh = lambda: _noop(refreshed)

    asyncio.run(coordinator.async_after_write())
    asyncio.run(coordinator.async_after_write())

    assert cancelled == [0]
    assert len(calls) == 2


def test_the_targeted_refresh_asks_for_the_account_read(monkeypatch):
    """The seam : the write path is what books it, and nothing else does."""
    account, session = connected(monkeypatch)
    session._answers["/magellan/capabilities/"] = FakeResponse(
        [{"capabilityId": 100, "value": "23"}]
    )

    asked: list[bool] = []
    hub = hub_over(account)
    hub._entry = SimpleNamespace(
        runtime_data=SimpleNamespace(
            coordinator=SimpleNamespace(async_after_write=lambda: _noop(asked))
        )
    )

    asyncio.run(hub._async_update_data())

    assert asked == [True]
