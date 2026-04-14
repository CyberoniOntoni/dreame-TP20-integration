"""Sensor platform for AirPursue PM10."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.sensor import SensorEntity, SensorDeviceClass, SensorStateClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONCENTRATION_MICROGRAMS_PER_CUBIC_METER, PERCENTAGE, UnitOfTemperature, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .entity import DreameEntity


@dataclass(frozen=True, slots=True)
class SensorSpec:
    key: str
    attr: str
    device_class: SensorDeviceClass | None = None
    state_class: SensorStateClass | None = None
    unit: str | None = None
    icon: str | None = None
    precision: int | None = None
    scale: float = 1.0
    category: EntityCategory | None = None


_M = SensorStateClass.MEASUREMENT
_T = SensorStateClass.TOTAL_INCREASING
_UG = CONCENTRATION_MICROGRAMS_PER_CUBIC_METER
_D = EntityCategory.DIAGNOSTIC

SENSORS: tuple[SensorSpec, ...] = (
    SensorSpec("humidity", "humidity", SensorDeviceClass.HUMIDITY, _M, PERCENTAGE),
    SensorSpec("temperature", "temperature", SensorDeviceClass.TEMPERATURE, _M, UnitOfTemperature.CELSIUS),
    SensorSpec("pm25", "pm25", SensorDeviceClass.PM25, _M, _UG),
    SensorSpec("pm10", "pm10_value", SensorDeviceClass.PM10, _M, _UG),
    SensorSpec("pm1", "pm1", SensorDeviceClass.PM1, _M, _UG),
    SensorSpec("hcho", "hcho", None, _M, "mg/m\u00b3", "mdi:molecule", 3, 0.001),
    SensorSpec("tvoc", "tvoc", SensorDeviceClass.VOLATILE_ORGANIC_COMPOUNDS, _M, _UG),
    SensorSpec("air_quality", "air_quality_level", icon="mdi:air-filter"),
    SensorSpec("aq_percent", "aq_percent", state_class=_M, unit=PERCENTAGE, icon="mdi:air-filter"),
    SensorSpec("hepa_life", "hepa_life", state_class=_M, unit=PERCENTAGE, icon="mdi:air-filter", category=_D),
    SensorSpec("hepa_used", "hepa_hours_used", state_class=_T, unit=UnitOfTime.HOURS, icon="mdi:clock-outline", category=_D),
    SensorSpec("hepa_days", "hepa_days_total", unit=UnitOfTime.DAYS, icon="mdi:calendar-clock", category=_D),
    SensorSpec("carbon_life", "carbon_life", state_class=_M, unit=PERCENTAGE, icon="mdi:air-filter", category=_D),
    SensorSpec("carbon_used", "carbon_hours_used", state_class=_T, unit=UnitOfTime.HOURS, icon="mdi:clock-outline", category=_D),
    SensorSpec("carbon_days", "carbon_days_total", unit=UnitOfTime.DAYS, icon="mdi:calendar-clock", category=_D),
)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    data = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(DreameSensor(data["coordinator"], p, spec) for p in data["purifiers"] for spec in SENSORS)


class DreameSensor(DreameEntity, SensorEntity):
    def __init__(self, coordinator, purifier, spec: SensorSpec):
        super().__init__(coordinator, purifier)
        self._spec = spec
        self._attr_unique_id = f"{purifier.unique_id}_{spec.key}"
        self._attr_translation_key = spec.key
        self._attr_device_class = spec.device_class
        self._attr_state_class = spec.state_class
        self._attr_native_unit_of_measurement = spec.unit
        if spec.icon:
            self._attr_icon = spec.icon
        if spec.precision is not None:
            self._attr_suggested_display_precision = spec.precision
        if spec.category is not None:
            self._attr_entity_category = spec.category

    @property
    def native_value(self):
        v = getattr(self._purifier, self._spec.attr)
        if v is None:
            return None
        return v * self._spec.scale if self._spec.scale != 1 else v
