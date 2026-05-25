"""Atlantic Cozytouch Hub."""

from __future__ import annotations

import asyncio
import base64
import copy
from datetime import UTC, datetime, time as t, timedelta, timezone
import json
import logging
import re

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
EXPLORER_EVO_3_FALLBACK_TANK_CAPACITY_CAPABILITY = 900258
EXPLORER_EVO_3_FALLBACK_TANK_MIDDLE_TEMPERATURE_CAPABILITY = 900265
EXPLORER_EVO_3_FALLBACK_V40_AVAILABLE_CAPABILITY = 900268
EXPLORER_EVO_3_FALLBACK_V40_CAPACITY_CAPABILITY = 900270
EXPLORER_EVO_3_FALLBACK_TANK_CAPACITY_L = 260.0
EXPLORER_EVO_3_MIXED_WATER_TEMPERATURE_C = 40.0
EXPLORER_EVO_3_FALLBACK_MIN_USABLE_TANK_TEMPERATURE_C = 33.0
EXPLORER_EVO_3_OVERKIZ_STATE_TO_CAPABILITY = {
    "io:MiddleWaterTemperatureState": 265,
    "core:MiddleWaterTemperatureState": 265,
    "core:MiddleWaterTemperatureInState": 265,
    "core:BottomTankWaterTemperatureState": 267,
}
EXPLORER_EVO_3_OVERKIZ_FALLBACK_INTERVAL = timedelta(minutes=5)
EXPLORER_EVO_3_MAGELLAN_PROBE_INTERVAL = timedelta(hours=6)
OVERKIZ_ENDUSER_API = (
    "https://ha110-1.overkiz.com/enduser-mobile-web/enduserAPI"
)
COZYTOUCH_OVERKIZ_CLIENT_ID = (
    "ZThEMW5BM2h2djF0bmMxTXBvQTdHNXVENDZBYTo3aktaS1N3ZlVJNGRvaDdqRWZJVWRzR2VHNWth"
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
        self._last_explorer_capability_diagnostic = None
        self._last_explorer_overkiz_fallback_attempt = None
        self._last_explorer_magellan_probe_attempt = None
        self._explorer_overkiz_fallback_diagnostics_seen = set()
        self._explorer_magellan_probe_diagnostics_seen = set()

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

    def _cozytouch_token_scope(self) -> str:
        """Return the current Cozytouch mobile-app token scope shape."""
        return f"openid device_{int(datetime.now(UTC).timestamp())}"

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
                            "scope": self._cozytouch_token_scope(),
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
                    for dev in self._devices:
                        if dev["deviceId"] == self._deviceId:
                            await self._probe_explorer_magellan_endpoints(dev)
                            await self._apply_explorer_overkiz_temperature_fallback(
                                dev
                            )
                            break

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
        merged = self._ensure_model_required_capabilities(
            list(merged_by_id.values()), model_id
        )
        merged = self._apply_explorer_calculated_fallbacks(merged, model_id)
        self._log_explorer_capability_diagnostic(merged, model_id)
        return merged

    def _apply_explorer_calculated_fallbacks(self, capabilities, model_id: int):
        """Add Explorer fallback values derived from the app-visible payload."""
        if model_id != EXPLORER_EVO_3_MODEL_ID:
            return capabilities

        merged_by_id = {
            capability.get("capabilityId"): copy.deepcopy(capability)
            for capability in capabilities or []
            if isinstance(capability, dict) and "capabilityId" in capability
        }

        cold_water_temperature = self._get_capability_float(
            merged_by_id, 280, default=15.0
        )
        water_limit = self._get_capability_float(merged_by_id, 105300, default=62.0)
        max_user_target = self._get_capability_float(
            merged_by_id,
            252,
            default=water_limit,
        )
        target_temperature = self._get_capability_float(merged_by_id, 22)
        if target_temperature is None:
            target_temperature = self._get_capability_float(merged_by_id, 40)
        if target_temperature is None:
            target_temperature = max_user_target
        water_limit = self._get_capability_float(
            merged_by_id, 105300, default=max_user_target
        )
        hot_water_available_percent = self._get_capability_float(merged_by_id, 271)

        tank_capacity = self._get_capability_float(
            merged_by_id,
            258,
            default=EXPLORER_EVO_3_FALLBACK_TANK_CAPACITY_L,
        )
        self._set_synthetic_capability(
            merged_by_id,
            EXPLORER_EVO_3_FALLBACK_TANK_CAPACITY_CAPABILITY,
            tank_capacity,
        )

        tank_middle_fallback = self._get_capability_float(merged_by_id, 265)
        if (
            tank_middle_fallback is None
            and hot_water_available_percent is not None
            and target_temperature is not None
        ):
            bounded_percent = max(0.0, min(100.0, hot_water_available_percent))
            usable_floor = min(
                EXPLORER_EVO_3_FALLBACK_MIN_USABLE_TANK_TEMPERATURE_C,
                target_temperature,
            )
            tank_middle_fallback = usable_floor + (
                (target_temperature - usable_floor) * bounded_percent / 100.0
            )
        self._set_synthetic_capability(
            merged_by_id,
            EXPLORER_EVO_3_FALLBACK_TANK_MIDDLE_TEMPERATURE_CAPABILITY,
            tank_middle_fallback,
        )

        real_v40_capacity = self._get_capability_float(merged_by_id, 270)
        v40_capacity_fallback = real_v40_capacity
        if (
            v40_capacity_fallback is None
            and tank_capacity is not None
            and cold_water_temperature is not None
            and water_limit is not None
            and EXPLORER_EVO_3_MIXED_WATER_TEMPERATURE_C > cold_water_temperature
            and water_limit > cold_water_temperature
        ):
            v40_capacity_fallback = tank_capacity * (
                (water_limit - cold_water_temperature)
                / (EXPLORER_EVO_3_MIXED_WATER_TEMPERATURE_C - cold_water_temperature)
            )
        self._set_synthetic_capability(
            merged_by_id,
            EXPLORER_EVO_3_FALLBACK_V40_CAPACITY_CAPABILITY,
            v40_capacity_fallback,
        )

        real_v40_available = self._get_capability_float(merged_by_id, 268)
        v40_available_fallback = real_v40_available
        if (
            v40_available_fallback is None
            and v40_capacity_fallback is not None
            and hot_water_available_percent is not None
        ):
            v40_available_fallback = (
                v40_capacity_fallback * hot_water_available_percent / 100.0
            )
        self._set_synthetic_capability(
            merged_by_id,
            EXPLORER_EVO_3_FALLBACK_V40_AVAILABLE_CAPABILITY,
            v40_available_fallback,
        )

        return list(merged_by_id.values())

    def _get_capability_float(self, capabilities_by_id, capability_id, default=None):
        """Return a numeric capability value from a capabilities dictionary."""
        capability = capabilities_by_id.get(capability_id)
        if not isinstance(capability, dict):
            return default
        value = capability.get("value")
        if value is None or isinstance(value, bool):
            return default
        try:
            return float(value)
        except (TypeError, ValueError):
            return default

    def _set_synthetic_capability(self, capabilities_by_id, capability_id, value):
        """Set a synthetic capability value while keeping it clearly separate."""
        capabilities_by_id[capability_id] = {
            "capabilityId": capability_id,
            "value": None if value is None else round(float(value), 2),
        }

    def _explorer_missing_capabilities(self, capabilities, capability_ids):
        """Return known Explorer capabilities that currently have no value."""
        by_id = {
            capability.get("capabilityId"): capability
            for capability in capabilities or []
            if isinstance(capability, dict)
        }
        return [
            capability_id
            for capability_id in capability_ids
            if by_id.get(capability_id, {}).get("value") is None
        ]

    async def _apply_explorer_overkiz_temperature_fallback(self, dev) -> None:
        """Fill missing Explorer temperatures from the Overkiz state payload."""
        if dev.get("modelId") != EXPLORER_EVO_3_MODEL_ID:
            return

        missing = self._explorer_missing_capabilities(
            dev.get("capabilities", []),
            set(EXPLORER_EVO_3_OVERKIZ_STATE_TO_CAPABILITY.values()),
        )
        if not missing:
            return

        now = datetime.now(UTC)
        if (
            self._last_explorer_overkiz_fallback_attempt is not None
            and now - self._last_explorer_overkiz_fallback_attempt
            < EXPLORER_EVO_3_OVERKIZ_FALLBACK_INTERVAL
        ):
            return
        self._last_explorer_overkiz_fallback_attempt = now

        overkiz_setup = await self._fetch_overkiz_setup()
        if overkiz_setup is None:
            return

        overkiz_values = self._extract_explorer_overkiz_temperature_values(
            overkiz_setup
        )
        if not overkiz_values:
            self._log_explorer_overkiz_fallback_diagnostic(
                "no-supported-temperature-states", []
            )
            return

        applied = []
        capabilities_by_id = {
            capability.get("capabilityId"): capability
            for capability in dev.get("capabilities", [])
            if isinstance(capability, dict)
        }
        for state_name, value in overkiz_values.items():
            capability_id = EXPLORER_EVO_3_OVERKIZ_STATE_TO_CAPABILITY[state_name]
            if capability_id not in missing or value is None:
                continue
            capability = capabilities_by_id.get(capability_id)
            if capability is None:
                continue
            capability["value"] = value
            applied.append(f"{state_name}->{capability_id}={value}")

        if applied:
            self._log_explorer_overkiz_fallback_diagnostic("applied", applied)
            self._log_explorer_capability_diagnostic(
                dev.get("capabilities", []), dev.get("modelId")
            )
        else:
            self._log_explorer_overkiz_fallback_diagnostic(
                "found-no-missing-match",
                [f"{name}={value}" for name, value in overkiz_values.items()],
            )

    async def _probe_explorer_magellan_endpoints(self, dev) -> None:
        """Probe read-only Magellan endpoint variants when Explorer values are absent."""
        if dev.get("modelId") != EXPLORER_EVO_3_MODEL_ID:
            return

        missing = self._explorer_missing_capabilities(
            dev.get("capabilities", []),
            EXPLORER_EVO_3_REQUIRED_CAPABILITIES,
        )
        if not missing or not self._access_token:
            return

        now = datetime.now(UTC)
        if (
            self._last_explorer_magellan_probe_attempt is not None
            and now - self._last_explorer_magellan_probe_attempt
            < EXPLORER_EVO_3_MAGELLAN_PROBE_INTERVAL
        ):
            return
        self._last_explorer_magellan_probe_attempt = now

        setup_id = self._setup.get("id")
        gateway_id = dev.get("gatewayId")
        endpoint_templates = [
            ("setupviewv2", "/magellan/cozytouch/setupviewv2"),
            ("setupview", "/magellan/cozytouch/setupview"),
            ("setupviewv3", "/magellan/cozytouch/setupviewv3"),
            ("capabilities", "/magellan/capabilities/?deviceId={device_id}"),
            (
                "capabilities-op",
                "/magellan/capabilities/?deviceId={device_id}",
                {
                    "X-Operation-ID": (
                        "GacomaWcfService.CapabilitiesService.GetCapabilities"
                    )
                },
            ),
            ("devices", "/magellan/devices"),
            ("devices-slash", "/magellan/devices/"),
            (
                "devices-gateway-op",
                "/magellan/devices/?gatewayId={gateway_id}",
                {
                    "X-Operation-ID": (
                        "GacomaWcfService.DeviceService.GetAllLinkedToGatewayId"
                    )
                },
            ),
            ("device", "/magellan/devices/{device_id}"),
            ("device-capabilities", "/magellan/devices/{device_id}/capabilities"),
            (
                "device-details-op",
                "/magellan/devices/{device_id}/details",
                {
                    "X-Operation-ID": (
                        "GacomaWcfService.DeviceService.GetDeviceInformation"
                    )
                },
            ),
            ("zones", "/magellan/zones"),
            ("zones-slash", "/magellan/zones/"),
            (
                "zones-setup-op",
                "/magellan/zones/?setupId={setup_id}",
                {
                    "X-Operation-ID": (
                        "GacomaWcfService.ZoneService.GetZoneFromSetup"
                    )
                },
            ),
            ("gateways", "/magellan/gateways"),
            (
                "gateways-setup-op",
                "/magellan/gateways/?setupId={setup_id}",
                {
                    "X-Operation-ID": (
                        "GacomaWcfService.GatewayService.GetGateways"
                    )
                },
            ),
            ("gateway", "/magellan/gateways/{gateway_id}"),
            ("gateway-slash", "/magellan/gateways/{gateway_id}/"),
            (
                "gateway-details-op",
                "/magellan/gateways/{gateway_id}/details",
                {
                    "X-Operation-ID": (
                        "GacomaWcfService.GatewayService.GetGatewayDetails"
                    )
                },
            ),
            ("v2-gateway", "/magellan/v2/gateways/{gateway_id}"),
            ("v2-gateway-slash", "/magellan/v2/gateways/{gateway_id}/"),
            ("v2-gateways-slash", "/magellan/v2/gateways/"),
            ("v2-device", "/magellan/v2/devices/{device_id}"),
            (
                "v2-device-capabilities",
                "/magellan/v2/devices/{device_id}/capabilities",
            ),
            ("setup-v3", "/magellan/v3/setups/{setup_id}"),
            ("setup-v3-slash", "/magellan/v3/setups/{setup_id}/"),
            ("gateway-v3", "/magellan/v3/gateways/{gateway_id}"),
            ("gateway-v3-slash", "/magellan/v3/gateways/{gateway_id}/"),
            ("v3-gateways-slash", "/magellan/v3/gateways/"),
            ("setup-v2", "/magellan/v2/setups/{setup_id}"),
            ("setups", "/magellan/setups"),
            ("setup", "/magellan/setups/{setup_id}"),
        ]
        headers = {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        results = []
        for endpoint_definition in endpoint_templates:
            label = endpoint_definition[0]
            endpoint_template = endpoint_definition[1]
            extra_headers = (
                endpoint_definition[2] if len(endpoint_definition) > 2 else None
            )
            if "{setup_id}" in endpoint_template and setup_id is None:
                continue
            if "{gateway_id}" in endpoint_template and gateway_id is None:
                continue
            endpoint = endpoint_template.format(
                device_id=dev.get("deviceId"),
                setup_id=setup_id,
                gateway_id=gateway_id,
            )
            request_headers = dict(headers)
            if extra_headers is not None:
                request_headers.update(extra_headers)
            try:
                async with self._session.get(
                    COZYTOUCH_ATLANTIC_API + endpoint,
                    headers=request_headers,
                ) as response:
                    if response.status != 200:
                        details = await self._safe_response_error_details(response)
                        result = f"{label}=http-{response.status}"
                        if details:
                            result += f"({details})"
                        results.append(result)
                        continue
                    try:
                        payload = await response.json()
                    except ContentTypeError:
                        results.append(
                            f"{label}=not-json({response.headers.get('content-type')})"
                        )
                        continue
                    target = self._find_explorer_probe_target(
                        payload, dev.get("deviceId")
                    )
                    if (
                        gateway_id is None
                        and isinstance(target, dict)
                        and target.get("gatewayId") is not None
                    ):
                        gateway_id = target.get("gatewayId")
                    results.append(
                        f"{label}=ok "
                        + self._summarize_explorer_probe_payload(
                            payload, dev.get("deviceId")
                        )
                    )
            except Exception as err:
                results.append(f"{label}=error-{err.__class__.__name__}")

        self._log_explorer_magellan_probe_diagnostic(missing, results)

    def _summarize_explorer_probe_payload(self, payload, device_id) -> str:
        """Summarize endpoint payload without logging account/device identifiers."""
        target = self._find_explorer_probe_target(payload, device_id) or payload
        summary = self._payload_shape(target)

        capabilities = None
        if isinstance(target, list) and any(
            isinstance(item, dict) and "capabilityId" in item for item in target
        ):
            capabilities = target
        elif isinstance(target, dict) and isinstance(target.get("capabilities"), list):
            capabilities = target["capabilities"]

        if capabilities is not None:
            capability_summary = self._safe_probe_capability_summary(capabilities)
            return f"{summary} caps[{capability_summary}]"

        numeric_candidates = self._probe_numeric_candidates(target)
        if numeric_candidates:
            return f"{summary} values[{', '.join(numeric_candidates)}]"
        return summary

    def _find_explorer_probe_target(self, payload, device_id):
        """Return the matching device object from a setup-like payload."""
        candidates = [payload]
        if isinstance(payload, dict):
            candidates.extend(
                payload.get(key) for key in ("setup", "data", "result", "items")
            )

        for candidate in candidates:
            if isinstance(candidate, list):
                for item in candidate:
                    found = self._find_explorer_probe_target(item, device_id)
                    if found is not None:
                        return found
            elif isinstance(candidate, dict):
                if candidate.get("deviceId") == device_id:
                    return candidate
                devices = candidate.get("devices")
                if isinstance(devices, list):
                    for device in devices:
                        if isinstance(device, dict) and device.get("deviceId") == device_id:
                            return device
        return None

    def _safe_probe_capability_summary(self, capabilities) -> str:
        """Summarize capability values for endpoint comparison."""
        parts = []
        for capability in sorted(
            (item for item in capabilities or [] if isinstance(item, dict)),
            key=lambda item: str(item.get("capabilityId")),
        ):
            capability_id = capability.get("capabilityId")
            if capability_id in {88, 94, 98, 121, 219, 316, 335}:
                continue
            value = capability.get("value")
            if isinstance(value, (str, int, float, bool)) or value is None:
                value_text = repr(value)
            else:
                value_text = f"<{type(value).__name__}>"
            parts.append(f"{capability_id}={value_text[:50]}")
        return ", ".join(parts)[:900]

    def _probe_numeric_candidates(self, payload) -> list[str]:
        """Collect plausible numeric telemetry candidates from an unknown payload."""
        candidates = []
        self._collect_probe_numeric_candidates(payload, "$", candidates)
        return candidates[:40]

    def _collect_probe_numeric_candidates(self, payload, path: str, candidates) -> None:
        """Recursive worker for numeric probe summaries."""
        if len(candidates) >= 40:
            return

        if isinstance(payload, dict):
            if "capabilityId" in payload and "value" in payload:
                capability_id = payload.get("capabilityId")
                value = self._coerce_probe_numeric(payload.get("value"))
                if value is None and capability_id in EXPLORER_EVO_3_REQUIRED_CAPABILITIES:
                    candidates.append(f"cap{capability_id}=None")
                elif value is not None and -50 <= value <= 700:
                    candidates.append(
                        f"cap{capability_id}={self._format_probe_number(value)}"
                    )
            for key, value in payload.items():
                if key in {
                    "gatewaySerialNumber",
                    "name",
                    "productId",
                    "deviceId",
                    "id",
                    "address",
                }:
                    continue
                self._collect_probe_numeric_candidates(value, f"{path}.{key}", candidates)
                if len(candidates) >= 40:
                    return
        elif isinstance(payload, list):
            for index, item in enumerate(payload[:80]):
                self._collect_probe_numeric_candidates(item, f"{path}[{index}]", candidates)
                if len(candidates) >= 40:
                    return
        else:
            value = self._coerce_probe_numeric(payload)
            if value is not None and -50 <= value <= 700:
                lowered_path = path.lower()
                if any(
                    token in lowered_path
                    for token in (
                        "temp",
                        "water",
                        "tank",
                        "v40",
                        "dhw",
                        "capacity",
                        "value",
                        "state",
                    )
                ):
                    candidates.append(
                        f"{path}={self._format_probe_number(value)}"
                    )

    def _coerce_probe_numeric(self, value):
        """Coerce safe numeric probe values."""
        if value is None or isinstance(value, bool):
            return None
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            text = value.strip()
            if not text or len(text) > 20:
                return None
            try:
                return float(text)
            except ValueError:
                return None
        return None

    def _format_probe_number(self, value: float) -> str:
        """Format a numeric probe value compactly."""
        if abs(value - round(value)) < 0.000001:
            return str(int(round(value)))
        return f"{value:.3f}".rstrip("0").rstrip(".")

    def _log_explorer_magellan_probe_diagnostic(self, missing, results) -> None:
        """Log Magellan endpoint probe results once per result set."""
        diagnostic_key = (tuple(missing), tuple(results))
        if diagnostic_key in self._explorer_magellan_probe_diagnostics_seen:
            return
        self._explorer_magellan_probe_diagnostics_seen.add(diagnostic_key)
        _LOGGER.warning(
            "Explorer EVO 3 Magellan read-only probe build 1.5.4 missing "
            "capabilities %s: %s",
            missing,
            "; ".join(results)[:9000],
        )

    async def _fetch_overkiz_setup(self):
        """Fetch the read-only Overkiz setup using the Atlantic account token."""
        if not self._access_token:
            return None

        setup = await self._fetch_overkiz_setup_with_token(
            self._access_token, "primary"
        )
        if setup is not None:
            return setup

        legacy_access_token = await self._fetch_legacy_overkiz_access_token()
        if legacy_access_token:
            return await self._fetch_overkiz_setup_with_token(
                legacy_access_token, "legacy"
            )

        return None

    async def _fetch_overkiz_setup_with_token(self, access_token: str, source: str):
        """Fetch the read-only Overkiz setup using a given Atlantic token."""
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        async with self._session.get(
            COZYTOUCH_ATLANTIC_API + "/magellan/accounts/jwt",
            headers=headers,
        ) as response:
            if response.status != 200:
                self._log_explorer_overkiz_fallback_diagnostic(
                    f"{source}-jwt-http-{response.status}", []
                )
                return None
            jwt = self._parse_overkiz_jwt(await response.text())

        if not jwt:
            self._log_explorer_overkiz_fallback_diagnostic(
                f"{source}-jwt-empty", []
            )
            return None

        jwt_summary = self._safe_jwt_principal_summary(jwt)
        if jwt_summary:
            self._log_explorer_overkiz_fallback_diagnostic(
                f"{source}-jwt-{jwt_summary}", []
            )

        if not await self._login_overkiz_with_jwt(jwt, source):
            return None

        async with self._session.get(
            OVERKIZ_ENDUSER_API + "/setup",
            headers={"Content-Type": "application/json"},
        ) as response:
            if response.status != 200:
                self._log_explorer_overkiz_fallback_diagnostic(
                    f"{source}-setup-http-{response.status}", []
                )
                return None
            try:
                return await response.json()
            except ContentTypeError:
                self._log_explorer_overkiz_fallback_diagnostic(
                    f"{source}-setup-not-json", []
                )
                return None

    async def _login_overkiz_with_jwt(self, jwt: str, source: str) -> bool:
        """Try known Overkiz JWT login payload formats."""
        attempts = (
            (
                "form",
                {
                    "data": FormData({"jwt": jwt}),
                    "headers": {"Content-Type": "application/x-www-form-urlencoded"},
                },
            ),
            (
                "json",
                {
                    "json": {"jwt": jwt},
                    "headers": {"Content-Type": "application/json"},
                },
            ),
        )
        for label, kwargs in attempts:
            async with self._session.post(
                OVERKIZ_ENDUSER_API + "/login",
                **kwargs,
            ) as response:
                if 200 <= response.status < 300:
                    self._log_explorer_overkiz_fallback_diagnostic(
                        f"{source}-login-{label}-ok", []
                    )
                    return True
                details = await self._safe_response_error_details(response)
                self._log_explorer_overkiz_fallback_diagnostic(
                    f"{source}-login-{label}-http-{response.status}",
                    [details] if details else [],
                )
        return False

    async def _fetch_legacy_overkiz_access_token(self):
        """Fetch the legacy Atlantic token used by public Overkiz scripts."""
        async with self._session.post(
            COZYTOUCH_ATLANTIC_API + "/token",
            data=FormData(
                {
                    "grant_type": "password",
                    "scope": self._cozytouch_token_scope(),
                    "username": "GA-PRIVATEPERSON/" + self._username,
                    "password": self._password,
                }
            ),
            headers={
                "Authorization": f"Basic {COZYTOUCH_OVERKIZ_CLIENT_ID}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
        ) as response:
            if response.status != 200:
                self._log_explorer_overkiz_fallback_diagnostic(
                    f"legacy-token-http-{response.status}", []
                )
                return None
            try:
                token = await response.json()
            except ContentTypeError:
                self._log_explorer_overkiz_fallback_diagnostic(
                    "legacy-token-not-json", []
                )
                return None

        access_token = token.get("access_token") if isinstance(token, dict) else None
        if not access_token:
            self._log_explorer_overkiz_fallback_diagnostic(
                "legacy-token-missing-access-token", []
            )
            return None

        return access_token

    def _parse_overkiz_jwt(self, payload: str):
        """Extract a JWT from known Atlantic response shapes."""
        text = payload.strip()
        if not text:
            return None

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return text.strip('"')

        if isinstance(parsed, str):
            return parsed
        if isinstance(parsed, dict):
            for key in ("jwt", "token", "access_token", "id_token"):
                value = parsed.get(key)
                if isinstance(value, str) and value:
                    return value
        return None

    def _safe_jwt_principal_summary(self, jwt: str):
        """Return a non-identifying summary of the JWT principal class."""
        parts = jwt.split(".")
        if len(parts) < 2:
            return None
        payload = parts[1]
        payload += "=" * (-len(payload) % 4)
        try:
            decoded = base64.urlsafe_b64decode(payload.encode("ascii"))
            claims = json.loads(decoded.decode("utf-8"))
        except (ValueError, json.JSONDecodeError, UnicodeDecodeError):
            return None
        if not isinstance(claims, dict):
            return None

        for key in ("sub", "username", "user_name", "preferred_username"):
            value = claims.get(key)
            if not isinstance(value, str) or not value:
                continue
            if value.startswith("GACOMA_Production_"):
                return "subject-class-GACOMA_Production"
            if value.startswith("GA-PRIVATEPERSON/"):
                return "subject-class-GA-PRIVATEPERSON"
            if "@" in value:
                return "subject-class-email"
            return "subject-class-other"
        return None

    def _extract_explorer_overkiz_temperature_values(self, overkiz_setup):
        """Return supported temperature states from the best Overkiz device match."""
        devices = []
        if isinstance(overkiz_setup, dict):
            devices = overkiz_setup.get("devices", [])
        elif isinstance(overkiz_setup, list):
            devices = overkiz_setup

        best_values = {}
        best_score = 0
        for device in devices or []:
            if not isinstance(device, dict):
                continue
            states = device.get("states", [])
            if not isinstance(states, list):
                continue

            values = {}
            for state in states:
                if not isinstance(state, dict):
                    continue
                state_name = state.get("name")
                if state_name not in EXPLORER_EVO_3_OVERKIZ_STATE_TO_CAPABILITY:
                    continue
                value = self._coerce_overkiz_temperature_value(state.get("value"))
                if value is not None:
                    values[state_name] = value

            if len(values) > best_score:
                best_values = values
                best_score = len(values)

        return best_values

    def _coerce_overkiz_temperature_value(self, value):
        """Coerce a numeric Overkiz temperature state value."""
        if value is None or isinstance(value, bool):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    def _log_explorer_overkiz_fallback_diagnostic(self, status: str, details) -> None:
        """Log Overkiz fallback status without account or device identifiers."""
        diagnostic_key = (status, tuple(details))
        if diagnostic_key in self._explorer_overkiz_fallback_diagnostics_seen:
            return
        self._explorer_overkiz_fallback_diagnostics_seen.add(diagnostic_key)
        _LOGGER.warning(
            "Explorer EVO 3 Overkiz temperature fallback build 1.5.4 %s: %s",
            status,
            ", ".join(details) if details else "no details",
        )

    async def _safe_response_error_details(self, response) -> str | None:
        """Return sanitized error response details for API diagnostics."""
        try:
            text = await response.text()
        except Exception:
            return None
        return self._redact_error_text(text)

    def _redact_error_text(self, text: str) -> str | None:
        """Remove account identifiers from an API error body."""
        if not text:
            return None
        redacted = text.replace(self._username, "<username>")
        redacted = re.sub(
            r"GA-PRIVATEPERSON/[^\s\"']+",
            "GA-PRIVATEPERSON/<redacted>",
            redacted,
        )
        redacted = re.sub(
            r"GACOMA_Production_[A-Za-z0-9._-]+",
            "GACOMA_Production_<redacted>",
            redacted,
        )
        redacted = re.sub(
            r"[A-Za-z0-9_.+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+",
            "<email>",
            redacted,
        )
        redacted = " ".join(redacted.split())
        return redacted[:240] if redacted else None

    def _log_explorer_capability_diagnostic(self, capabilities, model_id: int) -> None:
        """Log Explorer payload details once when expected telemetry is absent."""
        if model_id != EXPLORER_EVO_3_MODEL_ID:
            return

        by_id = {
            capability.get("capabilityId"): capability
            for capability in capabilities or []
            if isinstance(capability, dict)
        }
        missing = [
            capability_id
            for capability_id in EXPLORER_EVO_3_REQUIRED_CAPABILITIES
            if by_id.get(capability_id, {}).get("value") is None
        ]
        if not missing:
            self._last_explorer_capability_diagnostic = None
            return

        summary = self._safe_capability_summary(capabilities)
        diagnostic_key = (tuple(missing), summary)
        if diagnostic_key == self._last_explorer_capability_diagnostic:
            return
        self._last_explorer_capability_diagnostic = diagnostic_key

        _LOGGER.warning(
            "Explorer EVO 3 telemetry missing values for capabilities %s; "
            "current Cozytouch payload capabilities: %s",
            missing,
            summary,
        )

    def _safe_capability_summary(self, capabilities) -> str:
        """Summarize capability IDs and non-sensitive values for diagnostics."""
        redacted_ids = {
            88,  # model name
            94,  # product number
            98,  # product number
            121,  # firmware/version
            219,  # Wi-Fi SSID
            316,  # interface firmware
            335,  # serial number
        }
        parts = []
        for capability in sorted(
            (item for item in capabilities or [] if isinstance(item, dict)),
            key=lambda item: str(item.get("capabilityId")),
        ):
            capability_id = capability.get("capabilityId")
            value = capability.get("value")
            if capability_id in redacted_ids:
                value_text = "<redacted>"
            elif isinstance(value, (str, int, float, bool)) or value is None:
                value_text = repr(value)
            else:
                value_text = f"<{type(value).__name__}>"
            parts.append(f"{capability_id}={value_text[:80]}")
        return ", ".join(parts)

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
                    if capabilities_data is None:
                        _LOGGER.warning(
                            "Cozytouch capabilities payload for device %s did not "
                            "contain capabilities; forcing reconnect",
                            self._deviceId,
                        )
                        self.online = False
                        await self.connect()
                        return

                    for dev in self._devices:
                        if dev["deviceId"] == self._deviceId:
                            dev["capabilities"] = self._merge_capabilities(
                                dev.get("capabilities", []),
                                capabilities_data,
                                dev.get("modelId"),
                            )
                            await self._probe_explorer_magellan_endpoints(dev)
                            await self._apply_explorer_overkiz_temperature_fallback(
                                dev
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
