"""Dreame air purifier Cloud API Client — fully async with data-driven property registry."""
from __future__ import annotations

import hashlib
import itertools
import logging
import random
import time
from dataclasses import dataclass
from typing import Any, Callable

import aiohttp

from .const import MODE_AUTO, SWIVEL_OPTIONS, UNSAFE_ACTIONS, UNSAFE_PROPS, ModelProfile, profile_for

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

# TP20 (dreame.airp.u2630). Mapped by watching the device while using the app and by
# single reads/writes. Reading 3.10 crashes it (see UNSAFE_PROPS); 2.1 power is
# read-only (written with -4002), so power goes through the toggle action.
TP20_PROP_DEFS: tuple[PropDef, ...] = (
    PropDef("power",                2,  1, 0),
    PropDef("mode_value",           2,  3, 0),
    PropDef("fan_speed",            2,  4, 0),
    PropDef("fan_level",            2, 10, 0),   # mirrors fan_speed; read-only
    PropDef("air_quality_level",    3,  4, 0),
    PropDef("pm25",                 3,  5, 0),
    # 3.12 is left out: it rises with pollution (~70-84, 0 when off), but the app
    # doesn't show it, so there's nothing to check a "%" reading against.
    PropDef("hepa_life",            4,  1, 0),
    PropDef("hepa_days_left",       4,  2, 0),   # days of filter life left (filters last 5 years)
    PropDef("temp_unit",            6,  4, 0),
    PropDef("timer",                6,  8, 0),
    PropDef("child_lock",           6, 10, False, bool),
    PropDef("continuous_monitoring", 6, 15, False, bool),  # measures air quality while off
)

# Models whose properties differ from the PM10 map above.
MODEL_PROP_DEFS: dict[str, tuple[PropDef, ...]] = {
    "dreame.airp.u2630": TP20_PROP_DEFS,
}

# Pre-compute poll batches (≤15 props per request)
_BATCH_SIZE = 15


def _batches(defs: tuple[PropDef, ...]) -> tuple[tuple[PropDef, ...], ...]:
    return tuple(defs[i : i + _BATCH_SIZE] for i in range(0, len(defs), _BATCH_SIZE))


# Every request gets its own id. With a fixed id, replies got mixed up when another
# client (the app, a tool) talked to the device at the same time.
_request_ids = itertools.count(random.randint(1000, 1_000_000))


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
        req_id = next(_request_ids)
        payload = {"did": did, "id": req_id, "data": {"did": did, "id": req_id, "method": method, "params": params}}
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

    async def get_properties(self, did: str, prop_defs: tuple[PropDef, ...], host: str | None = None) -> dict[tuple[int, int], Any] | None:
        """Read properties. Returns None if the request itself failed, so callers can
        tell a failed request apart from a device that doesn't have these properties."""
        params = [{"did": did, "siid": p.siid, "piid": p.piid} for p in prop_defs]
        result = await self.send_command(did, "get_properties", params, host)
        if not isinstance(result, list):
            return None
        wanted = {(p.siid, p.piid) for p in prop_defs}
        values: dict[tuple[int, int], Any] = {}
        for prop in result:
            key = (prop.get("siid"), prop.get("piid"))
            if key not in wanted:
                # A reply meant for another request. Treat this request as failed rather
                # than as "device has none of these", which would hide their entities.
                _LOGGER.debug("Reply contained unrequested property %s; treating request as failed", key)
                return None
            if prop.get("code", -1) == 0:
                values[key] = prop.get("value")
        return values

    async def set_property(self, did: str, siid: int, piid: int, value: Any, host: str | None = None) -> bool:
        params = [{"did": did, "siid": siid, "piid": piid, "value": value}]
        result = await self.send_command(did, "set_properties", params, host)
        if isinstance(result, dict) and result.get("code") == 0:
            # The cloud accepted it but the device didn't echo a per-property result
            # (seen on the TP20, and the write did take effect). The integration only
            # writes properties the model has, so treat it as accepted.
            return True
        if not (isinstance(result, list) and result):
            return False
        first = result[0]
        if (first.get("siid"), first.get("piid")) != (siid, piid):
            return False
        if first.get("code", -1) != 0:
            _LOGGER.warning("Device rejected setting %s.%s = %r (code %s)", siid, piid, value, first.get("code"))
            return False
        return True

    async def call_action(self, did: str, siid: int, aiid: int, params: list | None = None, host: str | None = None) -> bool:
        payload = {"did": did, "siid": siid, "aiid": aiid, "in": params or []}
        result = await self.send_command(did, "action", payload, host)
        if not isinstance(result, dict):
            return False
        if "aiid" in result and (result.get("siid"), result.get("aiid")) != (siid, aiid):
            return False
        return result.get("code", -1) == 0

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
    """Dreame air purifier backed by a data-driven property registry.

    Properties from the model's PropDef table (PROP_DEFS, or MODEL_PROP_DEFS for other
    models) are accessible as attributes via __getattr__. Derived properties (is_on,
    mode, fan_speed_percent) are explicit; control behaviour comes from the model profile.
    """

    __slots__ = ("_api", "_did", "_host", "_model", "_mac", "_name", "_state", "_available", "_supported", "_detected", "_partial", "_raw", "_poll_defs", "_skipped", "_defs", "_profile")

    def __init__(self, api: DreameCloudAPI, device_info: dict):
        self._api = api
        self._did = str(device_info["did"])
        self._host: str | None = device_info.get("bindDomain")
        self._model: str = device_info.get("model", "unknown")
        self._mac: str = device_info.get("mac", "")
        self._name: str = (
            device_info.get("customName")
            or device_info.get("deviceInfo", {}).get("displayName", "Dreame Air Purifier")
        )
        self._defs: tuple[PropDef, ...] = MODEL_PROP_DEFS.get(self._model, PROP_DEFS)
        self._profile: ModelProfile = profile_for(self._model)
        self._state: dict[str, Any] = {p.attr: p.default for p in self._defs}
        self._available = True
        # Attributes the device has actually reported (code 0, non-null value).
        # Used to skip creating entities for properties a model doesn't have.
        self._supported: set[str] = set()
        # True once a poll has completed with every batch answering, i.e. the
        # supported set is trustworthy enough to decide which entities to create.
        self._detected = False
        # True if the last poll before detection got only some batches back.
        self._partial = False
        # Last raw value seen per (siid, piid), for diagnostics.
        self._raw: dict[tuple[int, int], Any] = {}
        # Properties to poll. Starts as everything except reads known to crash
        # this model; narrowed to what the device supports once detected.
        unsafe = UNSAFE_PROPS.get(self._model, frozenset())
        self._poll_defs: tuple[PropDef, ...] = tuple(p for p in self._defs if (p.siid, p.piid) not in unsafe)
        self._skipped: list[str] = sorted(p.attr for p in self._defs if (p.siid, p.piid) in unsafe)

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

    @property
    def profile(self) -> ModelProfile:
        return self._profile

    # ── Derived properties ──────────────────────────────────────────────

    @property
    def is_on(self) -> bool:
        return self._state["power"] == 1

    @property
    def mode(self) -> str:
        v = self._state.get("mode_value")
        return self._profile.modes.get(v, f"Unknown ({v})")

    @property
    def fan_speed_percent(self) -> int:
        return round(self._state.get("fan_speed", 0) * 100 / self._profile.speed_count)

    @property
    def auto_fan(self) -> bool:
        return self._state.get("auto_fan_raw", 0) == 0

    def supports(self, attr: str) -> bool:
        """True if the device has reported a value for this registry attribute."""
        return attr in self._supported

    @property
    def detection_incomplete(self) -> bool:
        """True if the device answered but some poll batches failed before detection."""
        return not self._detected and self._partial

    @property
    def supported_attrs(self) -> list[str]:
        return sorted(self._supported)

    @property
    def unsupported_attrs(self) -> list[str]:
        return sorted(p.attr for p in self._defs if p.attr not in self._supported)

    @property
    def skipped_attrs(self) -> list[str]:
        """Attributes never read on this model because reading them is unsafe."""
        return list(self._skipped)

    @property
    def raw_properties(self) -> dict[str, Any]:
        """Last raw value per property, keyed "siid.piid"."""
        return {f"{s}.{pi}": v for (s, pi), v in sorted(self._raw.items())}

    # ── Polling ─────────────────────────────────────────────────────────

    async def update(self) -> bool:
        all_values: dict[tuple[int, int], Any] = {}
        failed = False
        for batch in _batches(self._poll_defs):
            values = await self._api.get_properties(self._did, batch, self._host)
            if values is None:
                failed = True
            else:
                all_values.update(values)
        if not all_values:
            self._available = False
            return False
        if failed and not self._detected:
            # A failed batch would look like "device lacks these properties" and
            # permanently hide their entities, so don't trust a partial first poll.
            self._partial = True
            self._available = False
            _LOGGER.warning("%s: partial response while detecting properties, will retry", self._name)
            return False
        self._partial = False
        self._available = True
        self._raw.update(all_values)
        for p in self._defs:
            raw = all_values.get((p.siid, p.piid))
            if raw is not None:
                self._supported.add(p.attr)
                self._state[p.attr] = p.coerce(raw) if p.coerce else raw
            elif p.attr not in self._supported:
                self._state[p.attr] = p.coerce(p.default) if p.coerce else p.default
            # else: supported but missing this poll (e.g. a batch failed) -> keep last value
        if not self._detected:
            self._detected = True
            # From now on only ask for what the device has: fewer, smaller requests.
            self._poll_defs = tuple(p for p in self._poll_defs if p.attr in self._supported)
            _LOGGER.info(
                "%s (%s) reported properties: %s; not reported: %s; skipped as unsafe: %s",
                self._name, self._model, self.raw_properties, self.unsupported_attrs, self._skipped,
            )
        return True

    # ── Commands ────────────────────────────────────────────────────────

    def _def(self, attr: str) -> PropDef | None:
        return next((p for p in self._defs if p.attr == attr), None)

    async def _set_attr(self, attr: str, value: Any) -> bool:
        """Write a property by name, using this model's own property numbers."""
        p = self._def(attr)
        if p is None:
            _LOGGER.warning("%s (%s) has no %s property; not writing", self._name, self._model, attr)
            return False
        return await self._api.set_property(self._did, p.siid, p.piid, value, self._host)

    async def refresh_power(self) -> None:
        """Read power right before toggling, so a stale poll can't flip it the wrong way."""
        p = self._def("power")
        if p is None:
            return
        values = await self._api.get_properties(self._did, (p,), self._host)
        if values and (p.siid, p.piid) in values:
            self._state["power"] = values[(p.siid, p.piid)]

    @property
    def can_switch_power(self) -> bool:
        return self._profile.power_action is not None

    async def _call_action(self, siid: int, aiid: int) -> bool:
        """Call an action, refusing any known to crash this model."""
        if (siid, aiid) in UNSAFE_ACTIONS.get(self._model, frozenset()):
            _LOGGER.error("%s: action %s/%s is known to crash %s; not sending it", self._name, siid, aiid, self._model)
            return False
        return await self._api.call_action(self._did, siid, aiid, host=self._host)

    async def toggle_power(self) -> bool:
        if self._profile.power_action is None:
            _LOGGER.warning("%s: %s can't be switched on or off from Home Assistant", self._name, self._model)
            return False
        return await self._call_action(*self._profile.power_action)

    async def turn_on(self, mode: int | None = None) -> bool:
        await self.refresh_power()
        if not self.is_on and not await self.toggle_power():
            return False
        return await self.set_mode(mode) if mode is not None else True

    async def turn_off(self) -> bool:
        await self.refresh_power()
        return await self.toggle_power() if self.is_on else True

    async def set_mode(self, mode: int) -> bool:
        if mode not in self._profile.modes:
            _LOGGER.warning("%s: mode %s isn't valid for %s", self._name, mode, self._model)
            return False
        return await self._set_attr("mode_value", mode)

    async def set_fan_speed(self, speed: int) -> bool:
        return await self._set_attr("fan_speed", max(1, min(self._profile.speed_count, speed)))

    async def set_swivel(self, angle: int) -> bool:
        if angle not in SWIVEL_OPTIONS:
            return False
        return await self._set_attr("swivel", angle)

    async def set_continuous_monitoring(self, enabled: bool) -> bool:
        return await self._set_attr("continuous_monitoring", int(enabled))

    async def set_child_lock(self, enabled: bool) -> bool:
        return await self._set_attr("child_lock", int(enabled))

    async def set_human_sensing(self, enabled: bool) -> bool:
        return await self._set_attr("human_sensing", int(enabled))

    async def set_follow_mode(self, enabled: bool) -> bool:
        return await self._set_attr("follow_mode", int(enabled))

    async def set_voice_assistant(self, enabled: bool) -> bool:
        return await self._set_attr("voice_assistant", int(enabled))

    async def set_temp_unit(self, unit: int) -> bool:
        return await self._set_attr("temp_unit", unit)

    async def set_timer(self, hours: int) -> bool:
        return await self._set_attr("timer", max(0, min(self._profile.timer_max, hours)))

    async def reset_hepa_filter(self) -> bool:
        return await self._call_action(4, 1)

    async def reset_carbon_filter(self) -> bool:
        return await self._call_action(5, 1)
