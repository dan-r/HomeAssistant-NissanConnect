"""Support for Kamereon car sensors."""
import logging

from homeassistant.const import (
    DEVICE_CLASS_BATTERY, DEVICE_CLASS_POWER, DEVICE_CLASS_TEMPERATURE,
    DEVICE_CLASS_TIMESTAMP, LENGTH_KILOMETERS, POWER_WATT, STATE_UNKNOWN,
    TEMP_CELSIUS, TIME_MINUTES, UNIT_PERCENTAGE, VOLUME_LITERS)

from . import DATA_KEY, KamereonEntity
from .kamereon import ChargingSpeed

_LOGGER = logging.getLogger(__name__)


async def async_setup_platform(hass, config, async_add_entities, vehicle=None):
    """Set up the Kamereon sensors."""
    if vehicle is None:
        return
    async_add_entities([
        BatteryLevelSensor(vehicle),
        BatteryTemperatureSensor(vehicle),
        ChargingPowerSensor(vehicle),
        ChargingSpeedSensor(vehicle),
        ChargeTimeRequiredSensor(vehicle, ChargingSpeed.FAST),
        ChargeTimeRequiredSensor(vehicle, ChargingSpeed.NORMAL),
        ChargeTimeRequiredSensor(vehicle, ChargingSpeed.SLOW),
        ExternalTemperatureSensor(vehicle),
        RangeSensor(vehicle, hvac=True),
        RangeSensor(vehicle, hvac=False),
        TimestampSensor(vehicle, 'plugged_in_time', 'plugged in time'),
        TimestampSensor(vehicle, 'unplugged_time', 'unplugged time'),
        TimestampSensor(vehicle, 'battery_status_last_updated', 'battery status last updated time'),
        TimestampSensor(vehicle, 'location_last_updated', 'location last updated time'),
        TimestampSensor(vehicle, 'lock_status_last_updated', 'lock status last updated time'),
        FuelLevelSensor(vehicle),
        FuelQuantitySensor(vehicle),
        MileageSensor(vehicle, total=False),
        MileageSensor(vehicle, total=True),
        ])


class BatteryLevelSensor(KamereonEntity):
    """Representation of a Kamereon car sensor."""

    @property
    def state(self):
        """Return the state."""
        return self.vehicle.battery_bar_level

    @property
    def _entity_name(self):
        return 'battery level'

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return UNIT_PERCENTAGE

    @property
    def device_class(self):
        """Return the class of this sensor."""
        return DEVICE_CLASS_BATTERY

    @property
    def device_state_attributes(self):
        """Return device specific state attributes."""
        a = KamereonEntity.device_state_attributes.fget(self)
        a.update({
            'battery_capacity': self.vehicle.battery_capacity,
            'battery_level': self.vehicle.battery_level,
        })


class FuelLevelSensor(KamereonEntity):
    """Representation of a Kamereon car sensor."""

    @property
    def state(self):
        """Return the state."""
        if self.vehicle.fuel_level is None:
            return STATE_UNKNOWN
        return self.vehicle.fuel_level

    @property
    def _entity_name(self):
        return 'fuel level'

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return UNIT_PERCENTAGE


class FuelQuantitySensor(KamereonEntity):
    """Representation of a Kamereon car sensor."""

    @property
    def state(self):
        """Return the state."""
        if self.vehicle.fuel_quantity is None:
            return STATE_UNKNOWN
        return self.vehicle.fuel_quantity

    @property
    def _entity_name(self):
        return 'fuel quantity'

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return VOLUME_LITERS


class BatteryTemperatureSensor(KamereonEntity):
    """Representation of a Kamereon car sensor."""

    @property
    def state(self):
        """Return the state."""
        if self.vehicle.battery_temperature is None:
            return STATE_UNKNOWN
        return self.vehicle.battery_temperature

    @property
    def _entity_name(self):
        return 'battery temperature'

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return TEMP_CELSIUS

    @property
    def device_class(self):
        """Return the class of this sensor."""
        return DEVICE_CLASS_TEMPERATURE

    @property
    def device_state_attributes(self):
        """Return device specific state attributes."""
        a = KamereonEntity.device_state_attributes.fget(self)
        a.update({
            'battery_capacity': self.vehicle.battery_capacity,
            'battery_bar_level': self.vehicle.battery_bar_level,
        })
        return a


class ExternalTemperatureSensor(KamereonEntity):
    """Representation of a Kamereon car sensor."""

    @property
    def state(self):
        """Return the state."""
        if self.vehicle.external_temperature is None:
            return STATE_UNKNOWN
        return self.vehicle.external_temperature

    @property
    def _entity_name(self):
        return 'external temperature'

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return TEMP_CELSIUS

    @property
    def device_class(self):
        """Return the class of this sensor."""
        return DEVICE_CLASS_TEMPERATURE


class ChargingPowerSensor(KamereonEntity):
    """Representation of a Kamereon car sensor."""

    @property
    def state(self):
        """Return the state."""
        if self.vehicle.instantaneous_power is None:
            return STATE_UNKNOWN
        return self.vehicle.instantaneous_power * 1000

    @property
    def _entity_name(self):
        return 'charging power'

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return POWER_WATT

    @property
    def device_class(self):
        """Return the class of this sensor."""
        return DEVICE_CLASS_POWER

    @property
    def device_state_attributes(self):
        """Return device specific state attributes."""
        a = KamereonEntity.device_state_attributes.fget(self)
        a.update({
            'battery_capacity': self.vehicle.battery_capacity,
            'battery_bar_level': self.vehicle.battery_bar_level,
        })


class ChargingSpeedSensor(KamereonEntity):
    """Representation of a Kamereon car sensor."""

    @property
    def _entity_name(self):
        return 'charging speed'

    @property
    def state(self):
        """Return the state."""
        if self.vehicle.charging_speed is None:
            return STATE_UNKNOWN
        return self.vehicle.charging_speed.value


class ChargeTimeRequiredSensor(KamereonEntity):
    """Representation of a Kamereon car sensor."""

    CHARGING_SPEED_NAME = {
        ChargingSpeed.FAST: 'fast',
        ChargingSpeed.NORMAL: 'normal',
        ChargingSpeed.SLOW: 'slow',
    }

    def __init__(self, vehicle, charging_speed):
        KamereonEntity.__init__(self, vehicle)
        self.charging_speed = charging_speed

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return TIME_MINUTES

    @property
    def _entity_name(self):
        return 'charging time required to full ({})'.format(self.CHARGING_SPEED_NAME[self.charging_speed])

    @property
    def state(self):
        """Return the state."""
        if self.vehicle.charge_time_required_to_full[self.charging_speed] is None:
            return STATE_UNKNOWN
        return self.vehicle.charge_time_required_to_full[self.charging_speed]


class RangeSensor(KamereonEntity):
    """Representation of a Kamereon car sensor."""

    def __init__(self, vehicle, hvac):
        KamereonEntity.__init__(self, vehicle)
        self.hvac = hvac

    @property
    def _entity_name(self):
        return 'range (HVAC {})'.format('on' if self.hvac else 'off')

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return LENGTH_KILOMETERS

    @property
    def state(self):
        """Return the state."""
        val = getattr(self.vehicle, 'range_hvac_{}'.format('on' if self.hvac else 'off'))
        if val is None:
            return STATE_UNKNOWN
        return val


class MileageSensor(KamereonEntity):
    """Representation of a Kamereon car sensor."""

    def __init__(self, vehicle, total=False):
        KamereonEntity.__init__(self, vehicle)
        self.total = total

    @property
    def _entity_name(self):
        return '{}mileage'.format('total ' if self.total else '')

    @property
    def unit_of_measurement(self):
        """Return the unit of measurement."""
        return LENGTH_KILOMETERS

    @property
    def state(self):
        """Return the state."""
        val = getattr(self.vehicle, '{}mileage'.format('total_' if self.total else ''))
        if val is None:
            return STATE_UNKNOWN
        return val


class TimestampSensor(KamereonEntity):
    """Representation of a Kamereon car sensor."""

    def __init__(self, vehicle, attribute, name):
        KamereonEntity.__init__(self, vehicle)
        self.attribute = attribute
        self.__entity_name = name

    @property
    def _entity_name(self):
        return self.__entity_name

    @property
    def device_class(self):
        """Return the device class."""
        return DEVICE_CLASS_TIMESTAMP

    @property
    def state(self):
        """Return the state."""
        val = getattr(self.vehicle, self.attribute)
        if val is None:
            return STATE_UNKNOWN
        return val.isoformat()