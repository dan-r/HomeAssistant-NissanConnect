"""Support for Kamereon cars."""
import logging

from homeassistant.components.binary_sensor import DEVICE_CLASSES, BinarySensorDevice
from homeassistant.const import STATE_UNKNOWN

from . import KamereonEntity
from .kamereon import ChargingStatus, Door, LockStatus, PluggedStatus

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, vehicle=None):
    """Set up the Kamereon sensors."""
    if vehicle is None:
        return
    async_add_entities([
        ChargingStatusEntity(vehicle),
        PluggedStatusEntity(vehicle),
        FuelLowWarningEntity(vehicle),
        DoorEntity(vehicle, Door.FRONT_LEFT),
        DoorEntity(vehicle, Door.FRONT_RIGHT),
        DoorEntity(vehicle, Door.REAR_LEFT),
        DoorEntity(vehicle, Door.REAR_RIGHT),
        DoorEntity(vehicle, Door.HATCH),
        ])


class ChargingStatusEntity(KamereonEntity, BinarySensorDevice):
    """Representation of charging status."""

    @property
    def _entity_name(self):
        return 'charging'

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:{}'.format('battery-charging' if self.is_on else 'battery-off')

    @property
    def is_on(self):
        """Return True if the binary sensor is on."""
        if self.vehicle.charging is None:
            return STATE_UNKNOWN
        return self.vehicle.charging is ChargingStatus.CHARGING

    @property
    def device_class(self):
        """Return the class of this sensor."""
        return 'power'

    @property
    def device_state_attributes(self):
        a = KamereonEntity.device_state_attributes.fget(self)
        a.update({
            'charging_speed': self.vehicle.charging_speed.value,
            'last_updated': self.vehicle.battery_status_last_updated,
        })
        return a


class PluggedStatusEntity(KamereonEntity, BinarySensorDevice):
    """Representation of plugged status."""

    @property
    def _entity_name(self):
        return 'plugged_in'

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:{}'.format('power-plug' if self.is_on else 'power-plug-off')

    @property
    def is_on(self):
        """Return True if the binary sensor is on."""
        if self.vehicle.plugged_in is None:
            return STATE_UNKNOWN
        return self.vehicle.plugged_in is PluggedStatus.PLUGGED

    @property
    def device_class(self):
        """Return the class of this sensor."""
        return 'plug'

    @property
    def device_state_attributes(self):
        a = KamereonEntity.device_state_attributes.fget(self)
        a.update({
            'plugged_in_time': self.vehicle.plugged_in_time,
            'unplugged_time': self.vehicle.unplugged_time,
            'last_updated': self.vehicle.battery_status_last_updated,
        })
        return a


class FuelLowWarningEntity(KamereonEntity, BinarySensorDevice):
    """Representation of fuel low warning status."""

    @property
    def _entity_name(self):
        return 'fuel_low'

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:fuel'

    @property
    def is_on(self):
        """Return True if the binary sensor is on."""
        if self.vehicle.fuel_low_warning is None:
            return STATE_UNKNOWN
        return self.vehicle.fuel_low_warning

    @property
    def device_class(self):
        """Return the class of this sensor."""
        return 'safety'


class DoorEntity(KamereonEntity, BinarySensorDevice):
    """Representation of a door (or hatch)."""

    def __init__(self, vehicle, door):
        KamereonEntity.__init__(self, vehicle)
        self.door = door

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:car-door'

    @property
    def _entity_name(self):
        return '{}_door'.format(self.door.value)

    @property
    def is_on(self):
        """Return True if the binary sensor is open."""
        if self.door not in self.vehicle.door_status or self.vehicle.door_status[self.door] is None:
            return STATE_UNKNOWN
        return self.vehicle.door_status[self.door] == LockStatus.OPEN

    @property
    def device_class(self):
        """Return the class of this sensor."""
        return 'door'