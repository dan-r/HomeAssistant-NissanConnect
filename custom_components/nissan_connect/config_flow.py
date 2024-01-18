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

    def async_get_options_flow(entry):
        return NissanOptionsFlow(entry)


class NissanOptionsFlow(OptionsFlow):
    """Options flow."""

    def __init__(self, entry) -> None:
        self._config_entry = entry

    async def async_step_init(self, options):
        errors = {}
        # If form filled
        if options is not None:
            data = dict(self._config_entry.data)
             # Validate credentials
            kamereon_session = NCISession(
                region=data["region"]
            )
            if "password" in options:
                try:
                    await self.hass.async_add_executor_job(kamereon_session.login,
                                                        options["email"],
                                                        options["password"]
                                                        )
                except:
                    errors["base"] = "auth_error"

            # If we have no errors, update the data array
            if len(errors) == 0:
                # If password not provided, dont take the new details
                if not "password" in options:
                    options.pop('email', None)
                    options.pop('password', None)
                
                # Update data
                data.update(options)
                self.hass.config_entries.async_update_entry(
                    self._config_entry, data=data
                )

                # Update options
                return self.async_create_entry(
                    title="",
                    data={}
                )

        return self.async_show_form(
            step_id="init", data_schema=vol.Schema({
                vol.Required("email", default=self._config_entry.data.get("email", "")): cv.string,
                vol.Optional("password"): cv.string,
                vol.Optional(
                    "interval", default=self._config_entry.data.get("interval", 60)
                ): int,
                vol.Optional(
                    "interval_charging", default=self._config_entry.data.get("interval_charging", 15)
                ): int
            }), errors=errors
        )
