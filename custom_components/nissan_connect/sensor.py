import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    UnitOfTemperature
)
from homeassistant.const import PERCENTAGE, UnitOfLength, UnitOfTime
from .base import KamereonEntity
from .kamereon import ChargingSpeed, Feature
from .const import DOMAIN, DATA_VEHICLES, DATA_COORDINATOR
_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config, async_add_entities):
    """Set up the Kamereon sensors."""
    data = hass.data[DOMAIN][DATA_VEHICLES]
    coordinator = hass.data[DOMAIN][DATA_COORDINATOR]

    entities = []

    for vehicle in data:
        if Feature.BATTERY_STATUS in data[vehicle].features:
            entities.append(BatteryLevelSensor(coordinator, data[vehicle]))
            entities.append(RangeSensor(coordinator, data[vehicle], True))
            entities.append(RangeSensor(coordinator, data[vehicle], False))
            entities.append(ChargeTimeRequiredSensor(coordinator, data[vehicle], ChargingSpeed.SLOW))
            entities.append(ChargeTimeRequiredSensor(coordinator, data[vehicle], ChargingSpeed.NORMAL))
            entities.append(ChargeTimeRequiredSensor(coordinator, data[vehicle], ChargingSpeed.FAST))
            entities.append(TimestampSensor(coordinator, data[vehicle], 'battery_status_last_updated', 'Last Updated', 'mdi:clock-time-eleven-outline'))
        if data[vehicle].internal_temperature is not None:
            entities.append(InternalTemperatureSensor(coordinator, data[vehicle]))
        if data[vehicle].external_temperature is not None:
            entities.append(ExternalTemperatureSensor(coordinator, data[vehicle]))

        entities.append(OdometerSensor(coordinator, data[vehicle]))

    async_add_entities(entities, update_before_add=True)


class BatteryLevelSensor(KamereonEntity, SensorEntity):
    _attr_name = "Battery Level"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE

    @property
    def state(self):
        """Return the state."""
        return self.vehicle.battery_level
    
    @property
    def icon(self):
        """Icon of the sensor."""
        return "mdi:battery"

    @property
    def device_state_attributes(self):
        """Return device specific state attributes."""
        a = KamereonEntity.device_state_attributes.fget(self)
        a.update({
            'battery_capacity': self.vehicle.battery_capacity,
            'battery_level': self.vehicle.battery_level,
        })

class InternalTemperatureSensor(KamereonEntity, SensorEntity):
    _attr_name = "Internal Temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def native_value(self):
        """Return the state."""
        return self.vehicle.internal_temperature
    
    @property
    def icon(self):
        """Icon of the sensor."""
        return "mdi:thermometer"

    @property
    def device_state_attributes(self):
        """Return device specific state attributes."""
        a = KamereonEntity.device_state_attributes.fget(self)
        a.update({
            'battery_capacity': self.vehicle.battery_capacity,
            'battery_bar_level': self.vehicle.battery_bar_level,
        })
        return a

class ExternalTemperatureSensor(KamereonEntity, SensorEntity):
    _attr_name = "External Temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def native_value(self):
        """Return the state."""
        return self.vehicle.external_temperature

    @property
    def icon(self):
        """Icon of the sensor."""
        return "mdi:thermometer"
    
    @property
    def device_state_attributes(self):
        """Return device specific state attributes."""
        a = KamereonEntity.device_state_attributes.fget(self)
        a.update({
            'battery_capacity': self.vehicle.battery_capacity,
            'battery_bar_level': self.vehicle.battery_bar_level,
        })
        return a

class RangeSensor(KamereonEntity, SensorEntity):
    _attr_name = "Range"
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS

    def __init__(self, coordinator, vehicle, hvac):
        self._attr_name = "Range (AC On)" if hvac else "Range (AC Off)"
        KamereonEntity.__init__(self, coordinator, vehicle)
        self.hvac = hvac

    @property
    def native_value(self):
        """Return the state."""
        val = getattr(self.vehicle, 'range_hvac_{}'.format('on' if self.hvac else 'off'))
        return val
    
    @property
    def icon(self):
        """Icon of the sensor."""
        return "mdi:map-marker-distance"

class OdometerSensor(KamereonEntity, SensorEntity):
    _attr_name = "Odometer"
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS

    @property
    def native_value(self):
        """Return the state."""
        return getattr(self.vehicle, "total_mileage")
    
    @property
    def icon(self):
        """Icon of the sensor."""
        return "mdi:gauge"

class ChargeTimeRequiredSensor(KamereonEntity, SensorEntity):
    _attr_name = "Charge Time"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    CHARGING_SPEED_NAME = {
        ChargingSpeed.FASTEST: 'fastest',
        ChargingSpeed.FAST: 'fast',
        ChargingSpeed.NORMAL: 'normal',
        ChargingSpeed.SLOW: 'slow',
    }

    def __init__(self, coordinator, vehicle, charging_speed):
        self._attr_name = f"Charge Time ({self.CHARGING_SPEED_NAME[charging_speed]})"
        KamereonEntity.__init__(self, coordinator, vehicle)
        self.charging_speed = charging_speed

    @property
    def native_value(self):
        """Return the state."""
        return self.vehicle.charge_time_required_to_full[self.charging_speed]
 
    @property
    def icon(self):
        """Icon of the sensor."""
        return "mdi:timer-sand-complete"

class TimestampSensor(KamereonEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, vehicle, attribute, name, icon):
        self._attr_name = name
        self._icon = icon
        KamereonEntity.__init__(self, coordinator, vehicle)
        self.attribute = attribute

    @property
    def icon(self):
        """Icon of the sensor."""
        return self._icon
    
    @property
    def state(self):
        """Return the state."""
        val = getattr(self.vehicle, self.attribute)
        if val is None:
            return None
        return val.isoformat()