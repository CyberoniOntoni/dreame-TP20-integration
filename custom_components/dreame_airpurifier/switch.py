"""Switch platform for AirPursue PM10."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import DreameEntity


@dataclass(frozen=True, slots=True)
class SwitchSpec:
    key: str
    attr: str
    setter: str
    icon: str


SWITCHES: tuple[SwitchSpec, ...] = (
    SwitchSpec("continuous_monitoring", "continuous_monitoring", "set_continuous_monitoring", "mdi:eye"),
    SwitchSpec("human_sensing", "human_sensing", "set_human_sensing", "mdi:motion-sensor"),
    SwitchSpec("follow_mode", "follow_mode", "set_follow_mode", "mdi:rotate-3d-variant"),
    SwitchSpec("voice_assistant", "voice_assistant", "set_voice_assistant", "mdi:microphone"),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(DreameSwitch(data["coordinator"], p, spec) for p in data["purifiers"] for spec in SWITCHES)


class DreameSwitch(DreameEntity, SwitchEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, purifier, spec: SwitchSpec):
        super().__init__(coordinator, purifier)
        self._spec = spec
        self._attr_unique_id = f"{purifier.unique_id}_{spec.key}"
        self._attr_translation_key = spec.key
        self._attr_icon = spec.icon

    @property
    def is_on(self):
        return getattr(self._purifier, self._spec.attr)

    async def _set(self, value: bool) -> None:
        await getattr(self._purifier, self._spec.setter)(value)
        await self.coordinator.async_request_refresh()

    async def async_turn_on(self, **kwargs) -> None:
        await self._set(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self._set(False)
