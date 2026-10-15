"""Base entity for Dreame Air Purifier."""
from __future__ import annotations

from collections.abc import Awaitable

from homeassistant.exceptions import HomeAssistantError
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

    async def _write(self, *steps: Awaitable[bool], action: str) -> None:
        """Run commands in order, refresh, and show an error in HA if one wasn't
        confirmed (stopping there, so e.g. a speed isn't sent after a failed mode change)."""
        ok, done = True, 0
        try:
            for step in steps:
                done += 1
                if not await step:
                    ok = False
                    break
        finally:
            for rest in steps[done:]:
                rest.close()  # never sent (after a failure or an exception)
        await self.coordinator.async_request_refresh()
        if not ok:
            raise HomeAssistantError(f"{self._purifier.name}: couldn't {action}. The change wasn't confirmed; see the log for details.")
