"""Number platform for AirPursue PM10."""
from __future__ import annotations

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import DreameEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(DreameTimer(data["coordinator"], p) for p in data["purifiers"] if p.supports("timer"))


class DreameTimer(DreameEntity, NumberEntity):
    _attr_entity_category = EntityCategory.CONFIG
    _attr_translation_key = "timer"
    _attr_icon = "mdi:timer-outline"
    _attr_native_min_value = 0
    _attr_native_max_value = 24
    _attr_native_step = 1
    _attr_mode = NumberMode.SLIDER
    _attr_native_unit_of_measurement = UnitOfTime.HOURS

    def __init__(self, coordinator, purifier):
        super().__init__(coordinator, purifier)
        self._attr_unique_id = f"{purifier.unique_id}_timer"

    @property
    def native_value(self):
        return self._purifier.timer

    async def async_set_native_value(self, value: float) -> None:
        await self._purifier.set_timer(int(value))
        await self.coordinator.async_request_refresh()
