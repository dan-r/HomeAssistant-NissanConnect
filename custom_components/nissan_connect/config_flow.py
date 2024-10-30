import voluptuous as vol
from homeassistant.config_entries import (ConfigFlow, OptionsFlow)
from .const import DOMAIN, CONFIG_VERSION, DEFAULT_INTERVAL_POLL, DEFAULT_INTERVAL_CHARGING, DEFAULT_INTERVAL_STATISTICS, DEFAULT_INTERVAL_FETCH, DEFAULT_REGION, REGIONS
from .kamereon import NCISession
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import selector

USER_SCHEMA = vol.Schema({
    vol.Required("email"): cv.string,
    vol.Required("password"): cv.string,
    # vol.Required(
    #     "interval", default=DEFAULT_INTERVAL_POLL
    # ): int,
    # vol.Required(
    #     "interval_charging", default=DEFAULT_INTERVAL_CHARGING
    # ): int,
    # vol.Required(
    #     "interval_fetch", default=DEFAULT_INTERVAL_FETCH
    # ): int,
    # vol.Required(
    #     "interval_statistics", default=DEFAULT_INTERVAL_STATISTICS
    # ): int,
    vol.Required(
        "region", default=DEFAULT_REGION): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=REGIONS,
                mode=selector.SelectSelectorMode.DROPDOWN,
                translation_key="region"
            ),
    ),
    vol.Required(
        "imperial_distance", default=False): bool
})


class NissanConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow."""
    VERSION = CONFIG_VERSION

    async def async_step_user(self, info):
        errors = {}
        if info is not None and info["region"] not in REGIONS:
            errors["base"] = "region_error"
        elif info is not None:
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
                vol.Required(
                    "interval", default=self._config_entry.data.get("interval", DEFAULT_INTERVAL_POLL)
                ): int,
                vol.Required(
                    "interval_charging", default=self._config_entry.data.get("interval_charging", DEFAULT_INTERVAL_CHARGING)
                ): int,
                vol.Required(
                    "interval_fetch", default=self._config_entry.data.get("interval_fetch", DEFAULT_INTERVAL_FETCH)
                ): int,
                vol.Required(
                    "interval_statistics", default=self._config_entry.data.get("interval_statistics", DEFAULT_INTERVAL_STATISTICS)
                ): int,
                # Excluded from config flow under #61
                # vol.Required(
                #     "imperial_distance", default=self._config_entry.data.get("imperial_distance", False)): bool
            }), errors=errors
        )
