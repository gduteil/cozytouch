"""Atlantic Cozytouch Hub."""
from __future__ import annotations

import copy
from datetime import datetime, time, timedelta, timezone
import json
import logging

from aiohttp import ClientSession, ContentTypeError, FormData

from homeassistant import exceptions
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .capability import get_capability_infos
from .const import COZYTOUCH_ATLANTIC_API, COZYTOUCH_CLIENT_ID
from .model import get_model_infos

_LOGGER = logging.getLogger(__name__)


class Hub(DataUpdateCoordinator):
    """Atlantic Cozytouch Hub."""

    manufacturer = "Atlantic Group"
    _localization = {}

    _default_tarrifs = []
    _setup_tarrifs = []
    _consumptions = []
    _consumption_last_update = 0

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
            update_interval=timedelta(seconds=10),
        )
        self._session = ClientSession()
        self._host = "none"
        self._hass = hass
        self._username = username
        self._password = password
        self._deviceId = deviceId
        self._setupId = None
        self._mainDHWEnergyId = None
        self._mainHeatingEnergyId = None
        self._access_token = ""
        self._id = "cozytouch." + username.lower()
        self._tariffs = False
        self._create_unknown = False
        self._dump_json = False
        self._devices = []
        self.online = False

        # Load json for test during dev
        self._test_load = False
        if self._test_load:
            self._dump_json = False
            self.online = True
            with open(
                self._hass.config.config_dir + "/cozytouch_alfea.json",
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
                    token = await response.json()

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
                    COZYTOUCH_ATLANTIC_API + "/magellan/cozytouch/setupview",
                    headers=headers,
                ) as response:
                    json_data = await response.json()

                    # Store setup and energy prices IDs
                    self._setupId = json_data[0].get("id", None)
                    self._mainDHWEnergyId = json_data[0].get("mainDHWEnergy", None)
                    self._mainHeatingEnergyId = json_data[0].get(
                        "mainHeatingEnergy", None
                    )

                    # Update devices infos
                    self.update_devices_from_json_data(json_data)

                    # Store country to retrieve localization informations
                    if "address" in json_data[0]:
                        await self._update_localization(
                            json_data[0]["address"].get("country", None)
                        )

                    if self._tariffs:
                        await self._update_default_tariffs()
                        await self._update_setup_tariffs()

                self.online = True

            except CannotConnect:
                self.online = False

        return self.online

    async def close(self) -> None:
        """Close session."""
        await self._session.close()

    def update_devices_from_json_data(self, json_data) -> None:
        """Update the devices list."""

        if self._dump_json:
            with open(
                self._hass.config.config_dir + "/Cozytouch.json", "w", encoding="utf-8"
            ) as outfile:
                json_object = json.dumps(json_data, indent=4)
                outfile.write(json_object)

        # Start by removing old devices
        for local_device in self._devices[:]:
            bStillExists = False
            for remote_device in json_data[0]["devices"]:
                if remote_device["deviceId"] == local_device["deviceId"]:
                    bStillExists = True
                    break

            if bStillExists is False:
                self._devices.remove(local_device)

        # Create new devices
        deviceIndex = -1
        for remote_device in json_data[0]["devices"]:
            deviceIndex = -1
            for i, local_device in enumerate(self._devices):
                if remote_device["deviceId"] == local_device["deviceId"]:
                    deviceIndex = i
                    break

            if deviceIndex == -1:
                self._devices.append(
                    {
                        "deviceId": remote_device["deviceId"],
                        "name": remote_device["name"],
                        "gatewaySerialNumber": remote_device["gatewaySerialNumber"],
                        "modelId": remote_device["modelId"],
                        "productId": remote_device["productId"],
                        "modelInfos": get_model_infos(remote_device["modelId"]),
                        "capabilities": [],
                    }
                )
                deviceIndex = len(self._devices) - 1

            # Only retrieve capabilites from current device
            if self._deviceId == remote_device["deviceId"]:
                self._devices[deviceIndex]["capabilities"] = copy.deepcopy(
                    remote_device["capabilities"]
                )

    def set_create_entities_for_tariffs(self, tariffs: bool) -> None:
        """Set option from config flow to create entities for tariffs."""
        self._tariffs = tariffs

    def get_create_entities_for_tariffs(self) -> bool:
        """Get option from config flow to create entities for tariffs."""
        modelInfos = self.get_model_infos()
        return self._tariffs and modelInfos.get("supportTariff", False)

    def get_dhw_energy_id(self) -> int:
        """Get DHW energy ID."""
        return self._mainDHWEnergyId

    def get_heating_energy_id(self) -> int:
        """Get heating energy ID."""
        return self._mainHeatingEnergyId

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
                    for dev in self._devices:
                        if dev["deviceId"] == self._deviceId:
                            dev["capabilities"] = copy.deepcopy(json_data)
                            break
                except ContentTypeError:
                    self.online = False

            # Update tariffs and consumptions
            if self._tariffs:
                if len(self._default_tarrifs) == 0:
                    await self._update_default_tariffs()

                if len(self._setup_tarrifs) == 0:
                    await self._update_setup_tariffs()

                # Only update consumption every 10 minute
                if (datetime.now().timestamp() - self._consumption_last_update) > 600:
                    await self._update_consumptions()

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

    def get_model_infos(self, deviceId: int | None = None) -> str:
        """Get model infos."""
        if not deviceId:
            deviceId = self._deviceId

        for dev in self._devices:
            if dev["deviceId"] == deviceId:
                return get_model_infos(dev["modelId"])

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
                            "name": "Capability_" + str(capability["capabilityId"]),
                            "type": "string",
                            "category": "diag",
                        }

                    if capability_infos is not None and len(capability_infos) > 0:
                        capability_infos["deviceId"] = deviceId
                        capability_infos["capabilityId"] = capability["capabilityId"]

                        capabilities.append(capability_infos)

        return capabilities

    def get_capability_infos(
        self, modelId: int, capabilityId: int, capabilityValue: str
    ):
        """Get capability infos."""
        return get_capability_infos(modelId, capabilityId, capabilityValue)

    def get_capability_value(self, capabilityId: int):
        """Get value for a device capability."""
        for dev in self._devices:
            if dev["deviceId"] == self._deviceId:
                for capability in dev["capabilities"]:
                    if capabilityId == capability["capabilityId"]:
                        return capability["value"]

                return "0"

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
                                            if nbRetry > 3:
                                                break

                                            time.sleep(1)

                                        if completed:
                                            capability["value"] = value
                            break

    def get_energy_tariff(self, energyId: int) -> float | None:
        """Get tariff of energy ID, return first tariff for now."""
        price = None
        for tariff in self._setup_tarrifs:
            if (
                tariff.get("active", False)
                and tariff.get("consumptionType", -1) == energyId
            ):
                energyTariffLines = tariff.get("energyTariffLines", [])
                if len(energyTariffLines) > 0:
                    price = energyTariffLines[0].get("energyPrice", None)
                    break

        if not price and energyId < len(self._default_tarrifs):
            for tariff in self._default_tarrifs:
                if (
                    tariff.get("active", False)
                    and tariff.get("consumptionType", -1) == energyId
                ):
                    energyTariffLines = tariff.get("energyTariffLines", [])
                    if len(energyTariffLines) > 0:
                        price = energyTariffLines[0].get("energyPrice", None)
                        break

        return price

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
                    for localization in json_data:
                        if localization.get("countryCode", "") == country:
                            self._localization = copy.deepcopy(localization)
                            break

                except ContentTypeError:
                    self._localization = {}

        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }
        async with self._session.get(
            COZYTOUCH_ATLANTIC_API + "/magellan/tariffs/default",
            headers=headers,
        ) as response:
            try:
                json_data = await response.json()
                self._default_tarrifs = copy.deepcopy(json_data)

            except ContentTypeError:
                self._default_tarrifs = []

    async def _update_default_tariffs(self):
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
        }
        async with self._session.get(
            COZYTOUCH_ATLANTIC_API + "/magellan/tariffs/default",
            headers=headers,
        ) as response:
            try:
                json_data = await response.json()
                self._default_tarrifs = copy.deepcopy(json_data)

            except ContentTypeError:
                self._default_tarrifs = []

    async def _update_setup_tariffs(self):
        if self._setupId:
            headers = {
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            }
            async with self._session.get(
                COZYTOUCH_ATLANTIC_API
                + "/magellan/tariffs/?setupId="
                + str(self._setupId),
                headers=headers,
            ) as response:
                try:
                    json_data = await response.json()
                    self._setup_tarrifs = copy.deepcopy(json_data)

                except ContentTypeError:
                    self._setup_tarrifs = []

    async def _update_consumptions(self):
        if self._setupId:
            headers = {
                "Authorization": f"Bearer {self._access_token}",
                "Content-Type": "application/json",
            }

            timestamp = int(
                datetime.combine(datetime.now(timezone.utc), time.min).timestamp()
            )
            async with self._session.get(
                COZYTOUCH_ATLANTIC_API
                + "/magellan/setups/"
                + str(self._setupId)
                + "/consumptions?fromDate="
                + str(timestamp)
                + "&toDate="
                + str(timestamp),
                headers=headers,
            ) as response:
                try:
                    json_data = await response.json()
                    if response.status == 200:
                        self._consumptions = copy.deepcopy(json_data)
                        self._consumption_last_update = datetime.now().timestamp()

                except ContentTypeError:
                    self._consumptions = []

    def get_daily_consumption(self, index: int):
        """Get daily consumption."""
        if (
            index < len(self._consumptions)
            and "consumptionPeriods" in self._consumptions[index]
        ):
            consumptions = self._consumptions[index]["consumptionPeriods"][-1]
            if "consumedQuantity" in consumptions:
                return float(consumptions["consumedQuantity"])


class CannotConnect(exceptions.HomeAssistantError):
    """Error to indicate we cannot connect."""
