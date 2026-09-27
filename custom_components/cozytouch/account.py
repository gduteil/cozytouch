"""The Atlantic Cozytouch account a config entry is built on.

One account, one login, one setup view : `setupviewv2` describes the whole
account and not the device that fetched it. The per-device half stays on `Hub`.
See docs/decisions.md.
"""

from __future__ import annotations

import asyncio
import copy
from datetime import UTC, datetime
import json
import logging

from aiohttp import ClientError, ClientTimeout, ContentTypeError, FormData

from homeassistant import exceptions
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .capability_table import CAPABILITIES
from .const import COZYTOUCH_ATLANTIC_API, COZYTOUCH_CLIENT_ID
from .model import CozytouchDeviceType, get_device_model_infos

_LOGGER = logging.getLogger(__name__)

# Timeout for all HTTP requests. Without this, a hung Atlantic API server
# will stall a poll forever, blocking every subsequent one.
REQUEST_TIMEOUT = ClientTimeout(total=30)

# How long a confirmed write outranks the setup view, in seconds. The lag
# between the two is not documented anywhere; see docs/decisions.md.
PENDING_WRITE_GRACE = 60.0

# How long to stop asking after a 429 that does not say. A guess, deliberately
# long -- see docs/decisions.md.
RATE_LIMIT_BACKOFF = 300.0

# What a throttling proxy puts in front of its answer, logged rather than
# parsed. See docs/decisions.md.
RATE_LIMIT_HEADERS = (
    "Retry-After",
    "X-RateLimit-Limit",
    "X-RateLimit-Remaining",
    "X-RateLimit-Reset",
)

# What the API declares about a device on top of the fields that drive
# behaviour. Carried to the diagnostics dump, read by nothing. See
# docs/decisions.md.
API_DECLARED_FIELDS = (
    "customName",
    "longName",
    "modelFamily",
    "productRange",
    "masterDeviceId",
    "isAvailable",
)

# How often the consumption endpoint is read, in seconds. Its days are
# aggregated in the cloud and move far slower than the setup view. See
# docs/decisions.md.
CONSUMPTION_INTERVAL = 900

# HOME_EnergyConsumptionCapabilities, whose bits its table row names. Every
# member but the `_production` ones is a meter ; those are heat made. Derived
# from the row rather than written out, so the two cannot drift apart. See
# docs/decisions.md.
CONSUMPTION_CAPABILITY = 164
CONSUMPTION_BITS = sum(
    bit
    for bit, name in CAPABILITIES[CONSUMPTION_CAPABILITY].bits or ()
    if not name.endswith("_production")
)

# Keys of the setup view worth keeping. The rest of the payload is per-device.
SETUP_FIELDS = (
    "absence",
    "address",
    "area",
    "currency",
    "id",
    "mainDHWEnergy",
    "mainHeatingEnergy",
    "name",
    "numberOfPersons",
    "numberOfRooms",
    # Units unknown ; carried to the dump rather than acted on.
    "rateLimit",
    "setupBuildingDate",
    "type",
)

# The subset the away-mode PUT has to send back. See docs/decisions.md.
SETUP_WRITABLE_FIELDS = (
    "address",
    "area",
    "currency",
    "mainHeatingEnergy",
    "mainDHWEnergy",
    "name",
    "numberOfPersons",
    "numberOfRooms",
    "setupBuildingDate",
    "type",
)



def why(err: BaseException) -> str:
    """What to print for an exception that may carry no message.

    `asyncio.TimeoutError` stringifies to "". See docs/decisions.md.
    """
    return str(err) or type(err).__name__

class CozytouchAccount:
    """One Atlantic account, and the only thing that talks to its API."""

    def __init__(self, hass: HomeAssistant, username: str, password: str) -> None:
        """Init the account."""
        self._hass = hass
        # Home Assistant's own session, so a discarded account leaks nothing.
        self._session = async_get_clientsession(hass)
        self._username = username
        self._password = password

        self._access_token = ""
        self._token_expiry: float = 0  # Unix timestamp; 0 = unknown/expired
        # Turns several reconnects arriving at once into one login.
        self._connect_lock = asyncio.Lock()
        # Set by a 429, and honoured by every caller before it spends a
        # request. 0 = not throttled.
        self._backoff_until: float = 0

        self.online = False
        self.setup: dict = {}
        self.zones: list | dict = []
        self.devices: list = []
        # When the setup view last answered, which is the age of everything
        # above. Only a success moves it. See docs/decisions.md.
        self.last_poll: datetime | None = None

        self._dump_json = False
        # A write the cloud confirmed but the setup view does not report yet,
        # as (deviceId, capabilityId) -> (value, expiry). See
        # docs/decisions.md.
        self._pending_writes: dict[tuple[int, int], tuple[str, float]] = {}
        # The vendor's fault table per model id, read once and kept. An empty
        # list is an answer -- most models have no table. See
        # docs/decisions.md.
        self._fault_tables: dict[int, list] = {}
        # The vendor's capability catalogue, fetched only when a diagnostics
        # dump is taken. None until then, and an empty dict once a request has
        # failed, so one refusal is not retried per device. See
        # docs/decisions.md.
        self._capability_catalogue: dict[int, dict] | None = None

        # What the consumption endpoint last answered, as it answered it, and
        # the status it answered with ; None until it has. Read by the sensors
        # and carried whole to the dump. See docs/decisions.md.
        self.consumptions: list | None = None
        self.consumptions_status: int | None = None
        self._consumptions_due: float = 0
        # Set once the endpoint has said this setup has nothing to report, so
        # an account without a meter spends one request per start, not one
        # every quarter of an hour.
        self._consumptions_unsupported = False

    @property
    def account_id(self) -> str:
        """A stable id for this account, for logging and unique ids."""
        return "cozytouch." + self._username.lower()

    def set_dump_json(self, dump_json: bool) -> None:
        """Set option from the config flow to dump JSON from the API."""
        self._dump_json = dump_json

    def _headers(self) -> dict[str, str]:
        """The authenticated headers every call but the token request uses."""
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }

    @property
    def rate_limit(self) -> int | None:
        """What the account declares its own limit to be, if it said.

        Units unknown ; read as requests per minute and only as a ceiling. See
        docs/decisions.md.
        """
        rateLimit = self.setup.get("rateLimit")
        return rateLimit if isinstance(rateLimit, int) else None

    @property
    def backoff_remaining(self) -> float:
        """Seconds left before this account may ask Atlantic for anything."""
        return max(0.0, self._backoff_until - datetime.now(UTC).timestamp())

    def _note_rate_limited(self, response, what: str) -> float:
        """Stop asking for a while, and write down everything the 429 said.

        Deliberately does **not** touch `online`. See docs/decisions.md.
        """
        retry_after = RATE_LIMIT_BACKOFF
        header = response.headers.get("Retry-After")
        if header:
            try:
                # Seconds, per RFC 9110. See docs/decisions.md.
                retry_after = max(0.0, float(header.strip()))
            except ValueError:
                _LOGGER.debug("Unparsed Retry-After: %s", header)

        self._backoff_until = datetime.now(UTC).timestamp() + retry_after

        # At warning level on purpose. See docs/decisions.md.
        _LOGGER.warning(
            "Rate limited by Atlantic on %s ; backing off %.0fs. Headers: %s",
            what,
            retry_after,
            {
                name: response.headers[name]
                for name in RATE_LIMIT_HEADERS
                if name in response.headers
            },
        )

        return retry_after

    async def connect(self) -> bool:
        """Log in and read the setup view, unless somebody already did.

        Idempotent, and `InvalidAuth` propagates rather than folding into
        `online = False`. See docs/decisions.md.
        """
        if self.online:
            return True

        # Before the lock and before the login. See docs/decisions.md.
        if self.backoff_remaining:
            _LOGGER.debug(
                "Not reconnecting for another %.0fs, rate limited",
                self.backoff_remaining,
            )
            return False

        async with self._connect_lock:
            if self.online:
                return True

            try:
                await self._authenticate()
                await self._read_setup()
                self.online = True
            except CannotConnect:
                self.online = False
            except CozytouchRateLimited:
                # The backoff armed above is what stops the next caller.
                self.online = False
            except (TimeoutError, ClientError) as err:
                _LOGGER.warning("connect: network error: %s", why(err))
                self.online = False

        return self.online

    async def connect_or_auth_failed(self) -> bool:
        """connect(), with a refused password raised rather than returned.

        `ConfigEntryAuthFailed` is what opens the reauth dialog and stops the
        coordinator rescheduling. See docs/decisions.md.
        """
        try:
            return await self.connect()
        except InvalidAuth as err:
            raise ConfigEntryAuthFailed(
                "Atlantic Cozytouch rejected the stored credentials"
            ) from err

    async def _authenticate(self) -> None:
        """POST /users/token, and remember when it stops being good."""
        async with self._session.post(
            COZYTOUCH_ATLANTIC_API + "/users/token",
            data=FormData(
                {
                    "grant_type": "password",
                    "scope": "openid",
                    "username": "GA-PRIVATEPERSON/" + self._username,
                    "password": self._password,
                }
            ),
            headers={
                "Authorization": f"Basic {COZYTOUCH_CLIENT_ID}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=REQUEST_TIMEOUT,
        ) as response:
            token = await response.json()

            # The one answer that means the credentials are wrong ; anything
            # else malformed is a bad response. See docs/decisions.md.
            if token.get("error") == "invalid_grant":
                raise InvalidAuth

            if "token_type" not in token:
                raise CannotConnect

            if "access_token" not in token:
                raise CannotConnect

            self._access_token = token["access_token"]
            # Track token expiry; fall back to 1 hour if not provided
            expires_in = token.get("expires_in", 3600)
            self._token_expiry = datetime.now(UTC).timestamp() + expires_in - 60

    async def _read_setup(self) -> None:
        """GET setupviewv2, which is everything the integration knows."""
        async with self._session.get(
            COZYTOUCH_ATLANTIC_API + "/magellan/cozytouch/setupviewv2",
            headers=self._headers(),
            timeout=REQUEST_TIMEOUT,
        ) as response:
            # Not CannotConnect, whose answer is the reconnect a 429 must not
            # provoke. See docs/decisions.md.
            if response.status == 429:
                retry_after = self._note_rate_limited(response, "the setup view")
                raise CozytouchRateLimited(
                    "Rate limited by the setup view", retry_after
                )

            json_data = await response.json()

            # An empty list or an error dict would blow up on json_data[0]
            # below; treat it as a failed connection so setup is retried
            if not isinstance(json_data, list) or not json_data:
                _LOGGER.warning(
                    "connect: unexpected setup payload (%s)",
                    type(json_data).__name__,
                )
                raise CannotConnect

            for key in SETUP_FIELDS:
                if key in json_data[0]:
                    self.setup[key] = copy.deepcopy(json_data[0][key])

            # Update devices infos
            await asyncio.get_event_loop().run_in_executor(
                None, self.update_devices_from_json_data, json_data
            )

            self.last_poll = datetime.now(UTC)

    async def refresh_setup(self) -> None:
        """Re-read the setup view, which is the poll.

        One request refreshes the whole account. See docs/decisions.md.
        """
        if self.backoff_remaining:
            raise CozytouchRateLimited(
                "Still backing off from a 429", self.backoff_remaining
            )

        try:
            await self._read_setup()
        except CannotConnect as err:
            self.online = False
            raise CozytouchApiError("Unusable setup view, forcing reconnect") from err
        except (TimeoutError, ClientError) as err:
            self.online = False
            raise CozytouchApiError(
                f"Network error reading the setup view: {why(err)}, forcing reconnect"
            ) from err

    def check_token(self) -> None:
        """Drop the connection when the token is spent, so the next poll re-auths.

        Flipping `online` is how every failure path here asks for a reconnect.
        """
        if self.online and datetime.now(UTC).timestamp() >= self._token_expiry:
            _LOGGER.info("Token expired or about to expire, re-authenticating")
            self.online = False

    def update_devices_from_json_data(self, json_data) -> None:
        """Update the devices list."""
        if self._dump_json:
            with open(
                self._hass.config.config_dir + "/Cozytouch.json", "w", encoding="utf-8"
            ) as outfile:
                json_object = json.dumps(json_data, indent=4)
                outfile.write(json_object)

        # Refreshed on every setup view, not just the first : a zone renamed
        # in the app has to reach the entity names it feeds.
        if "zones" in json_data[0]:
            self.zones = copy.deepcopy(json_data[0]["zones"])

        # Start by removing old devices
        for local_device in self.devices[:]:
            bStillExists = False
            for remote_device in json_data[0]["devices"]:
                if remote_device["deviceId"] == local_device["deviceId"]:
                    bStillExists = True
                    break

            if bStillExists is False:
                self.devices.remove(local_device)

        # Create new devices
        deviceIndex = -1
        for remote_device in json_data[0]["devices"]:
            deviceIndex = -1
            for i, local_device in enumerate(self.devices):
                if remote_device["deviceId"] == local_device["deviceId"]:
                    deviceIndex = i
                    break

            if deviceIndex == -1:
                device = {
                    "deviceId": remote_device["deviceId"],
                    "name": remote_device["name"],
                    "gatewaySerialNumber": remote_device["gatewaySerialNumber"],
                    "modelId": remote_device["modelId"],
                    "productId": remote_device["productId"],
                    "zoneId": remote_device["zoneId"],
                    "capabilities": [],
                    "tags": [],
                }
                if "tags" in remote_device:
                    device["tags"] = copy.deepcopy(remote_device["tags"])

                self.devices.append(device)
                deviceIndex = len(self.devices) - 1

            # Refreshed rather than set once at creation : isAvailable moves.
            for field in API_DECLARED_FIELDS:
                self.devices[deviceIndex][field] = remote_device.get(field)

            # Every device, not just the one that asked. See
            # docs/decisions.md.
            if "capabilities" in remote_device:
                self.devices[deviceIndex]["capabilities"] = copy.deepcopy(
                    remote_device["capabilities"]
                )

        self._apply_pending_writes()

    def _apply_pending_writes(self) -> None:
        """Keep a confirmed write until the setup view catches up with it."""
        if not self._pending_writes:
            return

        now = datetime.now(UTC).timestamp()
        for device in self.devices:
            for capability in device["capabilities"]:
                key = (device["deviceId"], capability["capabilityId"])
                pending = self._pending_writes.get(key)
                if pending is None:
                    continue

                value, expiry = pending
                if capability["value"] == value or now >= expiry:
                    del self._pending_writes[key]
                else:
                    capability["value"] = value

        for key, (_, expiry) in list(self._pending_writes.items()):
            if now >= expiry:
                del self._pending_writes[key]

    async def _get_json_quietly(self, path: str, what: str) -> list | None:
        """GET a list from the API, or None on any failure, logged at debug."""
        try:
            async with self._session.get(
                COZYTOUCH_ATLANTIC_API + path,
                headers=self._headers(),
                timeout=REQUEST_TIMEOUT,
            ) as response:
                if response.status != 200:
                    _LOGGER.debug("No %s (%d)", what, response.status)
                    return None

                body = await response.json()
        except (TimeoutError, ClientError, ContentTypeError, ValueError) as err:
            _LOGGER.debug("The %s failed: %s", what, err)
            return None

        return body if isinstance(body, list) else None

    async def fetch_fault_table(self, modelId: int) -> list:
        """The vendor's fault table for one model, cached for the session.

        Nothing here is redistributed : the table is read from Atlantic, for
        the one model a device reporting a fault actually is. A failure is not
        worth an outage -- the codes still read -- so every one of them caches
        an empty table and moves on. See docs/decisions.md.
        """
        if modelId in self._fault_tables:
            return self._fault_tables[modelId]

        # Cached before the request, so a route that keeps failing is asked
        # once rather than once per poll.
        self._fault_tables[modelId] = []

        if self.backoff_remaining:
            del self._fault_tables[modelId]
            return []

        table = await self._get_json_quietly(
            f"/magellan/productmodels/models/{modelId}/detailederrors",
            f"fault table for model {modelId}",
        )
        if table is None:
            return []

        self._fault_tables[modelId] = table
        return table

    async def fetch_capability_catalogue(self) -> dict[int, dict]:
        """What Atlantic says every capability id means, cached for the session.

        405 rows with a name, a description, a type, a unit, bounds and the
        enum members, which is what turns an unnamed id in a diagnostics dump
        into a question somebody can answer. Asked for only when a dump is
        taken, never on the poll. A failure is not worth an outage -- the dump
        is still the dump -- so it caches empty and moves on. See
        docs/decisions.md.
        """
        if self._capability_catalogue is not None:
            return self._capability_catalogue

        self._capability_catalogue = {}

        if self.backoff_remaining:
            self._capability_catalogue = None
            return {}

        catalogue = await self._get_json_quietly(
            "/magellan/productmodels/capabilities", "capability catalogue"
        )
        if catalogue is None:
            return {}

        self._capability_catalogue = {
            row["id"]: row
            for row in catalogue
            if isinstance(row, dict) and isinstance(row.get("id"), int)
        }
        return self._capability_catalogue

    def consumption_declared(self) -> bool | None:
        """Whether a device says the setup tracks any consumption.

        None when no device reports 164, which leaves the endpoint to answer.
        See docs/decisions.md.
        """
        masks = []
        for device in self.devices:
            for capability in device["capabilities"]:
                if capability["capabilityId"] != CONSUMPTION_CAPABILITY:
                    continue
                try:
                    masks.append(int(str(capability["value"]).strip()))
                except (TypeError, ValueError):
                    continue

        if not masks:
            return None

        return any(mask & CONSUMPTION_BITS for mask in masks)

    async def refresh_consumptions(self) -> None:
        """Re-read what the setup consumed, when it is due.

        Never raises and never touches `online` : a meter reading is not worth
        a reconnect. A setup whose first answer is a refusal or an empty list
        is not asked again until the entry reloads, since no entity was built
        for it ; one whose devices declare no consumption in 164 is not asked
        at all. See docs/decisions.md.
        """
        setupId = self.setup.get("id")
        now = datetime.now(UTC).timestamp()
        if self.consumptions is None and self.consumption_declared() is False:
            self._consumptions_unsupported = True

        if (
            setupId is None
            or self._consumptions_unsupported
            or now < self._consumptions_due
            or self.backoff_remaining
        ):
            return

        # Before the request, so a route that keeps failing is asked once per
        # interval rather than once per poll.
        self._consumptions_due = now + CONSUMPTION_INTERVAL

        try:
            async with self._session.get(
                COZYTOUCH_ATLANTIC_API
                + f"/magellan/setups/{setupId}/consumptions?periodicity=daily",
                headers=self._headers(),
                timeout=REQUEST_TIMEOUT,
            ) as response:
                if response.status == 429:
                    self._note_rate_limited(response, "the consumptions")
                    return

                self.consumptions_status = response.status
                if 400 <= response.status < 500 and self.consumptions is None:
                    _LOGGER.debug(
                        "No consumptions for this setup (%d)", response.status
                    )
                    self._consumptions_unsupported = True
                    return

                if response.status != 200:
                    _LOGGER.debug("No consumptions (%d)", response.status)
                    return

                body = await response.json()
        except (TimeoutError, ClientError, ContentTypeError, ValueError) as err:
            _LOGGER.debug("Reading the consumptions failed: %s", why(err))
            return

        if not isinstance(body, list):
            return

        if not body and self.consumptions is None:
            self._consumptions_unsupported = True

        self.consumptions = body

    async def fetch_capabilities(self, deviceId: int) -> list:
        """GET the capability list of one device, to confirm a write.

        Raises rather than returning a sentinel, since an empty list is a
        legitimate answer. See docs/decisions.md.
        """
        if self.backoff_remaining:
            raise CozytouchRateLimited(
                "Still backing off from a 429", self.backoff_remaining
            )

        try:
            async with self._session.get(
                COZYTOUCH_ATLANTIC_API
                + "/magellan/capabilities/?deviceId="
                + str(deviceId),
                headers=self._headers(),
                timeout=REQUEST_TIMEOUT,
            ) as response:
                # 401 means the token was rejected; force re-auth next poll
                if response.status == 401:
                    self.online = False
                    raise CozytouchApiError(
                        "Token rejected (401), forcing re-authentication next poll"
                    )

                # Before the generic branch below, and without dropping the
                # session. See docs/decisions.md.
                if response.status == 429:
                    retry_after = self._note_rate_limited(response, "the capabilities")
                    raise CozytouchRateLimited(
                        "Rate limited by the capabilities endpoint", retry_after
                    )

                if response.status != 200:
                    self.online = False
                    raise CozytouchApiError(
                        f"Unexpected status {response.status} from"
                        " capabilities endpoint"
                    )

                try:
                    json_data = await response.json()
                except ContentTypeError as err:
                    self.online = False
                    raise CozytouchApiError(
                        "Non-JSON response from capabilities endpoint"
                    ) from err

                if not isinstance(json_data, list):
                    self.online = False
                    raise CozytouchApiError(
                        "Capabilities response is not a list (got"
                        f" {type(json_data).__name__}), forcing reconnect"
                    )

                return json_data

        except TimeoutError as err:
            self.online = False
            raise CozytouchApiError(
                f"Timeout fetching capabilities for device {deviceId},"
                " forcing reconnect"
            ) from err
        except ClientError as err:
            self.online = False
            raise CozytouchApiError(
                "Network error fetching capabilities for device"
                f" {deviceId}: {why(err)}, forcing reconnect"
            ) from err

    def store_capabilities(self, deviceId: int, capabilities: list) -> None:
        """Put a freshly polled capability list back on the device."""
        for dev in self.devices:
            if dev["deviceId"] == deviceId:
                dev["capabilities"] = copy.deepcopy(capabilities)
                break

        # This is the poll a write asks for, so it is the one most likely to
        # answer with the old value. See docs/decisions.md.
        self._apply_pending_writes()

    async def write_capability(
        self, deviceId: int, capabilityId: int, value: str
    ) -> bool:
        """Write one capability, and wait for the execution to complete.

        Attempted even while the account is backing off, unlike the polls. See
        docs/decisions.md.
        """
        try:
            async with self._session.post(
                COZYTOUCH_ATLANTIC_API + "/magellan/executions/writecapability",
                json={
                    "capabilityId": capabilityId,
                    "deviceId": deviceId,
                    "value": value,
                },
                headers=self._headers(),
                timeout=REQUEST_TIMEOUT,
            ) as response:
                if response.status == 429:
                    self._note_rate_limited(response, "a capability write")
                    return False

                if response.status != 201:
                    return False

                executionId = await response.json()
        except (TimeoutError, ClientError) as err:
            _LOGGER.warning(
                "Network error writing capability %d: %s", capabilityId, err
            )
            return False

        if not await self._await_execution(executionId):
            return False

        self._pending_writes[(deviceId, capabilityId)] = (
            value,
            datetime.now(UTC).timestamp() + PENDING_WRITE_GRACE,
        )
        return True

    async def _await_execution(self, executionId) -> bool:
        """Poll one execution until it reports completion, or give up."""
        nbRetry = 0
        while True:
            try:
                async with self._session.get(
                    COZYTOUCH_ATLANTIC_API + "/magellan/executions/" + str(executionId),
                    headers=self._headers(),
                    timeout=REQUEST_TIMEOUT,
                ) as response:
                    # The burstiest loop here, so the last place to keep
                    # hammering after a 429. See docs/decisions.md.
                    if response.status == 429:
                        self._note_rate_limited(response, "an execution poll")
                        return False

                    try:
                        execution_data = await response.json()
                    except ContentTypeError:
                        self.online = False
                        return False

                    execution_state = execution_data.get("state", False)
                    if execution_state == 1:
                        _LOGGER.info("Execution_state waiting execution")
                    elif execution_state == 2:
                        _LOGGER.info("Execution_state in progress")
                    elif execution_state == 3:
                        _LOGGER.info("Execution_state completed")
                        return True
                    else:
                        _LOGGER.info("Execution_state error")
                        return False
            except (TimeoutError, ClientError) as err:
                _LOGGER.warning("Network error polling execution: %s", why(err))
                return False

            nbRetry += 1
            if nbRetry > 5:
                return False

            await asyncio.sleep(1)

    async def set_absence(self, timestampStart, timestampEnd) -> bool:
        """PUT the absence window on the setup, which is the account's."""
        json_data = {
            key: copy.deepcopy(self.setup[key])
            for key in SETUP_WRITABLE_FIELDS
            if key in self.setup
        }

        json_data["absence"] = {}
        if timestampStart is not None and timestampEnd is not None:
            json_data["absence"]["startDate"] = timestampStart
            json_data["absence"]["endDate"] = timestampEnd

        try:
            async with self._session.put(
                COZYTOUCH_ATLANTIC_API + "/magellan/v2/setups/" + str(self.setup["id"]),
                json=json_data,
                headers=self._headers(),
                timeout=REQUEST_TIMEOUT,
            ) as response:
                if response.status in (200, 204):
                    return True

                if response.status == 429:
                    self._note_rate_limited(response, "the absence window")
                    return False

                _LOGGER.error(
                    "Set away mode : response %d (%s)",
                    response.status,
                    str(response.request_info),
                )
        except (TimeoutError, ClientError) as err:
            _LOGGER.warning("Network error writing the absence window: %s", why(err))

        return False

    def device_summaries(self) -> list[dict]:
        """The devices worth offering to somebody adding this integration.

        Zones are left out. See docs/decisions.md.
        """
        summaries = []
        for dev in self.devices:
            modelInfos = get_device_model_infos(self.devices, dev)
            if modelInfos.type is CozytouchDeviceType.ZONE:
                continue

            summaries.append(
                {
                    "deviceId": dev["deviceId"],
                    "name": dev["name"],
                    "model": modelInfos.name,
                }
            )

        return summaries

    def get_zone_name(self, zoneId: int | None) -> str | None:
        """What the account calls a zone, or None when it does not name it.

        None rather than the id as a string. See docs/decisions.md.
        """
        for zone in self.zones:
            if "id" in zone and zone["id"] == zoneId:
                return zone["name"]

        return None


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""


class InvalidAuth(exceptions.HomeAssistantError):
    """Error to indicate the account refused the username and password."""


class CozytouchApiError(exceptions.HomeAssistantError):
    """Error to indicate a call to the Cozytouch API did not answer usefully."""


class CozytouchRateLimited(CozytouchApiError):
    """Error to indicate Atlantic asked for fewer requests, not for none.

    Leaves `online` alone, unlike every other failure here. See
    docs/decisions.md.
    """

    def __init__(self, message: str, retry_after: float) -> None:
        """Init with how long the server, or the default, asks us to wait."""
        super().__init__(message)
        self.retry_after = retry_after
