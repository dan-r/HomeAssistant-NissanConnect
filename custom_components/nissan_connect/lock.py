"""Remote lock support for NissanConnect vehicles."""

from homeassistant.components.lock import LockEntity
from homeassistant.const import ATTR_CODE
from homeassistant.exceptions import HomeAssistantError

from .base import KamereonEntity
from .const import (
    CONF_REMOTE_LOCK,
    CONF_REMOTE_LOCK_DEVICE_ID,
    CONF_REMOTE_LOCK_STATUS,
    DATA_COORDINATOR_FETCH,
    DATA_VEHICLES,
    DOMAIN,
    REMOTE_LOCK_STATUS_ENABLED,
)
from .kamereon import LockStatus, RemoteLockError


async def async_setup_entry(hass, config, async_add_entities):
    """Set up remote locks for configured vehicles."""
    account_id = config.data["email"]
    vehicles = hass.data[DOMAIN][account_id][DATA_VEHICLES]
    coordinator = hass.data[DOMAIN][account_id][DATA_COORDINATOR_FETCH]
    remote_lock = config.data.get(CONF_REMOTE_LOCK, {})

    entities = []
    for vin, vehicle in vehicles.items():
        vehicle_config = remote_lock.get(vin, {})
        if (
                vehicle.supports_remote_lock_setup
                and vehicle_config.get(CONF_REMOTE_LOCK_STATUS)
                == REMOTE_LOCK_STATUS_ENABLED
                and vehicle_config.get(CONF_REMOTE_LOCK_DEVICE_ID)):
            entities.append(NissanLock(
                coordinator,
                vehicle,
                hass,
                vehicle_config[CONF_REMOTE_LOCK_DEVICE_ID],
            ))

    async_add_entities(entities, update_before_add=True)


class NissanLock(KamereonEntity, LockEntity):
    """Lock and unlock a Nissan vehicle."""

    _attr_code_format = r"^\d{4}$"
    _attr_translation_key = "doors"

    def __init__(self, coordinator, vehicle, hass, device_id):
        super().__init__(coordinator, vehicle)
        self._hass = hass
        self._device_id = device_id

    @property
    def is_locked(self):
        if self.vehicle.lock_status is None:
            return None
        return self.vehicle.lock_status is LockStatus.LOCKED

    async def async_lock(self, **kwargs):
        await self._async_run_command(self.vehicle.lock, kwargs.get(ATTR_CODE))

    async def async_unlock(self, **kwargs):
        await self._async_run_command(
            self.vehicle.unlock, kwargs.get(ATTR_CODE))

    async def _async_run_command(self, command, pin):
        if pin is None:
            raise HomeAssistantError("A four-digit Nissan PIN is required")

        is_locking = command == self.vehicle.lock
        self._attr_is_locking = is_locking
        self._attr_is_unlocking = not is_locking
        self.async_write_ha_state()
        try:
            await self._hass.async_add_executor_job(
                command,
                pin,
                self._device_id,
            )
        except RemoteLockError as error:
            raise HomeAssistantError(str(error)) from error
        finally:
            self._attr_is_locking = False
            self._attr_is_unlocking = False
            self.async_write_ha_state()

        await self.coordinator.async_refresh()