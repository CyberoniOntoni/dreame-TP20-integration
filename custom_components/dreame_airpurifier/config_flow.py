"""Config flow for AirPursue PM10 Air Purifier."""
from __future__ import annotations

import logging

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.const import CONF_USERNAME, CONF_PASSWORD
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .api import DreameCloudAPI
from .const import DOMAIN, CONF_COUNTRY, COUNTRY_OPTIONS

_LOGGER = logging.getLogger(__name__)

_SCHEMA = vol.Schema({
    vol.Required(CONF_USERNAME): str,
    vol.Required(CONF_PASSWORD): str,
    vol.Required(CONF_COUNTRY, default="us"): vol.In(COUNTRY_OPTIONS),
})


class DreameAirPurifierConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_USERNAME].lower())
            self._abort_if_unique_id_configured()

            session = async_get_clientsession(self.hass)
            api = DreameCloudAPI(session, user_input[CONF_USERNAME], user_input[CONF_PASSWORD], user_input[CONF_COUNTRY])
            if await api.login():
                purifiers = await api.get_purifiers()
                if purifiers:
                    return self.async_create_entry(
                        title=f"AirPursue PM10 ({user_input[CONF_USERNAME]})",
                        data=user_input,
                    )
                errors["base"] = "no_devices"
            else:
                errors["base"] = "invalid_auth"

        return self.async_show_form(step_id="user", data_schema=_SCHEMA, errors=errors)

    async def async_step_reauth(self, entry_data: dict):
        """Handle re-authentication when credentials expire."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input=None):
        errors = {}
        if user_input is not None:
            session = async_get_clientsession(self.hass)
            api = DreameCloudAPI(session, user_input[CONF_USERNAME], user_input[CONF_PASSWORD], user_input.get(CONF_COUNTRY, "us"))
            if await api.login():
                entry = self.hass.config_entries.async_get_entry(self.context["entry_id"])
                self.hass.config_entries.async_update_entry(entry, data=user_input)
                await self.hass.config_entries.async_reload(entry.entry_id)
                return self.async_abort(reason="reauth_successful")
            errors["base"] = "invalid_auth"

        return self.async_show_form(step_id="reauth_confirm", data_schema=_SCHEMA, errors=errors)
