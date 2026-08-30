import voluptuous as vol
from homeassistant.config_entries import (ConfigFlow, OptionsFlow)
from .const import DOMAIN, CONFIG_VERSION, DEFAULT_INTERVAL_POLL, DEFAULT_INTERVAL_CHARGING, DEFAULT_INTERVAL_STATISTICS, DEFAULT_INTERVAL_FETCH, DEFAULT_REGION, REGIONS
from .kamereon import NCISession, NissanAuthError
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
        "region", default=DEFAULT_REGION.lower()): selector.SelectSelector(
            selector.SelectSelectorConfig(
                options=[el.lower() for el in REGIONS], # Translation keys must be lowercase
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

    def __init__(self):
        self._reauth_entry = None

    async def async_step_user(self, info):
        errors = {}
        if info is not None:
            info["region"] = info["region"].upper()

            await self.async_set_unique_id(info["email"])
            self._abort_if_unique_id_configured()

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
                    title=info["email"],
                    data=info
                )

        return self.async_show_form(
            step_id="user", data_schema=USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(self, entry_data):
        """Start reauthentication for an existing entry."""
        self._reauth_entry = self.hass.config_entries.async_get_entry(
            self.context["entry_id"]
        )
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, info=None):
        """Validate updated OneID credentials."""
        errors = {}
        if info is not None:
            data = dict(self._reauth_entry.data)
            kamereon_session = NCISession(
                region=data["region"]
            )
            try:
                await self.hass.async_add_executor_job(
                    kamereon_session.login,
                    data["email"],
                    info["password"],
                )
            except NissanAuthError:
                errors["base"] = "auth_error"
            except Exception:
                errors["base"] = "cannot_connect"
            else:
                data.update(info)
                return self.async_update_reload_and_abort(
                    self._reauth_entry,
                    data=data,
                )

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema({
                vol.Required("password"): cv.string,
            }),
            errors=errors,
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
                                                           self._config_entry.data.get("email"),
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
                # vol.Required("email", default=self._config_entry.data.get("email", "")): cv.string,
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
