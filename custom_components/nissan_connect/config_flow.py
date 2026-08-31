import logging
import secrets

import voluptuous as vol
from homeassistant.config_entries import (ConfigFlow, OptionsFlow)
from .const import DOMAIN, CONFIG_VERSION, DEFAULT_INTERVAL_POLL, DEFAULT_INTERVAL_CHARGING, DEFAULT_INTERVAL_STATISTICS, DEFAULT_INTERVAL_FETCH, DEFAULT_REGION, REGIONS
from .kamereon import NCISession, NissanAuthError, Feature
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers import selector

_LOGGER = logging.getLogger(__name__)

# The app's own device-registration OTP field is a 6-digit numeric code
# (android:maxLength="6" / inputType="number" on that screen).
REMOTE_LOCK_OTP_SCHEMA = vol.Schema({
    vol.Required("otp"): cv.string,
    vol.Required("pincode"): cv.string,
    vol.Required("pincode_confirm"): cv.string,
})

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
        # Transient state carried between async_step_init and
        # async_step_remote_lock_otp while setting up remote lock/unlock.
        self._pending_data = None
        self._pending_vehicle = None
        self._pending_device_id = None

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

                setup_remote_lock = options.pop("setup_remote_lock", False)

                # Update data
                data.update(options)

                # Kick off remote lock/unlock setup (device registration +
                # SRP PIN enrollment) only when newly enabled - once done,
                # data.get("remote_lock_enabled") stays True and re-opening
                # options won't re-trigger it.
                if setup_remote_lock and not data.get("remote_lock_enabled"):
                    _LOGGER.info(
                        "Remote lock/unlock setup requested for account=%s", data.get("email")
                    )
                    return await self._async_start_remote_lock_setup(data)

                # Unticking the box disables the lock entity again. device_id
                # and srp_pincode are left in place (both are idempotent -
                # device_id stays registered, srp_pincode stays the account's
                # SRP PIN) so re-enabling later won't require the OTP flow
                # again unless the user wants to change the PIN.
                if not setup_remote_lock and data.get("remote_lock_enabled"):
                    _LOGGER.info(
                        "Remote lock/unlock disabled for account=%s", data.get("email")
                    )
                    data["remote_lock_enabled"] = False

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
            vol.Required(
                "setup_remote_lock", default=bool(self._config_entry.data.get("remote_lock_enabled", False))
            ): bool,
        })

    async def _async_start_remote_lock_setup(self, data):
        """Log in, find the first vehicle that supports remote door locking,
        generate/reuse a device id, and request the email OTP needed to
        register this integration as a trusted device for that vehicle."""
        errors = {}

        kamereon_session = NCISession(region=data["region"])
        try:
            _LOGGER.debug("Logging in to look up lockable vehicles for account=%s", data.get("email"))
            await self.hass.async_add_executor_job(
                kamereon_session.login, data.get("email"), data.get("password")
            )
            vehicles = await self.hass.async_add_executor_job(kamereon_session.fetch_vehicles)
            _LOGGER.debug("Found %d vehicle(s): %s", len(vehicles), [v.vin for v in vehicles])
        except Exception:
            _LOGGER.exception("Login/vehicle lookup failed while starting remote lock/unlock setup")
            errors["base"] = "auth_error"
            vehicles = []

        vehicle = next((v for v in vehicles if Feature.APP_DOOR_LOCKING in v.features), None)
        if not errors and vehicle is None:
            _LOGGER.warning(
                "No vehicle on account=%s supports APP_DOOR_LOCKING (checked %d vehicle(s))",
                data.get("email"), len(vehicles)
            )
            errors["base"] = "no_lockable_vehicle"

        if errors:
            self.hass.config_entries.async_update_entry(self._config_entry, data=data)
            return self.async_show_form(
                step_id="init", data_schema=self._init_schema(), errors=errors
            )

        device_id = data.get("device_id") or secrets.token_hex(8)
        _LOGGER.info("Using device_id=%s for vin=%s (%s)",
                     device_id, vehicle.vin, "reused" if data.get("device_id") else "newly generated")
        await self.hass.async_add_executor_job(vehicle.generate_device_otp, device_id)
        _LOGGER.info("Device OTP email requested for vin=%s; awaiting code from user", vehicle.vin)

        self._pending_data = data
        self._pending_vehicle = vehicle
        self._pending_device_id = device_id

        return self.async_show_form(
            step_id="remote_lock_otp", data_schema=REMOTE_LOCK_OTP_SCHEMA
        )

    async def async_step_remote_lock_otp(self, options):
        errors = {}

        if options is not None:
            vehicle = self._pending_vehicle
            otp = options["otp"].strip()
            pincode = options["pincode"].strip()
            _LOGGER.debug(
                "Submitted remote lock/unlock setup form for vin=%s: otp_len=%d pincode_len=%d",
                vehicle.vin, len(otp), len(pincode)
            )

            # otp: 6-digit numeric code emailed by generate-device-otp.
            # pincode: 4-digit numeric SRP PIN (matches the MyNISSAN app's own
            # PIN entry screens - android:maxLength="4" inputType="number").
            if not (otp.isdigit() and len(otp) == 6):
                _LOGGER.warning("Rejecting OTP: expected 6 digits, got len=%d", len(otp))
                errors["otp"] = "otp_invalid"

            if pincode != options["pincode_confirm"].strip():
                errors["pincode_confirm"] = "pincode_mismatch"
            elif not (pincode.isdigit() and len(pincode) == 4):
                _LOGGER.warning("Rejecting PIN: expected 4 digits, got len=%d", len(pincode))
                errors["pincode"] = "pincode_invalid"

            if not errors:
                _LOGGER.info("Submitting device registration for vin=%s device_id=%s",
                             vehicle.vin, self._pending_device_id)
                try:
                    await self.hass.async_add_executor_job(
                        vehicle.register_device, self._pending_device_id, otp
                    )
                except Exception:
                    _LOGGER.exception(
                        "Device registration failed for vin=%s (device_id=%s)",
                        vehicle.vin, self._pending_device_id
                    )
                    errors["base"] = "device_registration_error"
                else:
                    _LOGGER.info("Device registration succeeded for vin=%s", vehicle.vin)

            if not errors:
                _LOGGER.info("Enrolling SRP PIN for vin=%s (separate from device registration above)", vehicle.vin)
                try:
                    await self.hass.async_add_executor_job(
                        vehicle.initiate_srp, pincode
                    )
                except Exception:
                    _LOGGER.exception("SRP PIN enrollment failed for vin=%s", vehicle.vin)
                    errors["base"] = "srp_enrollment_error"
                else:
                    _LOGGER.info("SRP PIN enrollment succeeded for vin=%s", vehicle.vin)

            if not errors:
                data = self._pending_data
                data["device_id"] = self._pending_device_id
                data["srp_pincode"] = pincode
                data["remote_lock_enabled"] = True
                self.hass.config_entries.async_update_entry(
                    self._config_entry, data=data
                )
                _LOGGER.info("Remote lock/unlock setup complete for vin=%s", vehicle.vin)
                return self.async_create_entry(title="", data={})

        return self.async_show_form(
            step_id="remote_lock_otp", data_schema=REMOTE_LOCK_OTP_SCHEMA, errors=errors
        )
