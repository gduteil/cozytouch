"""Atlantic Cozytouch Hub."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.event import async_call_later
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)
from homeassistant.util import dt as dt_util

from . import faults
from .account import (
    API_DECLARED_FIELDS,
    CozytouchAccount,
    CozytouchApiError,
    CozytouchRateLimited,
)
from .capability import get_capability_infos
from .const import DOMAIN
from .infos import CapabilityCategory, CapabilityInfos, CapabilityType
from .model import get_device_model_infos, get_model_infos
from .repairs import async_check_faults

_LOGGER = logging.getLogger(__name__)

# How often the account asks Atlantic for the setup view, and the bounds the
# option is held between. See docs/decisions.md.
DEFAULT_POLL_INTERVAL = 60
MIN_POLL_INTERVAL = 15
MAX_POLL_INTERVAL = 600

POLL_INTERVAL_OPTION = "poll_interval"

# How long after a write the account is read a second time, in seconds. The
# first read is immediate : both planes carry the new value the moment the
# execution completes, measured. See docs/decisions.md.
WRITE_SETTLE_DELAY = 15


@dataclass
class CozytouchRuntimeData:
    """One account, and one hub per device, keyed by the device's subentry."""

    account: CozytouchAccount
    hubs: dict[str, Hub]
    coordinator: AccountCoordinator

# The firmware version, which the device registry wants as a string on the
# device rather than as an entity somewhere in the list.
SOFTWARE_VERSION_CAPABILITY_ID = 121

type CozytouchConfigEntry = ConfigEntry[CozytouchRuntimeData]


def poll_interval(entry: ConfigEntry, rate_limit: int | None) -> timedelta:
    """How often to poll, from the option and what the account will allow.

    The ceiling is `rateLimit` read as requests per minute. See
    docs/decisions.md.
    """
    seconds = entry.options.get(
        POLL_INTERVAL_OPTION,
        entry.data.get(POLL_INTERVAL_OPTION, DEFAULT_POLL_INTERVAL),
    )

    try:
        seconds = int(seconds)
    except (TypeError, ValueError):
        seconds = DEFAULT_POLL_INTERVAL

    seconds = max(MIN_POLL_INTERVAL, min(MAX_POLL_INTERVAL, seconds))

    if rate_limit and rate_limit > 0:
        # One request per interval is the whole steady-state cost, so the
        # budget is spent when the interval drops below 60 / rateLimit.
        allowed = 60 / rate_limit
        if seconds < allowed:
            _LOGGER.warning(
                "Poll interval of %ds exceeds the account's declared rateLimit"
                " of %s; using %ds",
                seconds,
                rate_limit,
                int(allowed) + 1,
            )
            seconds = int(allowed) + 1

    return timedelta(seconds=seconds)


class AccountCoordinator(DataUpdateCoordinator):
    """The one thing on a beat : re-read the setup view, tell every hub.

    The hubs stay coordinators with no schedule of their own, and are pushed to
    from here. See docs/decisions.md.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        account: CozytouchAccount,
        config_entry: ConfigEntry,
        hubs: dict[str, Hub],
    ) -> None:
        """Init the account coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            # Not the username : this name reaches every debug line written.
            config_entry=config_entry,
            name="Cozytouch_" + config_entry.entry_id,
            update_interval=poll_interval(config_entry, account.rate_limit),
        )
        self._account = account
        self._hubs = hubs
        self._entry = config_entry
        self._settle_unsubs: list[Callable[[], None]] = []
        config_entry.async_on_unload(self.async_cancel_settle)

        # Without a listener of its own, this coordinator never reschedules
        # and no poll follows setup's first one. See docs/decisions.md.
        self.async_add_listener(lambda: None)

    async def async_after_write(self) -> None:
        """Re-read the account after somebody wrote something.

        The device written to refreshes itself; this is what its siblings get,
        since a capability can be the whole home's. Immediately, because the
        cloud already holds the value, and once more later for what the device
        derives from it afterwards. See docs/decisions.md.
        """
        self.async_cancel_settle()
        self._settle_unsubs = [
            async_call_later(self.hass, WRITE_SETTLE_DELAY, self._settle_tick)
        ]
        await self.async_request_refresh()

    def async_cancel_settle(self) -> None:
        """Drop whatever a previous write scheduled."""
        for unsub in self._settle_unsubs:
            unsub()
        self._settle_unsubs = []

    async def _settle_tick(self, _now) -> None:
        """The settling read, for the values a write leads to rather than sets."""
        await self.async_refresh()

    async def _async_update_data(self) -> None:
        """Read the setup view once, and hand it to every device."""
        self._account.check_token()

        if not self._account.online:
            if not await self._account.connect_or_auth_failed():
                self._publish_error(UpdateFailed("Cannot connect to Atlantic"))
                raise UpdateFailed("Cannot connect to Atlantic Cozytouch API")

            # connect() reads the setup view itself, so this round is done.
            await self._account.refresh_consumptions()
            await self._publish()
            return

        try:
            await self._account.refresh_setup()
        except CozytouchRateLimited as err:
            # Not an UpdateFailed : see docs/decisions.md.
            _LOGGER.debug("Poll skipped, backing off : %s", err)
            return
        except CozytouchApiError as err:
            self._publish_error(UpdateFailed(str(err)))
            raise UpdateFailed(str(err)) from err

        # On its own, slower clock ; a no-op on most polls. See
        # docs/decisions.md.
        await self._account.refresh_consumptions()
        await self._publish()

    async def _publish(self) -> None:
        """Tell every hub its device has a fresh capability list."""
        for hub in self._hubs.values():
            await hub.async_account_updated()

        # Once the hubs have read the poll, not once per hub: the check looks
        # at the whole account, and only once it has one to look at.
        if getattr(self._entry, "runtime_data", None) is not None:
            async_check_faults(self.hass, self._entry)

    def _publish_error(self, err: Exception) -> None:
        """Mark every device unavailable, since the account they share failed."""
        for hub in self._hubs.values():
            hub.async_set_update_error(err)

def as_epoch(value) -> int | None:
    """A modificationDate as an int, or None when it says nothing.

    Missing, unparsable or at or below zero all read as None rather than as a
    date in 1970. See docs/decisions.md.
    """
    try:
        epoch = int(float(value))
    except (TypeError, ValueError):
        return None

    return epoch if epoch > 0 else None


def device_of(hub, deviceId: int | None = None) -> dict | None:
    """One device as the API describes it -- the hub's own, unless asked.

    None when the account does not hold it; what a missing device means is
    the caller's to decide.
    """
    deviceId = deviceId or hub._deviceId
    return next(
        (dev for dev in hub._account.devices if dev["deviceId"] == deviceId),
        None,
    )


class Hub(DataUpdateCoordinator):
    """One device of an Atlantic Cozytouch account.

    The session, the token, the setup view and the poll are the account's and
    live in `account.py`. What is left here is per device : which capability
    ids it reports, what its model makes of them, and the away-mode window
    staged before it is committed. A coordinator with `update_interval=None`,
    pushed to by `AccountCoordinator`. See docs/decisions.md.
    """

    manufacturer = "Atlantic Group"

    def __init__(
        self,
        hass: HomeAssistant,
        account: CozytouchAccount,
        deviceId: int | None = None,
        config_entry: ConfigEntry | None = None,
        subentry_id: str | None = None,
    ) -> None:
        """Init hub."""
        super().__init__(
            hass,
            _LOGGER,
            config_entry=config_entry,
            name="Cozytouch_" + str(deviceId),
            update_interval=None,
        )
        self._account = account
        self._hass = hass
        self._entry = config_entry
        self._subentry_id = subentry_id
        self._deviceId = deviceId
        self._create_unknown = False
        # What the vendor's table says about the faults this device is
        # reporting now, per capability id. Empty on a healthy device, which
        # is what spends no request. See docs/decisions.md.
        self._faults: dict[int, list[dict]] = {}

        # Staged rather than sent, so both ends can be set before either is
        # committed. See docs/decisions.md.
        self._timestamp_away_mode_last_change = None
        self._timestamp_away_mode_start = None
        self._timestamp_away_mode_end = None
        self._timestamps_away_mode_capability_id = None

    @property
    def account(self) -> CozytouchAccount:
        """The account this device hangs off."""
        return self._account

    @property
    def subentry_id(self) -> str | None:
        """The subentry this device was added as, and so the device's identity."""
        return self._subentry_id

    @property
    def online(self) -> bool:
        """Whether the account this device belongs to is connected."""
        return self._account.online

    def set_create_entities_for_unknown_entities(self, create_unknown: bool) -> None:
        """Set option from config flow to create entities for unknown capabilities."""
        self._create_unknown = create_unknown

    def get_create_entities_for_unknown_entities(self) -> bool:
        """Get option from config flow to create entities for unknown capabilities."""
        return self._create_unknown

    async def async_account_updated(self) -> None:
        """The account has a fresh setup view; publish it as this device's data.

        Nothing left to fetch : the values are already on `account.devices`.
        """
        await self._commit_staged_away_mode()
        await self._refresh_faults()
        self.async_set_updated_data(None)

    async def _refresh_faults(self) -> None:
        """Name the faults the device reports, in the vendor's own words.

        Reads the table only when a code is actually active, so a healthy
        account never asks for one. See docs/decisions.md.
        """
        active = {
            capabilityId: rows
            for capabilityId in faults.FAULT_CAPABILITIES
            if (
                rows := faults.active_rows(
                    self.get_capability_value(capabilityId, None)
                )
            )
        }

        if not active:
            self._faults = {}
            return

        modelId = self.get_model_id()
        table = (
            await self._account.fetch_fault_table(modelId)
            if modelId is not None
            else []
        )

        self._faults = {
            capabilityId: described
            for capabilityId, rows in active.items()
            if (
                described := [
                    fault
                    for row in rows
                    if (fault := faults.describe(table, row)) is not None
                ]
            )
        }

    def get_faults(self) -> dict[int, list[dict]]:
        """The named faults this device is reporting, per capability id."""
        return self._faults

    async def _async_update_data(self):
        """Fetch this one device, for a refresh that could not wait.

        Runs when `async_request_refresh()` asks, which is after a write. See
        docs/decisions.md.
        """
        _LOGGER.debug("_async_update_data %d", self._deviceId)

        # Proactively re-authenticate if the token is about to expire
        self._account.check_token()

        if not self._account.online:
            if not await self._account.connect_or_auth_failed():
                raise UpdateFailed("Cannot connect to Atlantic Cozytouch API")

            # A reconnect re-reads the setup view, so this round is done.
            await self._commit_staged_away_mode()
            return

        try:
            capabilities = await self._account.fetch_capabilities(self._deviceId)
        except CozytouchRateLimited:
            # Throttled, not broken : keep the values and stay available.
            return
        except CozytouchApiError as err:
            raise UpdateFailed(str(err)) from err

        self._account.store_capabilities(self._deviceId, capabilities)
        await self._commit_staged_away_mode()
        await self._refresh_faults()

        # This ran because of a write, and a write can be the home's. See
        # docs/decisions.md.
        if (runtime := getattr(self._entry, "runtime_data", None)) is not None:
            await runtime.coordinator.async_after_write()

    async def _commit_staged_away_mode(self) -> None:
        """Send the away window once both ends have stopped moving.

        Called from every path that can refresh this device, so the delay does
        not depend on which. See docs/decisions.md.
        """
        if (
            self._timestamp_away_mode_last_change is None
            or self._timestamps_away_mode_capability_id is None
            or self._timestamp_away_mode_start is None
            or self._timestamp_away_mode_end is None
        ):
            return

        now = datetime.now(tz=dt_util.DEFAULT_TIME_ZONE).timestamp()
        if now - self._timestamp_away_mode_last_change > 20:
            await self.set_away_mode_timestamps(
                None,
                None,
                self._timestamps_away_mode_capability_id,
                self._timestamp_away_mode_start,
                self._timestamp_away_mode_end,
            )

    def get_zone_name(self, zoneId: int | None = None) -> str:
        """Get zone infos."""
        return self._account.get_zone_name(zoneId)

    def get_model_infos(self, deviceId: int | None = None) -> str:
        """Get model infos."""
        dev = device_of(self, deviceId)
        if dev is None:
            return get_model_infos(-1)

        zoneId = dev["zoneId"]

        # Special case for sub-devices, use master zone Id
        for masterDev in self._account.devices:
            if "tags" in masterDev:
                for tag in masterDev["tags"]:
                    if (
                        "label" in tag
                        and tag["label"] == "iothubChildrenIds"
                        and "value" in tag
                        and tag["value"] == dev["name"]
                    ):
                        zoneId = masterDev["zoneId"]
                        break

        return get_device_model_infos(
            self._account.devices, dev, self.get_zone_name(zoneId)
        )

    def get_model_id(self, deviceId: int | None = None) -> int | None:
        """The model id the API reports, which is what the mapping is keyed on."""
        dev = device_of(self, deviceId)
        return dev["modelId"] if dev else None

    def get_serial_number(self, deviceId: int | None = None) -> str:
        """Get serial number."""
        dev = device_of(self, deviceId)
        return dev["gatewaySerialNumber"] if dev else "Unknown"

    def get_software_version(self) -> str | None:
        """The firmware version the device reports about itself, if it does.

        None for a device that does not report 121, the gateways among them,
        which leaves the registry field empty rather than guessing.
        """
        return self.get_capability_value(SOFTWARE_VERSION_CAPABILITY_ID, None)

    def get_via_device(self, deviceId: int | None = None) -> tuple[str, str] | None:
        """Identifiers of the gateway this device hangs off, when HA has it.

        None for a gateway, and for a child whose gateway nobody added. See
        docs/decisions.md.
        """
        dev = device_of(self, deviceId)
        masterDeviceId = dev.get("masterDeviceId") if dev else None

        if not masterDeviceId:
            return None

        for subentry_id, subentry in self._entry.subentries.items():
            if subentry.data.get("deviceId") == masterDeviceId:
                return (DOMAIN, subentry_id)

        return None

    def get_capabilities_for_device(self, deviceId: int | None = None):
        """Get capabilities for a device."""
        dev = device_of(self, deviceId)
        if dev is None:
            return []

        modelInfos = get_device_model_infos(self._account.devices, dev)
        availableCapabilityIds = {cap["capabilityId"] for cap in dev["capabilities"]}

        capabilities = []
        for capability in dev["capabilities"]:
            capability_infos = get_capability_infos(
                modelInfos,
                capability["capabilityId"],
                capability["value"],
                availableCapabilityIds,
            )

            if capability_infos is None and self._create_unknown:
                capability_infos = CapabilityInfos(
                    capabilityId=capability["capabilityId"],
                    name="Capability_" + str(capability["capabilityId"]),
                    type=CapabilityType.STRING,
                    category=CapabilityCategory.DIAG,
                )

            if capability_infos is None or len(capability_infos) == 0:
                continue

            capability_infos.deviceId = dev["deviceId"]

            if "capabilityDuplicate" in capability_infos and any(
                cap["capabilityId"] == capability_infos.capabilityDuplicate
                for cap in capabilities
            ):
                continue

            capabilities.append(capability_infos)

        return capabilities

    def get_capability_names(
        self, deviceId: int | None = None
    ) -> tuple[dict[int, str], list[int], list[int]]:
        """Split what a device reports three ways: named, suppressed, unknown.

        Three and not two. `get_capability_infos` answers None for an id
        nothing in the mapping knows, and an empty `CapabilityInfos` for one it
        knows and deliberately does not turn into an entity here -- a flag the
        product does not have, a type the row is absent on, a mode id the
        device reports without steering on. Both are falsy, so reading them the
        same way filed a decision as a gap: this account's 171, 172 and 100507
        have rows and read as unnamed. See docs/decisions.md.

        Read by the diagnostics dump and by the notice that asks for one, so
        the rule lives here rather than in each.
        """
        dev = device_of(self, deviceId)
        if dev is None:
            return {}, [], []

        modelInfos = get_device_model_infos(self._account.devices, dev)
        availableCapabilityIds = {cap["capabilityId"] for cap in dev["capabilities"]}

        mapped: dict[int, str] = {}
        suppressed: list[int] = []
        unmapped: list[int] = []
        for cap in dev["capabilities"]:
            infos = get_capability_infos(
                modelInfos,
                cap["capabilityId"],
                cap["value"],
                availableCapabilityIds,
            )
            if infos:
                mapped[cap["capabilityId"]] = infos.get("name")
            elif infos is None:
                unmapped.append(cap["capabilityId"])
            else:
                suppressed.append(cap["capabilityId"])

        return mapped, sorted(suppressed), sorted(unmapped)

    def get_diagnostics(self) -> dict:
        """Describe the account as the API reports it, for a diagnostics dump.

        Every device the setup returns, whether or not somebody added it :
        unmapped hardware is what a dump is read for. A property of the account
        and not of the hub that happened to be asked. See docs/decisions.md.
        """
        configured = {
            subentry.data.get("deviceId")
            for subentry in self._entry.subentries.values()
        }

        devices = []
        for dev in self._account.devices:
            modelInfos = get_device_model_infos(self._account.devices, dev)

            mapped, suppressed, unmapped = self.get_capability_names(
                dev["deviceId"]
            )

            devices.append(
                {
                    "deviceId": dev["deviceId"],
                    "name": dev["name"],
                    "modelId": dev["modelId"],
                    "productId": dev["productId"],
                    "zoneId": dev["zoneId"],
                    "zoneName": self.get_zone_name(dev["zoneId"]),
                    "tags": dev["tags"],
                    "isConfiguredHere": dev["deviceId"] in configured,
                    # Under the API's own names, so a report can be compared
                    # against docs/api-surface.md without a translation step.
                    **{field: dev.get(field) for field in API_DECLARED_FIELDS},
                    "model": {
                        "name": modelInfos.name,
                        "type": str(modelInfos.type),
                        "infos": {
                            key: str(value)
                            for key, value in modelInfos.items()
                            if key not in ("name", "type")
                        },
                    },
                    "capabilities": {
                        "mapped": mapped,
                        # Known, and deliberately not an entity on this
                        # product. Listed rather than dropped: it is the
                        # difference between "nobody has named this" and
                        # "somebody decided this", and only one of the two is
                        # a report worth opening.
                        "suppressed": suppressed,
                        "unmapped": unmapped,
                        "values": {
                            cap["capabilityId"]: cap["value"]
                            for cap in dev["capabilities"]
                        },
                        # When the device last changed each value, which is
                        # what tells a wrong value from an id the hardware
                        # never feeds at all.
                        "modificationDates": {
                            cap["capabilityId"]: as_epoch(
                                cap.get("modificationDate")
                            )
                            for cap in dev["capabilities"]
                        },
                    },
                }
            )

        return {
            "setup": dict(self._account.setup),
            "zones": list(self._account.zones),
            "devices": devices,
        }

    def get_capability_value(
        self, capabilityId: int, defaultIfNotExist: str | None = "0"
    ):
        """Get value for a device capability."""
        dev = device_of(self)
        if dev is None:
            return None

        for capability in dev["capabilities"]:
            if capabilityId == capability["capabilityId"]:
                return capability["value"]

        return defaultIfNotExist

    def get_capability_modification_date(self, capabilityId: int) -> int | None:
        """When the device last changed one capability, as the API says."""
        dev = device_of(self)
        if dev is None:
            return None

        return next(
            (
                as_epoch(capability.get("modificationDate"))
                for capability in dev["capabilities"]
                if capability["capabilityId"] == capabilityId
            ),
            None,
        )

    def get_last_modification_date(self) -> int | None:
        """The newest modification date this device reports, if it reports one.

        The whole device rather than one capability : any one of them can sit
        unchanged for hours. See docs/decisions.md.
        """
        dev = device_of(self)
        if dev is None:
            return None

        dates = [
            as_epoch(capability.get("modificationDate"))
            for capability in dev["capabilities"]
        ]

        return max([date for date in dates if date is not None], default=None)

    def get_last_poll(self) -> datetime | None:
        """When the integration last heard from the API, as an aware datetime.

        The account's date, not this device's. Paired with
        `get_last_modification_date`, it separates "nothing changed" from
        "nobody asked".
        """
        return self._account.last_poll

    def get_is_available(self, deviceId: int | None = None) -> bool | None:
        """The cloud's own reachability flag for this device (`isAvailable`).

        Finer than `online`, which is the account's session. None when the
        field is absent, so a missing reading is unknown rather than a guessed
        connected state, and not cleared when the session drops.
        """
        dev = device_of(self, deviceId)
        return dev.get("isAvailable") if dev else None

    async def set_capability_value(self, capabilityId: int, value: str):
        """Set value for a device capability."""
        _LOGGER.debug(
            "Set_capability_value for %d : %d = %s", self._deviceId, capabilityId, value
        )
        if not self.online:
            return

        dev = device_of(self)
        if dev is None:
            return

        for capability in dev["capabilities"]:
            if capabilityId != capability["capabilityId"]:
                continue

            # Only on a completed execution. See docs/decisions.md.
            if await self._account.write_capability(
                self._deviceId, capabilityId, value
            ):
                capability["value"] = value

            return

    def away_mode_init(self, timestampStart, timestampEnd):
        """Init away mode timestamps."""
        self._timestamp_away_mode_start = timestampStart
        self._timestamp_away_mode_end = timestampEnd

    async def set_away_mode_bound(
        self,
        index: int,
        capabilityIdTimestamps: int,
        timestamp,
    ):
        """Set the away mode start (index 0) or end (index 1) timestamp."""
        if index == 0:
            self._timestamp_away_mode_start = timestamp
        else:
            self._timestamp_away_mode_end = timestamp
        self._timestamps_away_mode_capability_id = capabilityIdTimestamps
        self._timestamp_away_mode_last_change = datetime.now(
            tz=dt_util.DEFAULT_TIME_ZONE
        ).timestamp()

    def get_away_mode_start(self):
        """Get away mode start timestamp."""
        return self._timestamp_away_mode_start

    def get_away_mode_end(self):
        """Get away mode end timestamp."""
        return self._timestamp_away_mode_end

    async def set_away_mode_timestamps(
        self,
        capabilityIdMode,
        valueMode,
        capabilityIdTimestamps: int,
        timestampStart,
        timestampEnd,
    ):
        """Set away mode timestamps."""
        if not self.online:
            return

        # The window lives on the setup, not on the device, so it goes first
        # and the capability write only mirrors what was accepted.
        if not await self._account.set_absence(timestampStart, timestampEnd):
            return

        if timestampStart is not None and timestampEnd is not None:
            valueTimestamps = "[" + str(timestampStart) + "," + str(timestampEnd) + "]"
            await self.set_capability_value(capabilityIdTimestamps, valueTimestamps)
            _LOGGER.info("Away mode enabled %d -> %d", timestampStart, timestampEnd)
        else:
            await self.set_capability_value(capabilityIdTimestamps, "[0,0]")
            _LOGGER.info("Away mode disabled")

        if capabilityIdMode is not None and valueMode is not None:
            await self.set_capability_value(capabilityIdMode, valueMode)

        self._timestamp_away_mode_last_change = None


# see docs/decisions.md
_VIA_DEVICE_ID_SUPPORTED = "via_device_id" in DeviceInfo.__annotations__


def via_device_info(hass: HomeAssistant, via_device: tuple[str, str]) -> DeviceInfo:
    """The gateway link, keyed the way the running Home Assistant wants it.

    Empty when the registry does not hold the gateway. See docs/decisions.md.
    """
    if not _VIA_DEVICE_ID_SUPPORTED:
        return DeviceInfo(via_device=via_device)

    gateway = dr.async_get(hass).async_get_device(identifiers={via_device})
    if gateway is None:
        return DeviceInfo()

    return DeviceInfo(via_device_id=gateway.id)


def device_info_for(coordinator: Hub, device_uniq_id: str) -> DeviceInfo:
    """The device every entity of one subentry belongs to.

    Setup registers every device from this before any platform runs, so what
    the registry holds and what the entities declare are the same description.
    See docs/decisions.md.
    """
    model_name = coordinator.get_model_infos().name
    info = DeviceInfo(
        identifiers={(DOMAIN, device_uniq_id)},
        manufacturer="Atlantic",
        name=model_name,
        model=model_name,
        serial_number=coordinator.get_serial_number(),
        # On the device and not only as a diagnostic entity : "which version
        # is this box on" is the first line of a bug report.
        sw_version=coordinator.get_software_version(),
    )
    via_device = coordinator.get_via_device()
    if via_device is not None:
        info.update(via_device_info(coordinator.hass, via_device))

    return info


class CozytouchDeviceEntity(CoordinatorEntity):
    """A coordinator entity that belongs to one subentry's device."""

    _device_uniq_id: str

    @property
    def device_info(self) -> DeviceInfo:
        """Return the device info."""
        return device_info_for(self.coordinator, self._device_uniq_id)


def add_capability_entities(
    config_entry: CozytouchConfigEntry,
    async_add_entities,
    builders: dict[CapabilityType, Callable],
) -> None:
    """Build one platform's entities from the capabilities each device reports.

    `builders` maps a capability type to what to make of it, called with the
    four arguments every entity here takes and returning one entity or several.
    A type absent from the map belongs to another platform.
    """
    for subentry_id, subentry in config_entry.subentries.items():
        hub = config_entry.runtime_data.hubs[subentry_id]

        entities = []
        for capability in hub.get_capabilities_for_device():
            builder = builders.get(capability.type)
            if builder is None:
                continue

            built = builder(
                coordinator=hub,
                capability=capability,
                config_title=subentry.title,
                config_uniq_id=subentry_id,
            )
            entities.extend(built if isinstance(built, list) else [built])

        if entities:
            async_add_entities(entities, True, config_subentry_id=subentry_id)
