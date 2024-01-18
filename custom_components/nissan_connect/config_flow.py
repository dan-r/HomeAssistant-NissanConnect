import voluptuous as vol
from homeassistant.config_entries import (ConfigFlow, OptionsFlow)
from .const import DOMAIN, CONFIG_VERSION
from .kamereon import NCISession
import homeassistant.helpers.config_validation as cv

USER_SCHEMA = vol.Schema({
    vol.Required("email"): cv.string,
    vol.Required("password"): cv.string,
    vol.Optional(
        "interval", default=60
    ): int,
    vol.Optional(
        "interval_charging", default=15
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
            # Validate credentials
            kamereon_session = NCISession(
                region=info["region"]
            )

            try:
                await self.hass.async_add_executor_job(kamereon_session.login,
                    info["email"],
                    info["password"]
                )
            except:
                errors["base"] = "auth_error"
            
            if len(errors) == 0:
                return self.async_create_entry(
                    title="NissanConnect Account",
                    data=info
                )

        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

