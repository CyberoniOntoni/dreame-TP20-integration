"""Fan platform for Dreame air purifiers."""
from __future__ import annotations

from typing import Any

from homeassistant.components.fan import FanEntity, FanEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
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
        features = FanEntityFeature.SET_SPEED | FanEntityFeature.PRESET_MODE
        if purifier.can_switch_power:
            features |= FanEntityFeature.TURN_ON | FanEntityFeature.TURN_OFF
        self._attr_supported_features = features

    async def _ensure_controllable(self) -> None:
        """On models without power control (TP20), refuse fan changes while it's off:
        writes to a switched-off TP20 are untested. Power is read fresh (a single read of
        it is safe), since the last poll can be up to 30 s old."""
        if self._purifier.can_switch_power:
            return
        await self._purifier.refresh_power()
        if not self._purifier.is_on:
            raise HomeAssistantError(
                f"{self._purifier.name} is off. Switch it on from the Dreame app or its power button; "
                "Home Assistant can't switch this model on or off."
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
        if not self._purifier.can_switch_power:
            # Can't switch power: just apply the preset or speed (each checks it's on).
            if preset_mode is not None:
                await self.async_set_preset_mode(preset_mode)
            if percentage:
                await self.async_set_percentage(percentage)
            if preset_mode is None and not percentage:
                await self._ensure_controllable()
            return
        if preset_mode is not None:
            mode = self._profile.mode_by_name.get(preset_mode)
        elif percentage:
            mode = self._profile.manual_mode
        else:
            mode = None  # just switch on, keeping whatever mode it was in
        steps = [self._purifier.turn_on(mode)]
        if percentage:
            steps.append(self._purifier.set_fan_speed(self._pct_to_speed(percentage)))
        await self._write(*steps, action="turn on" + (f" in {preset_mode}" if preset_mode else ""))

    async def async_turn_off(self, **kwargs) -> None:
        if not self._purifier.can_switch_power:
            raise HomeAssistantError(
                f"Home Assistant can't switch {self._purifier.name} off. Use the Dreame app or its power button."
            )
        await self._write(self._purifier.turn_off(), action="turn off")

    async def async_set_percentage(self, percentage: int) -> None:
        if percentage == 0:
            await self.async_turn_off()
            return
        await self._ensure_controllable()
        steps = []
        if self._purifier.mode_value != self._profile.manual_mode:
            steps.append(self._purifier.set_mode(self._profile.manual_mode))
        steps.append(self._purifier.set_fan_speed(self._pct_to_speed(percentage)))
        await self._write(*steps, action=f"set the fan speed to {percentage}%")

    async def async_set_preset_mode(self, preset_mode: str) -> None:
        mode_value = self._profile.mode_by_name.get(preset_mode)
        await self._ensure_controllable()
        if mode_value is not None:
            await self._write(self._purifier.set_mode(mode_value), action=f"switch to {preset_mode}")
