"""Fan platform for AirPursue PM10."""
from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, MODE_NAME_TO_VALUE, MODE_NAMES, MODE_CUSTOM, MODE_AUTO
from .entity import DreameEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(DreameFan(data["coordinator"], p) for p in data["purifiers"])


class DreameFan(DreameEntity, FanEntity):
    _attr_name = None
    _attr_speed_count = 10
    _attr_preset_modes = list(MODE_NAMES.values())

    def __init__(self, coordinator, purifier):
        super().__init__(coordinator, purifier)
        self._attr_unique_id = f"{purifier.unique_id}_fan"
        self._attr_supported_features = (
            FanEntityFeature.SET_SPEED | FanEntityFeature.PRESET_MODE
            | FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
        )

    @staticmethod
    def _pct_to_speed(percentage: int) -> int:
        """Convert HA percentage (0-100) to device speed level (1-10)."""
        return max(1, min(10, round(percentage / 10)))

    @property
    def is_on(self) -> bool:
        return self._purifier.is_on

    @property
    def percentage(self) -> int | None:
        if not self._purifier.is_on or self._purifier.mode_value != MODE_CUSTOM:
            return None
        return self._purifier.fan_speed_percent

    @property
    def preset_mode(self) -> str | None:
        return self._purifier.mode

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"fan_speed_level": self._purifier.fan_speed}

    async def async_turn_on(self, percentage=None, preset_mode=None, **kwargs) -> None:
        mode = MODE_NAME_TO_VALUE.get(preset_mode, MODE_CUSTOM if percentage else MODE_AUTO)
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
        if self._purifier.mode_value != MODE_CUSTOM:
            await self._purifier.set_mode(MODE_CUSTOM)
        await self._purifier.set_fan_speed(self._pct_to_speed(percentage))
        await self.coordinator.async_request_refresh()

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        mode_value = MODE_NAME_TO_VALUE.get(preset_mode)
        if mode_value is not None:
            await self._purifier.set_mode(mode_value)
            await self.coordinator.async_request_refresh()
