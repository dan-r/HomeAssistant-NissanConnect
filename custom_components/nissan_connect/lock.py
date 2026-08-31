"""Support for Kamereon cars."""
import asyncio
import logging

from homeassistant.components.lock import LockEntity

from .base import KamereonEntity
from .kamereon import Feature, LockStatus
from .const import DOMAIN, DATA_VEHICLES, DATA_COORDINATOR_FETCH

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config, async_add_entities):
    account_id = config.data['email']

    data = hass.data[DOMAIN][account_id][DATA_VEHICLES]
    coordinator = hass.data[DOMAIN][account_id][DATA_COORDINATOR_FETCH]

    pincode = config.data.get('srp_pincode')
    remote_lock_enabled = config.data.get('remote_lock_enabled', False)

    entities = []
    for vehicle in data:
        if Feature.APP_DOOR_LOCKING not in data[vehicle].features:
            continue
        if not pincode or not remote_lock_enabled:
            # The vehicle supports remote lock/unlock, but this account
            # hasn't completed device registration / SRP PIN setup for it
            # yet, or it's been disabled again (see the "Enable remote
            # lock/unlock" integration option) - device_id/srp_pincode are
            # kept around even when disabled, so check the flag too.
            _LOGGER.debug(
                "Not adding lock entity for %s: remote lock/unlock is not set up yet", vehicle
            )
            continue
        entities.append(KamereonLock(coordinator, data[vehicle], hass, pincode))

    async_add_entities(entities, update_before_add=True)


class KamereonLock(KamereonEntity, LockEntity):
    """Representation of a Kamereon vehicle's door lock."""
    _attr_translation_key = "lock"

    def __init__(self, coordinator, vehicle, hass, pincode):
        KamereonEntity.__init__(self, coordinator, vehicle)
        self._hass = hass
        self._pincode = pincode
        self._loop_mutex = False

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:car-door-lock' if self.is_locked else 'mdi:car-door-lock-open'

    @property
    def is_locked(self):
        if self.vehicle.lock_status is None:
            return None
        return self.vehicle.lock_status == LockStatus.LOCKED

    async def async_lock(self, **kwargs):
        await self._async_set_lock(True)

    async def async_unlock(self, **kwargs):
        await self._async_set_lock(False)

    async def _async_set_lock(self, locked: bool):
        action = self.vehicle.lock if locked else self.vehicle.unlock
        await self._hass.async_add_executor_job(action, self._pincode)
        self._hass.async_create_task(self._async_fetch_loop(locked))

    async def _async_fetch_loop(self, target_locked: bool):
        """Poll lock status for a while so the entity reflects the change
        without waiting for the next regular fetch interval."""
        if self._loop_mutex:
            return

        _LOGGER.debug("Beginning lock status fetch loop")
        self._loop_mutex = True
        target = LockStatus.LOCKED if target_locked else LockStatus.UNLOCKED

        try:
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(None, self.vehicle.refresh_lock_status)

            for _ in range(10):
                await asyncio.sleep(5)
                await loop.run_in_executor(None, self.vehicle.fetch_lock_status)
                await self.coordinator.async_refresh()

                if self.vehicle.lock_status == target:
                    _LOGGER.debug("Breaking out of lock status fetch loop")
                    break
        finally:
            self._loop_mutex = False
