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
from .const import DOMAIN, DATA_VEHICLES, DATA_COORDINATOR_FETCH, DATA_COORDINATOR_STATISTICS
_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config, async_add_entities):
    """Set up the Kamereon sensors."""
    data = hass.data[DOMAIN][DATA_VEHICLES]
    coordinator = hass.data[DOMAIN][DATA_COORDINATOR_FETCH]
    coordinator_stats = hass.data[DOMAIN][DATA_COORDINATOR_STATISTICS]

    entities = []

    imperial_distance = config.data.get("imperial_distance", False)

    for vehicle in data:
        if Feature.BATTERY_STATUS in data[vehicle].features or data[vehicle].range_hvac_on is not None:
            entities += [RangeSensor(coordinator, data[vehicle], True, imperial_distance),
                         TimestampSensor(coordinator, data[vehicle], 'battery_status_last_updated', 'last_updated', 'mdi:clock-time-eleven-outline')]
        if Feature.BATTERY_STATUS in data[vehicle].features:
            entities += [BatteryLevelSensor(coordinator, data[vehicle]),
                         RangeSensor(coordinator, data[vehicle], False, imperial_distance),
                         ChargeTimeRequiredSensor(coordinator, data[vehicle], ChargingSpeed.NORMAL),
                         ChargeTimeRequiredSensor(coordinator, data[vehicle], ChargingSpeed.FAST)]
        if data[vehicle].internal_temperature is not None:
            entities.append(InternalTemperatureSensor(coordinator, data[vehicle]))
        if data[vehicle].external_temperature is not None:
            entities.append(ExternalTemperatureSensor(coordinator, data[vehicle]))
        if Feature.DRIVING_JOURNEY_HISTORY in data[vehicle].features:
            entities += [
                StatisticSensor(coordinator_stats, data[vehicle], 'daily', lambda x: x.total_distance, 'daily_distance', 'mdi:map-marker-distance', SensorDeviceClass.DISTANCE, UnitOfLength.KILOMETERS, 0, imperial_distance),
                StatisticSensor(coordinator_stats, data[vehicle], 'daily', lambda x: x.trip_count, 'daily_trips', 'mdi:hiking', None, None, 0),
                StatisticSensor(coordinator_stats, data[vehicle], 'monthly', lambda x: x.total_distance, 'monthly_distance', 'mdi:map-marker-distance', SensorDeviceClass.DISTANCE, UnitOfLength.KILOMETERS, 0, imperial_distance),
                StatisticSensor(coordinator_stats, data[vehicle], 'monthly', lambda x: x.trip_count, 'monthly_trips', 'mdi:hiking',  None, None, 0),
            ]
            if Feature.BATTERY_STATUS in data[vehicle].features:
                entities += [
                    StatisticSensor(coordinator_stats, data[vehicle], 'daily', lambda x: x.total_distance / x.consumed_electricity, 'daily_efficiency', 'mdi:ev-station', SensorDeviceClass.DISTANCE, UnitOfLength.KILOMETERS, 2, imperial_distance),
                    StatisticSensor(coordinator_stats, data[vehicle], 'monthly', lambda x: x.total_distance / x.consumed_electricity, 'monthly_efficiency', 'mdi:ev-station', SensorDeviceClass.DISTANCE, UnitOfLength.KILOMETERS, 2, imperial_distance),
                ]

        entities.append(OdometerSensor(coordinator, data[vehicle], imperial_distance))

    async_add_entities(entities, update_before_add=True)


class BatteryLevelSensor(KamereonEntity, SensorEntity):
    _attr_translation_key = "battery_level"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE

    def __init__(self, coordinator, vehicle):
        KamereonEntity.__init__(self, coordinator, vehicle)
        
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
    _attr_translation_key = "internal_temperature"
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
    _attr_translation_key = "external_temperature"
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
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS

    def __init__(self, coordinator, vehicle, hvac, imperial_distance):
        if imperial_distance:
            self._attr_suggested_unit_of_measurement = UnitOfLength.MILES

        self._attr_translation_key = "range_ac_on" if hvac else "range_ac_off"
        KamereonEntity.__init__(self, coordinator, vehicle)
        self.hvac = hvac

    @property
    def native_value(self):
        """Return the state."""
        val = getattr(self.vehicle, 'range_hvac_{}'.format(
            'on' if self.hvac else 'off'))
        return val

    @property
    def icon(self):
        """Icon of the sensor."""
        return "mdi:map-marker-distance"


class OdometerSensor(KamereonEntity, SensorEntity):
    _attr_translation_key = "odometer"
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS

    def __init__(self, coordinator, vehicle, imperial_distance):
        if imperial_distance:
            self._attr_suggested_unit_of_measurement = UnitOfLength.MILES

        self._state = None

        KamereonEntity.__init__(self, coordinator, vehicle)

    @callback
    def _handle_coordinator_update(self) -> None:
        new_state = getattr(self.vehicle, "total_mileage")

        # This sometimes goes backwards? So only accept a positive odometer delta
        if new_state is not None and new_state > (self._state or 0):
            _LOGGER.debug(f"Updating odometer state")
            
            self._state = new_state
            self.async_write_ha_state()

    @property
    def native_value(self):
        """Return the state."""
        return self._state

    @property
    def icon(self):
        """Icon of the sensor."""
        return "mdi:counter"


class StatisticSensor(KamereonEntity, SensorEntity):
    def __init__(self, coordinator, vehicle, key, func, translation_key, icon, device_class, unit, precision, imperial_distance=False):
        self._attr_device_class = device_class
        self._attr_native_unit_of_measurement = unit
        self._attr_suggested_display_precision = precision
        if imperial_distance:
            self._attr_suggested_unit_of_measurement = UnitOfLength.MILES
        self._attr_translation_key = translation_key
        self._icon = icon
        self._key = key
        self._lambda = func
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

        # For statistic sensors, default to 0 on error
        try:
            self._state = self._lambda(summary[0])
        except:
            self._state = 0

        self.async_write_ha_state()

    @property
    def icon(self):
        """Icon of the sensor."""
        return self._icon


class ChargeTimeRequiredSensor(KamereonEntity, SensorEntity):
    _attr_translation_key = "charge_time"
    _attr_device_class = SensorDeviceClass.DURATION
    _attr_native_unit_of_measurement = UnitOfTime.MINUTES

    CHARGING_SPEED_NAME = {
        ChargingSpeed.FASTEST: '50kw',
        ChargingSpeed.FAST: '6kw',
        ChargingSpeed.NORMAL: '3kw',
        ChargingSpeed.SLOW: '1kw',
    }

    def __init__(self, coordinator, vehicle, charging_speed):
        self.charging_speed = charging_speed
        self._attr_translation_key = "charge_time_" + self.CHARGING_SPEED_NAME[charging_speed]
        KamereonEntity.__init__(self, coordinator, vehicle)

    @property
    def native_value(self):
        """Return the state."""
        return self.vehicle.charge_time_required_to_full[self.charging_speed]

    @property
    def icon(self):
        """Icon of the sensor."""
        return "mdi:battery-clock"


class TimestampSensor(KamereonEntity, SensorEntity):
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, coordinator, vehicle, attribute, translation_key, icon):
        self._attr_translation_key = translation_key
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
