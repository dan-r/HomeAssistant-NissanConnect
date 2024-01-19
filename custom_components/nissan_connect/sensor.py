import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    UnitOfTemperature
)
from homeassistant.core import callback
from homeassistant.const import PERCENTAGE, UnitOfLength, UnitOfTime
from .base import KamereonEntity
from .kamereon import ChargingSpeed, Feature
from .const import DOMAIN, DATA_VEHICLES, DATA_COORDINATOR, DATA_COORDINATOR_STATISTICS
_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, config, async_add_entities):
    """Set up the Kamereon sensors."""
    data = hass.data[DOMAIN][DATA_VEHICLES]
    coordinator = hass.data[DOMAIN][DATA_COORDINATOR]
    coordinator_stats = hass.data[DOMAIN][DATA_COORDINATOR_STATISTICS]

    entities = []

    for vehicle in data:
        if Feature.BATTERY_STATUS in data[vehicle].features:
            entities.append(BatteryLevelSensor(coordinator, data[vehicle]))
            entities.append(RangeSensor(coordinator, data[vehicle], True))
            entities.append(RangeSensor(coordinator, data[vehicle], False))
            entities.append(ChargeTimeRequiredSensor(coordinator, data[vehicle], ChargingSpeed.NORMAL))
            entities.append(ChargeTimeRequiredSensor(coordinator, data[vehicle], ChargingSpeed.FAST))
            entities.append(TimestampSensor(coordinator, data[vehicle], 'battery_status_last_updated', 'Last Updated', 'mdi:clock-time-eleven-outline'))
        if data[vehicle].internal_temperature is not None:
            entities.append(InternalTemperatureSensor(coordinator, data[vehicle]))
        if data[vehicle].external_temperature is not None:
            entities.append(ExternalTemperatureSensor(coordinator, data[vehicle]))
        if Feature.DRIVING_JOURNEY_HISTORY in data[vehicle].features:
            entities.append(StatisticSensor(coordinator_stats, data[vehicle], 'daily', 'Daily Distance' ))
            entities.append(StatisticSensor(coordinator_stats, data[vehicle], 'monthly', 'Monthly Distance' ))

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
        return "mdi:counter"
    
class StatisticSensor(KamereonEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator, vehicle, key, name):
        self._attr_name = name
        self._key = key
        self._state = None
        self._attributes = {}
        KamereonEntity.__init__(self, coordinator, vehicle)

    @property
    def native_value(self):
        """Return the state."""
        return self._state
    
    @property
    def extra_state_attributes(self):
        """Attributes of the sensor."""
        return self._attributes
    
    @callback
    def _handle_coordinator_update(self) -> None:
        if self.coordinator.data is None or self.vehicle.vin not in self.coordinator.data:
            return
        
        summary = self.coordinator.data[self.vehicle.vin][self._key]
        
        # No summaries yet, return 0
        if len(summary) == 0:
            self._state = 0
            self.async_write_ha_state()
            return
        
        summary = summary[0]
        
        self._state = summary.total_distance
        self._attributes = {
            'trip_count': summary.trip_count,
            'duration': summary.total_duration,
            'consumed_electricity': summary.consumed_electricity,
            'kwh_per_100km': (summary.consumed_electricity / summary.total_distance) * 100,
            'miles_per_kwh': (summary.total_distance * 0.6214) / summary.consumed_electricity

        }

        self.async_write_ha_state()
    
    @property
    def icon(self):
        """Icon of the sensor."""
        return "mdi:calendar-today"

class ChargeTimeRequiredSensor(KamereonEntity, SensorEntity):
    _attr_name = "Charge Time"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    CHARGING_SPEED_NAME = {
        ChargingSpeed.FASTEST: '50kW',
        ChargingSpeed.FAST: '6kW',
        ChargingSpeed.NORMAL: '3kW',
        ChargingSpeed.SLOW: '1kW',
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
