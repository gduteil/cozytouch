"""Atlantic Cozytouch Hub."""

from __future__ import annotations

import asyncio
import copy
from datetime import UTC, datetime, time as t, timedelta, timezone
import json
import logging

from aiohttp import ClientSession, ContentTypeError, FormData

from homeassistant import exceptions
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from .capability import get_capability_infos
from .const import COZYTOUCH_ATLANTIC_API, COZYTOUCH_CLIENT_ID
from .model import get_model_infos

_LOGGER = logging.getLogger(__name__)

EXPLORER_EVO_3_MODEL_ID = 2374
EXPLORER_EVO_3_REQUIRED_CAPABILITIES = (
    258,  # Tank Capacity
    265,  # Tank Middle Temperature
    267,  # Tank Bottom Temperature
    268,  # V40 Water Available
    270,  # V40 Water Capacity
    271,  # Hot Water Available
)


class Hub(DataUpdateCoordinator):
    """Atlantic Cozytouch Hub."""

    manufacturer = "Atlantic Group"
    _localization = {}
    _setup = {}
    _zones = {}

    _timestamp_away_mode_last_change = None
    _timestamp_away_mode_start = None
    _timestamp_away_mode_end = None

    def __init__(
        self,
        hass: HomeAssistant,
        username: str,
        password: str,
        deviceId: int | None = None,
    ) -> None:
        """Init hub."""
        super().__init__(
            hass,
            _LOGGER,
            name="Cozytouch_" + str(deviceId),
            update_interval=timedelta(seconds=60),
        )
        self._session = ClientSession()
        self._host = "none"
        self._hass = hass
        self._username = username
        self._password = password
        self._deviceId = deviceId
        self._zoneId = -1
        self._access_token = ""
        self._id = "cozytouch." + username.lower()
        self._create_unknown = False
        self._dump_json = False
        self._devices = []

        self.online = False

        modelInfos = self.get_model_infos()
        if "name" in modelInfos:
            self.device_info = DeviceInfo(
                entry_type=DeviceEntryType.SERVICE,
                identifiers={("cozytouch", "cozytouch" + str(deviceId))},
                manufacturer="Atlantic",
                name=modelInfos["name"],
            )

        self._timestamps_away_mode_capability_id = None

        # Load json for test during dev
        self._test_load = False
        if self._test_load:
            self._dump_json = False
            self.online = True
            with open(
                self._hass.config.config_dir + "/cozytouch_eoras2.json",
                encoding="utf-8",
            ) as json_file:
                file_contents = json_file.read()
                self.update_devices_from_json_data(json.loads(file_contents))

    @property
    def hub_id(self) -> str:
        """ID for hub."""
        return self._id

    async def test_connection(self) -> bool:
        """Test connection."""
        await self.connect()
        return self.online

    async def connect(self) -> bool:
        """Connect to Cozytouch server."""
        if self.online is False:
            try:
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
                ) as response:
                    try:
                        token = await response.json()
                    except ContentTypeError as err:
                        _LOGGER.warning(
                            "Cozytouch token response is not JSON: HTTP %s, content-type %s",
                            response.status,
                            response.headers.get("content-type"),
                        )
                        raise CannotConnect from err

                    if "error" in token and token["error"] == "invalid_grant":
                        raise CannotConnect

                    if "token_type" not in token:
                        raise CannotConnect

                    if "access_token" not in token:
                        raise CannotConnect

                    self._access_token = token["access_token"]

                headers = {
                    "Authorization": f"Bearer {self._access_token}",
                    "Content-Type": "application/json",
                }
                async with self._session.get(
                    COZYTOUCH_ATLANTIC_API + "/magellan/cozytouch/setupviewv2",
                    headers=headers,
                ) as response:
                    try:
                        json_data = await response.json()
                    except ContentTypeError as err:
                        _LOGGER.warning(
                            "Cozytouch setup response is not JSON: HTTP %s, content-type %s",
                            response.status,
                            response.headers.get("content-type"),
                        )
                        raise CannotConnect from err

                    setup_data = self._extract_setup_data(json_data)

                    # Store setup
                    for key in (
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
                        "setupBuildingDate",
                        "type",
                    ):
                        if key in setup_data:
                            self._setup[key] = copy.deepcopy(setup_data[key])

                    # Update devices infos
                    await asyncio.get_event_loop().run_in_executor(
                        None, self.update_devices_from_setup_data, setup_data
                    )

                    # Store country to retrieve localization informations
                    if "address" in setup_data:
                        await self._update_localization(
                            setup_data["address"].get("country", None)
                        )

                    # Store zones informations
                    if "zones" in setup_data:
                        copy.deepcopy(setup_data["zones"])

                self.online = True

            except CannotConnect:
                self.online = False

        return self.online

    async def close(self) -> None:
        """Close session."""
        await self._session.close()

    def _extract_setup_data(self, json_data):
        """Return the setup object from known Cozytouch API response shapes."""
        candidates = [json_data]
        if isinstance(json_data, dict):
            candidates.extend(
                json_data.get(key) for key in ("setup", "data", "result", "items")
            )

        for candidate in candidates:
            if isinstance(candidate, list) and candidate:
                first = candidate[0]
                if isinstance(first, dict) and "devices" in first:
                    return first
            if isinstance(candidate, dict) and "devices" in candidate:
                return candidate

        _LOGGER.warning(
            "Unexpected Cozytouch setup payload shape: %s",
            self._payload_shape(json_data),
        )
        raise CannotConnect

    def _extract_capabilities_data(self, json_data):
        """Return a capabilities list from known Cozytouch API response shapes."""
        if isinstance(json_data, list):
            return json_data
        if isinstance(json_data, dict):
            for key in ("capabilities", "data", "result", "items"):
                candidate = json_data.get(key)
                if isinstance(candidate, list):
                    return candidate

        _LOGGER.warning(
            "Unexpected Cozytouch capabilities payload shape for device %s: %s",
            self._deviceId,
            self._payload_shape(json_data),
        )
        return None

    def _payload_shape(self, payload) -> str:
        """Describe an unexpected payload without logging sensitive content."""
        if isinstance(payload, dict):
            return "dict keys=" + ",".join(sorted(str(key) for key in payload.keys()))
        if isinstance(payload, list):
            return f"list len={len(payload)}"
        return type(payload).__name__

    def _ensure_model_required_capabilities(self, capabilities, model_id: int):
        """Keep known telemetry entities available when setupview omits them."""
        merged = copy.deepcopy(capabilities) if isinstance(capabilities, list) else []
        if model_id == EXPLORER_EVO_3_MODEL_ID:
            existing_ids = {
                capability.get("capabilityId")
                for capability in merged
                if isinstance(capability, dict)
            }
            for capability_id in EXPLORER_EVO_3_REQUIRED_CAPABILITIES:
                if capability_id not in existing_ids:
                    merged.append({"capabilityId": capability_id, "value": None})
        return merged

    def _merge_capabilities(self, existing, incoming, model_id: int):
        """Merge API updates without dropping known-but-temporarily-omitted caps."""
        merged_by_id = {}
        for capability in existing or []:
            if isinstance(capability, dict) and "capabilityId" in capability:
                merged_by_id[capability["capabilityId"]] = copy.deepcopy(capability)
        for capability in incoming or []:
            if isinstance(capability, dict) and "capabilityId" in capability:
                merged_by_id[capability["capabilityId"]] = copy.deepcopy(capability)
        return self._ensure_model_required_capabilities(
            list(merged_by_id.values()), model_id
        )

    def update_devices_from_json_data(self, json_data) -> None:
        """Update the devices list from a raw setup API response."""
        self.update_devices_from_setup_data(self._extract_setup_data(json_data))

    def update_devices_from_setup_data(self, setup_data) -> None:
        """Update the devices list from a normalized setup object."""

        if self._dump_json:
            with open(
                self._hass.config.config_dir + "/Cozytouch.json", "w", encoding="utf-8"
            ) as outfile:
                json_object = json.dumps(setup_data, indent=4)
                outfile.write(json_object)

        # Get zones
        if len(self._zones) == 0 and "zones" in setup_data:
            self._zones = copy.deepcopy(setup_data["zones"])

        remote_devices = setup_data.get("devices", [])
        if not isinstance(remote_devices, list):
            _LOGGER.warning(
                "Unexpected Cozytouch devices payload shape: %s",
                self._payload_shape(remote_devices),
            )
            return

        # Start by removing old devices
        for local_device in self._devices[:]:
            bStillExists = False
            for remote_device in remote_devices:
                if remote_device["deviceId"] == local_device["deviceId"]:
                    bStillExists = True
                    break

            if bStillExists is False:
                self._devices.remove(local_device)

        # Create new devices
        deviceIndex = -1
        for remote_device in remote_devices:
            deviceIndex = -1
            for i, local_device in enumerate(self._devices):
                if remote_device["deviceId"] == local_device["deviceId"]:
                    deviceIndex = i
                    self._zoneId = remote_device["zoneId"]
                    break

            if deviceIndex == -1:
                device = {
                    "deviceId": remote_device["deviceId"],
                    "name": remote_device["name"],
                    "gatewaySerialNumber": remote_device["gatewaySerialNumber"],
                    "modelId": remote_device["modelId"],
                    "productId": remote_device["productId"],
                    "zoneId": remote_device["zoneId"],
                    "modelInfos": get_model_infos(remote_device["modelId"]),
                    "capabilities": [],
                    "tags": [],
                }
                if "tags" in remote_device:
                    device["tags"] = copy.deepcopy(remote_device["tags"])

                self._devices.append(device)
                deviceIndex = len(self._devices) - 1

            # Only retrieve capabilites from current device
            if self._deviceId == remote_device["deviceId"]:
                self._devices[deviceIndex]["capabilities"] = self._merge_capabilities(
                    self._devices[deviceIndex].get("capabilities", []),
                    remote_device.get("capabilities", []),
                    remote_device.get("modelId"),
                )

    def set_create_entities_for_unknown_entities(self, create_unknown: bool) -> None:
        """Set option from config flow to create entities for unknown capabilities."""
        self._create_unknown = create_unknown

    def get_create_entities_for_unknown_entities(self) -> bool:
        """Get option from config flow to create entities for unknown capabilities."""
        return self._create_unknown

    def set_dump_json(self, dump_json: bool) -> None:
        """Set option from config flow to dump JSON from API."""
        self._dump_json = dump_json

    async def _async_update_data(self):
        _LOGGER.debug("_async_update_data %d", self._deviceId)
        if self._test_load:
            return

        if self.online:
            headers = {
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            }
            async with self._session.get(
                COZYTOUCH_ATLANTIC_API
                + "/magellan/capabilities/?deviceId="
                + str(self._deviceId),
                headers=headers,
            ) as response:
                try:
                    json_data = await response.json()

                    capabilities_data = self._extract_capabilities_data(json_data)
                    if capabilities_data is not None:
                        for dev in self._devices:
                            if dev["deviceId"] == self._deviceId:
                                dev["capabilities"] = self._merge_capabilities(
                                    dev.get("capabilities", []),
                                    capabilities_data,
                                    dev.get("modelId"),
                                )
                                break

                        if (
                            self._timestamp_away_mode_last_change is not None
                            and self._timestamps_away_mode_capability_id is not None
                            and self._timestamp_away_mode_start is not None
                            and self._timestamp_away_mode_end is not None
                        ):
                            now = datetime.now(tz=dt_util.DEFAULT_TIME_ZONE).timestamp()
                            if now - self._timestamp_away_mode_last_change > 20:
                                await self.set_away_mode_timestamps(
                                    None,
                                    None,
                                    self._timestamps_away_mode_capability_id,
                                    self._timestamp_away_mode_start,
                                    self._timestamp_away_mode_end,
                                )
                except ContentTypeError:
                    _LOGGER.warning(
                        "Cozytouch capabilities response is not JSON for device %s",
                        self._deviceId,
                    )
                    self.online = False

        else:
            await self.connect()

    def devices(self):
        """Get devices list."""
        devs = []
        for dev in self._devices:
            devs.append(
                {
                    "deviceId": dev["deviceId"],
                    "name": dev["name"],
                    "model": dev["modelInfos"]["name"],
                }
            )

        return devs

    def get_zone_name(self, zoneId: int | None = None) -> str:
        """Get zone infos."""
        if not zoneId:
            zoneId = self._zoneId

        for zone in self._zones:
            if "id" in zone and zone["id"] == zoneId:
                return zone["name"]

        return str(zoneId)

    def get_model_infos(self, deviceId: int | None = None) -> str:
        """Get model infos."""
        if not deviceId:
            deviceId = self._deviceId

        for dev in self._devices:
            if dev["deviceId"] == deviceId:
                zoneId = dev["zoneId"]

                # Special case for sub-devices, use master zone Id
                for masterDev in self._devices:
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

                return get_model_infos(dev["modelId"], self.get_zone_name(zoneId))

        return get_model_infos(-1)

    def get_serial_number(self, deviceId: int | None = None) -> str:
        """Get serial number."""
        if not deviceId:
            deviceId = self._deviceId

        for dev in self._devices:
            if dev["deviceId"] == deviceId:
                return dev["gatewaySerialNumber"]

        return "Unknown"

    def get_capabilities_for_device(self, deviceId: int | None = None):
        """Get capabilities for a device."""

        if not deviceId:
            deviceId = self._deviceId

        capabilities = []
        for dev in self._devices:
            if dev["deviceId"] == deviceId:
                modelInfos = get_model_infos(dev["modelId"])
                for capability in dev["capabilities"]:
                    capability_infos = get_capability_infos(
                        modelInfos,
                        capability["capabilityId"],
                        capability["value"],
                    )

                    if capability_infos is None and self._create_unknown:
                        capability_infos = {
                            "capabilityId": capability["capabilityId"],
                            "name": "Capability_" + str(capability["capabilityId"]),
                            "type": "string",
                            "category": "diag",
                        }

                    if capability_infos is not None and len(capability_infos) > 0:
                        capability_infos["deviceId"] = deviceId

                        isDuplicate = False
                        if "capabilityDuplicate" in capability_infos:
                            for cap in capabilities:
                                if (
                                    cap["capabilityId"]
                                    == capability_infos["capabilityDuplicate"]
                                ):
                                    isDuplicate = True
                                    break

                        if not isDuplicate:
                            capabilities.append(capability_infos)

        return capabilities

    def get_capability_infos(
        self, modelId: int, capabilityId: int, capabilityValue: str
    ):
        """Get capability infos."""
        return get_capability_infos(modelId, capabilityId, capabilityValue)

    def get_capability_value(
        self, capabilityId: int, defaultIfNotExist: str | None = "0"
    ):
        """Get value for a device capability."""
        for dev in self._devices:
            if dev["deviceId"] == self._deviceId:
                for capability in dev["capabilities"]:
                    if capabilityId == capability["capabilityId"]:
                        return capability["value"]

                return defaultIfNotExist

        return None

    async def set_capability_value(self, capabilityId: int, value: str):
        """Set value for a device capability."""
        _LOGGER.debug(
            "Set_capability_value for %d : %d = %s", self._deviceId, capabilityId, value
        )
        if self.online:
            for dev in self._devices:
                if dev["deviceId"] == self._deviceId:
                    for capability in dev["capabilities"]:
                        if capabilityId == capability["capabilityId"]:
                            if self._test_load:
                                capability["value"] = value
                            else:
                                # Write capability value
                                async with self._session.post(
                                    COZYTOUCH_ATLANTIC_API
                                    + "/magellan/executions/writecapability",
                                    json={
                                        "capabilityId": capabilityId,
                                        "deviceId": self._deviceId,
                                        "value": value,
                                    },
                                    headers={
                                        "Authorization": f"Bearer {self._access_token}",
                                        "Content-Type": "application/json",
                                    },
                                ) as response:
                                    if response.status == 201:
                                        # Check completion
                                        executionId = await response.json()
                                        completed = False
                                        nbRetry = 0
                                        while not completed:
                                            async with self._session.get(
                                                COZYTOUCH_ATLANTIC_API
                                                + "/magellan/executions/"
                                                + str(executionId),
                                                headers={
                                                    "Authorization": f"Bearer {self._access_token}",
                                                    "Content-Type": "application/json",
                                                },
                                            ) as executionResponse:
                                                try:
                                                    execution_data = (
                                                        await executionResponse.json()
                                                    )
                                                    execution_state = (
                                                        execution_data.get(
                                                            "state", False
                                                        )
                                                    )
                                                    if execution_state == 1:
                                                        _LOGGER.info(
                                                            "Execution_state waiting execution"
                                                        )
                                                    if execution_state == 2:
                                                        _LOGGER.info(
                                                            "Execution_state in progress"
                                                        )
                                                    elif execution_state == 3:
                                                        _LOGGER.info(
                                                            "Execution_state completed"
                                                        )
                                                        completed = True
                                                        break
                                                    else:
                                                        _LOGGER.info(
                                                            "Execution_state error"
                                                        )
                                                        break

                                                except ContentTypeError:
                                                    self.online = False
                                                    break

                                            nbRetry += 1
                                            if nbRetry > 5:
                                                break

                                            await asyncio.sleep(1)

                                        if completed:
                                            capability["value"] = value
                            break

    def away_mode_init(self, timestampStart, timestampEnd):
        """Init away mode timestamps."""
        self._timestamp_away_mode_start = timestampStart
        self._timestamp_away_mode_end = timestampEnd

    async def set_away_mode_start(
        self,
        capabilityIdTimestamps: int,
        timestamp,
    ):
        """Set away mode start timestamp."""
        self._timestamp_away_mode_start = timestamp
        self._timestamps_away_mode_capability_id = capabilityIdTimestamps
        self._timestamp_away_mode_last_change = datetime.now(
            tz=dt_util.DEFAULT_TIME_ZONE
        ).timestamp()

    def get_away_mode_start(self):
        """Get away mode start timestamp."""
        return self._timestamp_away_mode_start

    async def set_away_mode_end(
        self,
        capabilityIdTimestamps: int,
        timestamp,
    ):
        """Set away mode end timestamp."""
        self._timestamp_away_mode_end = timestamp
        self._timestamps_away_mode_capability_id = capabilityIdTimestamps
        self._timestamp_away_mode_last_change = datetime.now(
            tz=dt_util.DEFAULT_TIME_ZONE
        ).timestamp()

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

        if self.online:
            # Update setup
            json_data = {}
            for key in (
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
            ):
                if key in self._setup:
                    json_data[key] = copy.deepcopy(self._setup[key])

            json_data["absence"] = {}
            if timestampStart is not None and timestampEnd is not None:
                json_data["absence"]["startDate"] = timestampStart
                json_data["absence"]["endDate"] = timestampEnd
                _timestamp_away_mode_start = timestampStart
                _timestamp_away_mode_end = timestampEnd

            async with self._session.put(
                COZYTOUCH_ATLANTIC_API
                + "/magellan/v2/setups/"
                + str(self._setup["id"]),
                json=json_data,
                headers={
                    "Authorization": f"Bearer {self._access_token}",
                    "Content-Type": "application/json",
                },
            ) as response:
                if response.status in (200, 204):
                    if timestampStart is not None and timestampEnd is not None:
                        valueTimestamps = (
                            "[" + str(timestampStart) + "," + str(timestampEnd) + "]"
                        )
                        await self.set_capability_value(
                            capabilityIdTimestamps, valueTimestamps
                        )
                        _LOGGER.info(
                            "Away mode enabled %d -> %d", timestampStart, timestampEnd
                        )
                    else:
                        valueTimestamps = "[0,0]"
                        await self.set_capability_value(
                            capabilityIdTimestamps, valueTimestamps
                        )
                        _LOGGER.info("Away mode disabled")

                    if capabilityIdMode is not None and valueMode is not None:
                        await self.set_capability_value(capabilityIdMode, valueMode)

                    self._timestamp_away_mode_last_change = None
                else:
                    _LOGGER.error(
                        "Set away mode : response %d (%s)",
                        response.status,
                        str(response.request_info),
                    )

    async def _update_localization(self, country: str):
        if len(self._localization) == 0:
            headers = {
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            }
            async with self._session.get(
                COZYTOUCH_ATLANTIC_API + "/magellan/refs/countries",
                headers=headers,
            ) as response:
                try:
                    json_data = await response.json()
                    if isinstance(json_data, list):
                        for localization in json_data:
                            if localization.get("countryCode", "") == country:
                                self._localization = copy.deepcopy(localization)
                                break

                except ContentTypeError:
                    self._localization = {}


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""
