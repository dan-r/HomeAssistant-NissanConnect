import voluptuous as vol
from homeassistant.config_entries import (ConfigFlow, OptionsFlow)
from .const import DOMAIN, CONFIG_VERSION, DEFAULT_UPDATE_INTERVAL
import homeassistant.helpers.config_validation as cv


USER_SCHEMA = vol.Schema({
    vol.Required("email"): cv.string,
    vol.Required("password"): cv.string,
    vol.Optional(
        "interval", default=DEFAULT_UPDATE_INTERVAL
    ): int,
    vol.Optional(
        "region", default="EU"): cv.string,
})


class NissanConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow."""
    VERSION = CONFIG_VERSION

    async def async_step_user(self, info):
        errors = {}

        if info is not None:
            # await self.async_set_unique_id("ohm)
            self._abort_if_unique_id_configured()
        
            return self.async_create_entry(
                title="Car",
                data=info
            )

        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

