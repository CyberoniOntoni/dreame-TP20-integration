"""Fan platform for Dreame air purifiers."""
from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import DreameEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(DreameFan(data["coordinator"], p) for p in data["purifiers"])


class DreameFan(DreameEntity, FanEntity):
    """Speeds, presets and the manual mode come from the model's profile."""

    _attr_name = None

    def __init__(self, coordinator, purifier):
        super().__init__(coordinator, purifier)
        self._profile = purifier.profile
        self._attr_unique_id = f"{purifier.unique_id}_fan"
        self._attr_speed_count = self._profile.speed_count
        self._attr_preset_modes = list(self._profile.modes.values())
        self._attr_supported_features = (
            FanEntityFeature.SET_SPEED | FanEntityFeature.PRESET_MODE
            | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
        )

    def _pct_to_speed(self, percentage: int) -> int:
        """Convert HA percentage (0-100) to device speed level (1..speed_count)."""
        n = self._profile.speed_count
        return max(1, min(n, round(percentage * n / 100)))

    @property
    def is_on(self) -> bool:
        return self._purifier.is_on

    @property
    def percentage(self) -> int | None:
        if not self._purifier.is_on or self._purifier.mode_value != self._profile.manual_mode:
            return None
        return self._purifier.fan_speed_percent

    @property
    def preset_mode(self) -> str | None:
        return self._purifier.mode

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"fan_speed_level": self._purifier.fan_speed}

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs) -> None:
        if preset_mode is not None:
            mode = self._profile.mode_by_name.get(preset_mode)
        elif percentage:
            mode = self._profile.manual_mode
        else:
            mode = None  # just switch on, keeping whatever mode it was in
        await self._purifier.turn_on(mode)
        if percentage:
            await self._purifier.set_fan_speed(self._pct_to_speed(percentage))
        await self.coordinator.async_request_refresh()

    async def async_turn_off(self, **kwargs) -> None:
        await self._purifier.turn_off()
        await self.coordinator.async_request_refresh()

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage == 0:
            await self.async_turn_off()
            return
        if self._purifier.mode_value != self._profile.manual_mode:
            await self._purifier.set_mode(self._profile.manual_mode)
        await self._purifier.set_fan_speed(self._pct_to_speed(percentage))
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        mode_value = self._profile.mode_by_name.get(preset_mode)
        if mode_value is not None:
            await self._purifier.set_mode(mode_value)
            await self.coordinator.async_request_refresh()
