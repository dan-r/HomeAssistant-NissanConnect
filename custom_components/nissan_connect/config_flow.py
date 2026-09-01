import secrets

import homeassistant.helpers.config_validation as cv
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, OptionsFlow
from homeassistant.helpers import selector

from .const import (
    CONFIG_VERSION,
    CONF_REMOTE_LOCK,
    CONF_REMOTE_LOCK_DEVICE_ID,
    CONF_REMOTE_LOCK_STATUS,
    DEFAULT_INTERVAL_CHARGING,
    DEFAULT_INTERVAL_FETCH,
    DEFAULT_INTERVAL_POLL,
    DEFAULT_INTERVAL_STATISTICS,
    DEFAULT_REGION,
    DOMAIN,
    REGIONS,
    REMOTE_LOCK_STATUS_CONFIGURED,
    REMOTE_LOCK_STATUS_ENABLED,
    REMOTE_LOCK_STATUS_REGISTERED,
    REMOTE_LOCK_STATUS_UNREGISTERED,
)
from .kamereon import NCISession, NissanAuthError, RemoteLockError

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
        self._pending_data = None
        self._pending_vehicle = None
        self._pending_device_id = None
        self._pending_status_after_pin = REMOTE_LOCK_STATUS_ENABLED
        self._remote_lock_vehicles = {}

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
                configure_remote_lock = options.pop(
                    "configure_remote_lock", False)

                # If password not provided, dont take the new details
                if "password" not in options:
                    options.pop('email', None)
                    options.pop('password', None)

                # Update data
                data.update(options)
                if configure_remote_lock:
                    return await self._async_start_remote_lock_setup(data)

                self.hass.config_entries.async_update_entry(
                    self._config_entry, data=data
                )

                # Update options
                return self.async_create_entry(
                    title="",
                    data={}
                )

        return self.async_show_form(
            step_id="init", data_schema=self._init_schema(), errors=errors
        )

    def _init_schema(self):
        return vol.Schema({
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
                vol.Required("configure_remote_lock", default=False): bool,
            })

    async def _async_start_remote_lock_setup(self, data):
        session = NCISession(region=data["region"])
        try:
            await self.hass.async_add_executor_job(
                session.login,
                data.get("email"),
                data.get("password"),
            )
            vehicles = await self.hass.async_add_executor_job(
                session.fetch_vehicles)
        except NissanAuthError:
            return self.async_show_form(
                step_id="init",
                data_schema=self._init_schema(),
                errors={"base": "auth_error"},
            )
        except Exception:
            return self.async_show_form(
                step_id="init",
                data_schema=self._init_schema(),
                errors={"base": "cannot_connect"},
            )

        self._remote_lock_vehicles = {
            vehicle.vin: vehicle
            for vehicle in vehicles
            if vehicle.supports_remote_lock_setup
        }
        if not self._remote_lock_vehicles:
            return self.async_abort(reason="no_remote_lock_vehicle")

        self._pending_data = data
        return await self.async_step_remote_lock_vehicle()

    def _vehicle_schema(self):
        options = []
        for vehicle in self._remote_lock_vehicles.values():
            name = vehicle.nickname or vehicle.model_name or "Nissan"
            options.append(selector.SelectOptionDict(
                value=vehicle.vin,
                label=f"{name} ({vehicle.vin[-6:]})",
            ))
        return vol.Schema({
            vol.Required("vehicle"): selector.SelectSelector(
                selector.SelectSelectorConfig(
                    options=options,
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )
            )
        })

    async def async_step_remote_lock_vehicle(self, options=None):
        errors = {}
        if options is not None:
            vehicle = self._remote_lock_vehicles.get(options["vehicle"])
            if vehicle is None:
                errors["vehicle"] = "invalid_vehicle"
            else:
                self._pending_vehicle = vehicle
                remote_lock = self._pending_data.get(CONF_REMOTE_LOCK, {})
                vehicle_config = remote_lock.get(vehicle.vin, {})
                status = vehicle_config.get(CONF_REMOTE_LOCK_STATUS)
                self._pending_device_id = vehicle_config.get(
                    CONF_REMOTE_LOCK_DEVICE_ID)

                if status == REMOTE_LOCK_STATUS_REGISTERED:
                    try:
                        registered = await self.hass.async_add_executor_job(
                            vehicle.remote_lock_device_is_registered,
                            self._pending_device_id,
                        )
                    except (RemoteLockError, ValueError):
                        errors["base"] = "remote_lock_setup_error"
                    else:
                        if registered:
                            self._pending_status_after_pin = (
                                REMOTE_LOCK_STATUS_ENABLED)
                            return await self.async_step_remote_lock_pin()
                        return await self._async_request_remote_lock_otp()
                elif status in (
                        REMOTE_LOCK_STATUS_CONFIGURED,
                        REMOTE_LOCK_STATUS_ENABLED):
                    return await self.async_step_remote_lock_enabled()
                else:
                    self._pending_device_id = (
                        self._pending_device_id or secrets.token_hex(16))
                    return await self._async_request_remote_lock_otp()

        return self.async_show_form(
            step_id="remote_lock_vehicle",
            data_schema=self._vehicle_schema(),
            errors=errors,
        )

    async def _async_request_remote_lock_otp(self):
        try:
            await self.hass.async_add_executor_job(
                self._pending_vehicle.request_remote_lock_otp,
                self._pending_device_id,
            )
        except (RemoteLockError, ValueError):
            return self.async_show_form(
                step_id="remote_lock_vehicle",
                data_schema=self._vehicle_schema(),
                errors={"base": "remote_lock_setup_error"},
            )
        return await self.async_step_remote_lock_otp()

    async def async_step_remote_lock_otp(self, options=None):
        errors = {}
        if options is not None:
            otp = options["otp"].strip()
            if len(otp) != 6 or not otp.isdigit():
                errors["otp"] = "otp_invalid"
            else:
                try:
                    await self.hass.async_add_executor_job(
                        self._pending_vehicle.register_remote_lock_device,
                        self._pending_device_id,
                        otp,
                    )
                except (RemoteLockError, ValueError):
                    errors["base"] = "device_registration_error"
                else:
                    self._save_remote_lock_config(
                        REMOTE_LOCK_STATUS_REGISTERED)
                    self._pending_status_after_pin = (
                        REMOTE_LOCK_STATUS_ENABLED)
                    return await self.async_step_remote_lock_pin()

        return self.async_show_form(
            step_id="remote_lock_otp",
            data_schema=vol.Schema({
                vol.Required("otp"): cv.string,
            }),
            errors=errors,
        )

    async def async_step_remote_lock_pin(self, options=None):
        errors = {}
        if options is not None:
            pin = options["pin"].strip()
            if len(pin) != 4 or not pin.isdigit():
                errors["pin"] = "pin_invalid"
            elif pin != options["pin_confirm"].strip():
                errors["pin_confirm"] = "pin_mismatch"
            else:
                try:
                    await self.hass.async_add_executor_job(
                        self._pending_vehicle.enroll_remote_lock_pin,
                        pin,
                    )
                except (RemoteLockError, ValueError):
                    errors["base"] = "pin_enrollment_error"
                else:
                    self._save_remote_lock_config(
                        self._pending_status_after_pin)
                    return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="remote_lock_pin",
            data_schema=vol.Schema({
                vol.Required("pin"): cv.string,
                vol.Required("pin_confirm"): cv.string,
            }),
            errors=errors,
        )

    async def async_step_remote_lock_enabled(self, options=None):
        vehicle_config = self._pending_data.get(
            CONF_REMOTE_LOCK, {}).get(self._pending_vehicle.vin, {})
        currently_enabled = (
            vehicle_config.get(CONF_REMOTE_LOCK_STATUS)
            == REMOTE_LOCK_STATUS_ENABLED
        )
        actions = (
            ["disable", "update_pin", "remove_device"]
            if currently_enabled
            else ["enable", "update_pin", "remove_device"]
        )
        errors = {}
        if options is not None:
            action = options["action"]
            if action == "update_pin":
                self._pending_status_after_pin = (
                    REMOTE_LOCK_STATUS_ENABLED
                    if currently_enabled
                    else REMOTE_LOCK_STATUS_CONFIGURED
                )
                return await self.async_step_remote_lock_pin()
            if action == "remove_device":
                try:
                    await self.hass.async_add_executor_job(
                        self._pending_vehicle.unregister_remote_lock_device,
                        self._pending_device_id,
                    )
                except (RemoteLockError, ValueError):
                    errors["base"] = "device_removal_error"
                else:
                    self._save_remote_lock_config(
                        REMOTE_LOCK_STATUS_UNREGISTERED)
                    return self.async_create_entry(title="", data={})
            elif action in ("enable", "disable"):
                status = (
                    REMOTE_LOCK_STATUS_ENABLED
                    if action == "enable"
                    else REMOTE_LOCK_STATUS_CONFIGURED
                )
                self._save_remote_lock_config(status)
                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="remote_lock_enabled",
            data_schema=vol.Schema({
                vol.Required("action"): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=actions,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                        translation_key="remote_lock_action",
                    )
                ),
            }),
            errors=errors,
        )

    def _save_remote_lock_config(self, status):
        data = dict(self._pending_data)
        remote_lock = {
            vin: dict(vehicle_config)
            for vin, vehicle_config in data.get(CONF_REMOTE_LOCK, {}).items()
        }
        remote_lock[self._pending_vehicle.vin] = {
            CONF_REMOTE_LOCK_DEVICE_ID: self._pending_device_id,
            CONF_REMOTE_LOCK_STATUS: status,
        }
        data[CONF_REMOTE_LOCK] = remote_lock
        self._pending_data = data
        self.hass.config_entries.async_update_entry(
            self._config_entry,
            data=data,
        )
