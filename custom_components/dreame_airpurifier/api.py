"""AirPursue PM10 Cloud API Client — fully async with data-driven property registry."""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Any, Callable

import aiohttp

from .const import MODE_AUTO, MODE_NAMES, SWIVEL_OPTIONS

_LOGGER = logging.getLogger(__name__)

DREAME_SALT = "RAylYC%fmSKp7%Tq"
DREAME_USER_AGENT = "Dreame_Smarthome/2.1.9 (iPhone; iOS 18.4.1; Scale/3.00)"
DREAME_AUTH_BASIC = "Basic ZHJlYW1lX2FwcHYxOkFQXmR2QHpAU1FZVnhOODg="
DREAME_TENANT_ID = "000000"
DREAME_RLC = "1c80b3787b2266776bcdc481f37d8fa42ba10a30af81a6df-1"

_TIMEOUT = aiohttp.ClientTimeout(total=10)

# ── Data-driven MiOT property registry ─────────────────────────────────


@dataclass(frozen=True, slots=True)
class PropDef:
    """Single MiOT property: maps (siid, piid) → named attribute on DreameAirPurifier."""

    attr: str
    siid: int
    piid: int
    default: Any = 0
    coerce: Callable[[Any], Any] | None = None


PROP_DEFS: tuple[PropDef, ...] = (
    # siid 2 — Control
    PropDef("power",                2,  1, 0),
    PropDef("mode_value",           2,  3, MODE_AUTO),
    PropDef("fan_speed",            2,  4, 0),
    PropDef("swivel",               2,  7, 0),
    PropDef("auto_fan_raw",         2,  8, 0),
    PropDef("continuous_monitoring", 2, 10, False, bool),
    # siid 3 — Sensors
    PropDef("humidity",             3,  2, 0),
    PropDef("temperature",          3,  3, 0),
    PropDef("air_quality_level",    3,  4, 0),
    PropDef("pm25",                 3,  5, 0),
    PropDef("pm10_value",           3,  6, 0),
    PropDef("hcho",                 3,  7, 0),
    PropDef("tvoc",                 3,  8, 0),
    PropDef("pm1",                  3, 10, 0),
    PropDef("aq_percent",           3, 12, 0, lambda v: max(0, min(100, 100 - int(v)))),
    # siid 4 — HEPA filter
    PropDef("hepa_life",            4,  1, 0),
    PropDef("hepa_days_total",      4,  2, 720),
    PropDef("hepa_hours_used",      4,  3, 0),
    # siid 5 — Carbon filter
    PropDef("carbon_life",          5,  1, 0),
    PropDef("carbon_days_total",    5,  2, 360),
    PropDef("carbon_hours_used",    5,  3, 0),
    # siid 6 — Settings
    PropDef("temp_unit",            6,  4, 0),
    PropDef("human_sensing",        6,  5, False, bool),
    PropDef("follow_mode",          6,  6, False, bool),
    PropDef("voice_assistant",      6,  7, False, bool),
    PropDef("timer",                6,  8, 0),
)

# Pre-compute poll batches (≤15 props per request)
_BATCH_SIZE = 15
_POLL_BATCHES: tuple[tuple[PropDef, ...], ...] = tuple(
    tuple(PROP_DEFS[i : i + _BATCH_SIZE])
    for i in range(0, len(PROP_DEFS), _BATCH_SIZE)
)

ACTION_TOGGLE_POWER = (2, 3)  # (siid, aiid)


# ── Cloud API ──────────────────────────────────────────────────────────


class DreameCloudAPI:
    """Async client for the Dreame Cloud API using aiohttp."""

    __slots__ = (
        "_session", "_username", "_password", "_country",
        "_access_token", "_refresh_token", "_uid", "_tenant_id", "_token_expire",
    )

    def __init__(self, session: aiohttp.ClientSession, username: str, password: str, country: str = "us"):
        self._session = session
        self._username = username
        self._password = password
        self._country = country
        self._access_token: str | None = None
        self._refresh_token: str | None = None
        self._uid: str | None = None
        self._tenant_id = DREAME_TENANT_ID
        self._token_expire: float | None = None

    @property
    def api_url(self) -> str:
        return f"https://{self._country}.iot.dreame.tech:13267"

    @property
    def logged_in(self) -> bool:
        return self._access_token is not None

    # ── Auth ────────────────────────────────────────────────────────────

    async def login(self) -> bool:
        url = f"{self.api_url}/dreame-auth/oauth/token"
        pw_hash = hashlib.md5((self._password + DREAME_SALT).encode()).hexdigest()
        data = (
            f"platform=IOS&scope=all&grant_type=password"
            f"&username={self._username}&password={pw_hash}&type=account"
        )
        headers = {
            "User-Agent": DREAME_USER_AGENT,
            "Authorization": DREAME_AUTH_BASIC,
            "Tenant-Id": DREAME_TENANT_ID,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "*/*",
        }
        if self._country == "cn":
            headers["Dreame-Rlc"] = DREAME_RLC
        try:
            async with self._session.post(url, headers=headers, data=data, timeout=_TIMEOUT) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    if "access_token" in result:
                        self._access_token = result["access_token"]
                        self._refresh_token = result.get("refresh_token")
                        self._uid = result.get("uid")
                        self._tenant_id = result.get("tenant_id", DREAME_TENANT_ID)
                        self._token_expire = time.time() + result.get("expires_in", 3600) - 300
                        return True
                    _LOGGER.error("Login failed: %s", result)
                else:
                    body = await resp.text()
                    _LOGGER.error("Login HTTP %s: %s", resp.status, body)
        except (aiohttp.ClientError, TimeoutError) as ex:
            _LOGGER.error("Login error: %s", ex)
        return False

    async def _ensure_token(self) -> bool:
        if not self._refresh_token or not self._token_expire or time.time() <= self._token_expire:
            return True
        url = f"{self.api_url}/dreame-auth/oauth/token"
        data = f"platform=IOS&scope=all&grant_type=refresh_token&refresh_token={self._refresh_token}"
        headers = {
            "User-Agent": DREAME_USER_AGENT,
            "Authorization": DREAME_AUTH_BASIC,
            "Tenant-Id": self._tenant_id,
            "Content-Type": "application/x-www-form-urlencoded",
        }
        try:
            async with self._session.post(url, headers=headers, data=data, timeout=_TIMEOUT) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    if "access_token" in result:
                        self._access_token = result["access_token"]
                        self._refresh_token = result.get("refresh_token", self._refresh_token)
                        self._token_expire = time.time() + result.get("expires_in", 3600) - 300
                        return True
        except (aiohttp.ClientError, TimeoutError) as ex:
            _LOGGER.warning("Token refresh failed: %s", ex)
        return await self.login()

    def _auth_headers(self) -> dict[str, str]:
        return {
            "User-Agent": DREAME_USER_AGENT,
            "Authorization": DREAME_AUTH_BASIC,
            "Tenant-Id": self._tenant_id,
            "Dreame-Auth": self._access_token,
            "Content-Type": "application/json",
            "Accept": "*/*",
        }

    # ── Transport ───────────────────────────────────────────────────────

    async def send_command(self, did: str, method: str, params: Any, host: str | None = None) -> Any:
        if not await self._ensure_token():
            return None
        host_prefix = f"-{host.split('.')[0]}" if host else ""
        url = f"{self.api_url}/dreame-iot-com{host_prefix}/device/sendCommand"
        payload = {"did": did, "id": 1, "data": {"did": did, "id": 1, "method": method, "params": params}}
        try:
            async with self._session.post(url, headers=self._auth_headers(), json=payload, timeout=_TIMEOUT) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    if result.get("code") == 0:
                        data = result.get("data")
                        if data and "result" in data:
                            return data["result"]
                        if result.get("success"):
                            return {"code": 0}
                elif resp.status == 401:
                    if await self.login():
                        return await self.send_command(did, method, params, host)
        except (aiohttp.ClientError, TimeoutError) as ex:
            _LOGGER.error("Command failed: %s", ex)
        return None

    # ── High-level operations ───────────────────────────────────────────

    async def get_properties(self, did: str, prop_defs: tuple[PropDef, ...], host: str | None = None) -> dict[tuple[int, int], Any]:
        params = [{"did": did, "siid": p.siid, "piid": p.piid} for p in prop_defs]
        result = await self.send_command(did, "get_properties", params, host)
        values: dict[tuple[int, int], Any] = {}
        if result and isinstance(result, list):
            for prop in result:
                if prop.get("code", -1) == 0:
                    values[(prop["siid"], prop["piid"])] = prop.get("value")
        return values

    async def set_property(self, did: str, siid: int, piid: int, value: Any, host: str | None = None) -> bool:
        params = [{"did": did, "siid": siid, "piid": piid, "value": value}]
        result = await self.send_command(did, "set_properties", params, host)
        return bool(result and isinstance(result, list) and result and result[0].get("code", -1) == 0)

    async def call_action(self, did: str, siid: int, aiid: int, params: list | None = None, host: str | None = None) -> bool:
        payload = {"did": did, "siid": siid, "aiid": aiid, "in": params or []}
        result = await self.send_command(did, "action", payload, host)
        if result:
            return result.get("code", -1) == 0 if isinstance(result, dict) else True
        return False

    async def get_devices(self) -> list | None:
        if not await self._ensure_token():
            return None
        url = f"{self.api_url}/dreame-user-iot/iotuserbind/device/listV2"
        try:
            async with self._session.post(url, headers=self._auth_headers(), json={}, timeout=_TIMEOUT) as resp:
                if resp.status == 200:
                    result = await resp.json()
                    if result.get("code") == 0 and "data" in result:
                        return result["data"]["page"]["records"]
        except (aiohttp.ClientError, TimeoutError) as ex:
            _LOGGER.error("Failed to get devices: %s", ex)
        return None

    async def get_purifiers(self) -> list:
        devices = await self.get_devices()
        if not devices:
            return []
        return [d for d in devices if ".airp." in d.get("model", "")]


# ── Device model ───────────────────────────────────────────────────────


class DreameAirPurifier:
    """AirPursue PM10 device backed by a data-driven property registry.

    All properties defined in PROP_DEFS are accessible as attributes via __getattr__.
    Derived properties (is_on, mode, fan_speed_percent, auto_fan) are explicit.
    """

    __slots__ = ("_api", "_did", "_host", "_model", "_mac", "_name", "_state", "_available")

    def __init__(self, api: DreameCloudAPI, device_info: dict):
        self._api = api
        self._did = str(device_info["did"])
        self._host: str | None = device_info.get("bindDomain")
        self._model: str = device_info.get("model", "unknown")
        self._mac: str = device_info.get("mac", "")
        self._name: str = (
            device_info.get("customName")
            or device_info.get("deviceInfo", {}).get("displayName", "AirPursue PM10")
        )
        self._state: dict[str, Any] = {p.attr: p.default for p in PROP_DEFS}
        self._available = True

    def __getattr__(self, name: str) -> Any:
        """Fall-through to _state dict for registry-managed attributes."""
        try:
            return self._state[name]
        except KeyError:
            raise AttributeError(f"'{type(self).__name__}' has no attribute '{name}'") from None

    # ── Identity ────────────────────────────────────────────────────────

    @property
    def unique_id(self) -> str:
        return self._mac.replace(":", "").lower()

    @property
    def name(self) -> str:
        return self._name

    @property
    def model(self) -> str:
        return self._model

    @property
    def device_id(self) -> str:
        return self._did

    @property
    def mac(self) -> str:
        return self._mac

    @property
    def available(self) -> bool:
        return self._available

    # ── Derived properties ──────────────────────────────────────────────

    @property
    def is_on(self) -> bool:
        return self._state["power"] == 1

    @property
    def mode(self) -> str:
        v = self._state["mode_value"]
        return MODE_NAMES.get(v, f"Unknown ({v})")

    @property
    def fan_speed_percent(self) -> int:
        return self._state["fan_speed"] * 10

    @property
    def auto_fan(self) -> bool:
        return self._state["auto_fan_raw"] == 0

    # ── Polling ─────────────────────────────────────────────────────────

    async def update(self) -> bool:
        all_values: dict[tuple[int, int], Any] = {}
        for batch in _POLL_BATCHES:
            values = await self._api.get_properties(self._did, batch, self._host)
            if values:
                all_values.update(values)
        if not all_values:
            self._available = False
            return False
        self._available = True
        for p in PROP_DEFS:
            raw = all_values.get((p.siid, p.piid), p.default)
            if raw is None:
                raw = p.default
            self._state[p.attr] = p.coerce(raw) if p.coerce else raw
        return True

    # ── Commands ────────────────────────────────────────────────────────

    async def toggle_power(self) -> bool:
        return await self._api.call_action(self._did, *ACTION_TOGGLE_POWER, host=self._host)

    async def turn_on(self, mode: int = MODE_AUTO) -> bool:
        if not self.is_on:
            await self.toggle_power()
        return await self.set_mode(mode)

    async def turn_off(self) -> bool:
        return await self.toggle_power() if self.is_on else True

    async def set_mode(self, mode: int) -> bool:
        return await self._api.set_property(self._did, 2, 3, mode, self._host)

    async def set_fan_speed(self, speed: int) -> bool:
        return await self._api.set_property(self._did, 2, 4, max(1, min(10, speed)), self._host)

    async def set_swivel(self, angle: int) -> bool:
        if angle not in SWIVEL_OPTIONS:
            return False
        return await self._api.set_property(self._did, 2, 7, angle, self._host)

    async def set_continuous_monitoring(self, enabled: bool) -> bool:
        return await self._api.set_property(self._did, 2, 10, int(enabled), self._host)

    async def set_human_sensing(self, enabled: bool) -> bool:
        return await self._api.set_property(self._did, 6, 5, int(enabled), self._host)

    async def set_follow_mode(self, enabled: bool) -> bool:
        return await self._api.set_property(self._did, 6, 6, int(enabled), self._host)

    async def set_voice_assistant(self, enabled: bool) -> bool:
        return await self._api.set_property(self._did, 6, 7, int(enabled), self._host)

    async def set_temp_unit(self, unit: int) -> bool:
        return await self._api.set_property(self._did, 6, 4, unit, self._host)

    async def set_timer(self, hours: int) -> bool:
        return await self._api.set_property(self._did, 6, 8, hours, self._host)

    async def reset_hepa_filter(self) -> bool:
        return await self._api.call_action(self._did, 4, 1, host=self._host)

    async def reset_carbon_filter(self) -> bool:
        return await self._api.call_action(self._did, 5, 1, host=self._host)
