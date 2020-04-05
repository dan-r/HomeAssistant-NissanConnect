"""Support for Kamereon car locks."""
import logging

from homeassistant.components.lock import LockDevice
from homeassistant.const import STATE_UNKNOWN

from . import KamereonEntity
from .kamereon import Door, LockStatus

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, vehicle=None):
    """Set up the Kamereon lock."""
    if vehicle is None:
        return

    async_add_entities([KamereonLock(vehicle)])


class KamereonLock(KamereonEntity, LockDevice):
    """Represents a car lock."""

    @property
    def _entity_name(self):
        return 'lock'

    @property
    def is_locked(self):
        """Return true if lock is locked."""
        if self.vehicle.lock_status is None:
            return STATE_UNKNOWN
        return self.vehicle.lock_status is LockStatus.LOCKED

    async def async_lock(self, **kwargs):
        """Lock the car."""
        self.vehicle.lock()

    async def async_unlock(self, **kwargs):
        """Unlock the car."""
        self.vehicle.unlock()

    @property
    def device_state_attributes(self):
        a = KamereonEntity.device_state_attributes.fget(self)
        lock_status = self.vehicle.lock_status
        if lock_status is None:
            lock_status = STATE_UNKNOWN
        else:
            lock_status = lock_status.value
        a.update({
            'last_updated': self.vehicle.lock_status_last_updated,
            'lock_status': lock_status,
        })