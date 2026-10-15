"""Diagnostics for Dreame Air Purifier.

Download from Settings -> Devices & services -> Dreame Air Purifier -> ... -> Download diagnostics.
Useful for mapping a new model: shows every property the device reported and which
known attributes it doesn't have. Credentials, device IDs and MACs are not included.
"""
from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    data = hass.data[DOMAIN][entry.entry_id]
    return {
        "devices": [
            {
                "model": p.model,
                "available": p.available,
                "supported": p.supported_attrs,
                "unsupported": p.unsupported_attrs,
                "raw_properties": p.raw_properties,
            }
            for p in data["purifiers"]
        ]
    }
