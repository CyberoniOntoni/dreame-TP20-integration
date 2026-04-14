"""Select platform for AirPursue PM10."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import DreameEntity


@dataclass(frozen=True, slots=True)
class SelectSpec:
    key: str
    attr: str
    setter: str
    icon: str
    options: dict[str, int]


SELECTS: tuple[SelectSpec, ...] = (
    SelectSpec("swivel", "swivel", "set_swivel", "mdi:rotate-3d-variant", {"0\u00b0": 0, "45\u00b0": 45, "90\u00b0": 90, "180\u00b0": 180}),
    SelectSpec("temp_unit", "temp_unit", "set_temp_unit", "mdi:thermometer", {"Celsius": 0, "Fahrenheit": 1}),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(DreameSelect(data["coordinator"], p, spec) for p in data["purifiers"] for spec in SELECTS)


class DreameSelect(DreameEntity, SelectEntity):
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator, purifier, spec: SelectSpec):
        super().__init__(coordinator, purifier)
        self._spec = spec
        self._value_to_name: dict[int, str] = {v: k for k, v in spec.options.items()}
        self._attr_unique_id = f"{purifier.unique_id}_{spec.key}"
        self._attr_translation_key = spec.key
        self._attr_icon = spec.icon
        self._attr_options = list(spec.options.keys())

    @property
    def current_option(self) -> str | None:
        return self._value_to_name.get(getattr(self._purifier, self._spec.attr))

    async def async_select_option(self, option: str) -> None:
        if self._spec.key == "swivel":
            await self._purifier.set_follow_mode(False)
        await getattr(self._purifier, self._spec.setter)(self._spec.options[option])
        await self.coordinator.async_request_refresh()
