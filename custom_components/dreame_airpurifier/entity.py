"""Base entity for Dreame Air Purifier."""
from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .api import DreameAirPurifier
from .const import DOMAIN


class DreameEntity(CoordinatorEntity):
    """Common base for all Dreame Air Purifier entities."""

    _attr_has_entity_name = True

    def __init__(self, coordinator, purifier: DreameAirPurifier):
        super().__init__(coordinator)
        self._purifier = purifier

    @property
    def device_info(self) -> DeviceInfo:
        from homeassistant.helpers.device_registry import CONNECTION_NETWORK_MAC

        return DeviceInfo(
            identifiers={(DOMAIN, self._purifier.unique_id)},
            connections={(CONNECTION_NETWORK_MAC, self._purifier.mac)} if self._purifier.mac else None,
            name=self._purifier.name,
            manufacturer="Dreame",
            model=self._purifier.model,
        )

    @property
    def available(self) -> bool:
        return self._purifier.available
