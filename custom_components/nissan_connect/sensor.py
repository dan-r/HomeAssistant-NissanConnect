import logging
import math

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
)
from homeassistant.core import callback
from homeassistant.const import PERCENTAGE, EntityCategory, UnitOfLength, UnitOfPressure, UnitOfTemperature, UnitOfTime, UnitOfVolume
from homeassistant.components.sensor import SensorStateClass
from .base import KamereonEntity
from .kamereon import ChargingSpeed, Feature
from .const import DOMAIN, DATA_VEHICLES, DATA_COORDINATOR_FETCH, DATA_COORDINATOR_STATISTICS
_LOGGER = logging.getLogger(__name__)

# Nissan does not identify the app's composite Brake System, 12 V Battery or
# Electric Shift Control rows. Keep the underlying codes, including switches
# and EV-specific codes, without guessing a subsystem, severity or voltage.
RAW_LAMPS = {
    "brakeFluidWarning": "brake_fluid_warning_raw",
    "emergencyBrakingWarning": "emergency_braking_warning_raw",
    "batteryLowWarning": "battery_low_warning_raw",
    "batteryHighWarning": "battery_high_warning_raw",
    "evBatteryLevelWarning": "ev_battery_level_warning_raw",
    "oilPressureWarning": "oil_pressure_warning_raw",
    "oilPressureSwitch": "oil_pressure_switch_raw",
    "globalServWarning": "global_service_warning_raw",
    "globalStopWarning": "global_stop_warning_raw",
    "parkingLightWarning": "parking_light_warning_raw",
    "lampRequest": "lamp_request_raw",
    "afuFailure": "afu_failure_raw",
    "evAlertCrbsFailureDisplay": "ev_alert_crbs_failure_display_raw",
}
WHEELS = {"fl": "front_left", "fr": "front_right", "rl": "rear_left", "rr": "rear_right"}


async def async_setup_entry(hass, config, async_add_entities):
    """Set up the Kamereon sensors."""
    account_id = config.data['email']

    data = hass.data[DOMAIN][account_id][DATA_VEHICLES]
    coordinator = hass.data[DOMAIN][account_id][DATA_COORDINATOR_FETCH]
    coordinator_stats = hass.data[DOMAIN][account_id][DATA_COORDINATOR_STATISTICS]

    entities = []

    imperial_distance = config.data.get("imperial_distance", False)

    for vehicle in data:
        is_ze2 = data[vehicle].is_ze2_leaf
        if is_ze2:
            entities.append(RepeatClimateTargetSensor(coordinator, data[vehicle]))
            # Grey Car returns "invalid"; do not present that as a closed sunroof.
            entities.append(RawDiagnosticSensor(coordinator, data[vehicle], "security_status", "sunroofStatus", "sunroof_status_raw"))
            for field, name in RAW_LAMPS.items():
                entities.append(RawDiagnosticSensor(coordinator, data[vehicle], "warning_lamps", field, name))
            for prefix, position in WHEELS.items():
                entities.append(TyrePressureSensor(coordinator, data[vehicle], prefix, position))
                # The meaning of the per-wheel status codes is still undocumented.
                entities.append(RawDiagnosticSensor(coordinator, data[vehicle], "tyre_readings",
                                                    prefix + "Status", f"{position}_tyre_status_raw"))
        entities.append(TimestampSensor(coordinator, data[vehicle], 'last_updated', 'last_updated', 'mdi:clock-time-eleven-outline'))

        if Feature.BATTERY_STATUS in data[vehicle].features or data[vehicle].range_hvac_on is not None:
            entities.append(RangeSensor(coordinator, data[vehicle], True, imperial_distance))
        if Feature.BATTERY_STATUS in data[vehicle].features or (is_ze2 and data[vehicle].battery_level is not None):
            entities.append(BatteryLevelSensor(coordinator, data[vehicle]))
        if data[vehicle].charge_time_required_to_full[ChargingSpeed.NORMAL] is not None:
            entities += [ChargeTimeRequiredSensor(coordinator, data[vehicle], ChargingSpeed.NORMAL),
                         ChargeTimeRequiredSensor(coordinator, data[vehicle], ChargingSpeed.FAST)]
        if data[vehicle].charge_time_required_to_full[ChargingSpeed.ADAPTIVE] is not None:
            entities.append(ChargeTimeRequiredSensor(coordinator, data[vehicle], ChargingSpeed.ADAPTIVE))
        if data[vehicle].range_hvac_off is not None:
            entities.append(RangeSensor(coordinator, data[vehicle], False, imperial_distance))
        if not is_ze2 and data[vehicle].fuel_autonomy is not None:
            entities.append(FuelRangeSensor(coordinator, data[vehicle], imperial_distance))
        if not is_ze2 and data[vehicle].fuel_quantity is not None and Feature.BATTERY_STATUS not in data[vehicle].features:
            entities.append(FuelQuantitySensor(coordinator, data[vehicle]))
        if not is_ze2 and data[vehicle].fuel_level is not None:
            entities.append(FuelLevelSensor(coordinator, data[vehicle]))
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


class RawDiagnosticSensor(KamereonEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC

    def __init__(self, coordinator, vehicle, source, field, name):
        super().__init__(coordinator, vehicle)
        self._source = source
        self._field = field
        self._attr_translation_key = name

    @property
    def native_value(self):
        return getattr(self.vehicle, self._source).get(self._field)


class TyrePressureSensor(KamereonEntity, SensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = SensorDeviceClass.PRESSURE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = UnitOfPressure.BAR
    _attr_suggested_unit_of_measurement = UnitOfPressure.BAR

    def __init__(self, coordinator, vehicle, prefix, position):
        super().__init__(coordinator, vehicle)
        self._field = prefix + "Pressure"
        # The translation key also forms the existing entity registry unique ID.
        self._attr_translation_key = f"{position}_tyre_pressure_raw"

    @property
    def native_value(self):
        millibars = self.vehicle.tyre_readings.get(self._field)
        if type(millibars) not in (int, float) or not math.isfinite(millibars) or millibars < 0:
            return None
        return millibars / 1000


class RepeatClimateTargetSensor(KamereonEntity, SensorEntity):
    _attr_translation_key = "repeat_climate_target"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS

    @property
    def native_value(self):
        return self.vehicle.repeat_climate_settings.get("globalTargetTemperature")


class BatteryLevelSensor(KamereonEntity, SensorEntity):
    _attr_translation_key = "battery_level"
    _attr_device_class = SensorDeviceClass.BATTERY
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, coordinator, vehicle):
        KamereonEntity.__init__(self, coordinator, vehicle)

    @property
    def state(self):
        """Return the state."""
        return self.vehicle.battery_level

    @property
    def icon(self):
        """Icon of the sensor. Round up to the nearest 10% icon."""
        nearest = math.ceil((self.state or 0) / 10.0) * 10
        if nearest == 0:
            return "mdi:battery-outline"
        elif nearest == 100:
            return "mdi:battery"
        else:
            return "mdi:battery-" + str(nearest)

    @property
    def device_state_attributes(self):
        """Return device specific state attributes."""
        a = KamereonEntity.device_state_attributes.fget(self)
        a.update({
            'battery_capacity': self.vehicle.battery_capacity,
            'battery_level': self.vehicle.battery_level,
        })
        return a


class InternalTemperatureSensor(KamereonEntity, SensorEntity):
    _attr_translation_key = "internal_temperature"
    _attr_device_class = SensorDeviceClass.TEMPERATURE
    _attr_native_unit_of_measurement = UnitOfTemperature.CELSIUS
    _attr_state_class = SensorStateClass.MEASUREMENT

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
    _attr_state_class = SensorStateClass.MEASUREMENT

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
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

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


class FuelRangeSensor(KamereonEntity, SensorEntity):
    """Distance the vehicle estimates it can still travel on the fuel it has."""
    _attr_translation_key = "fuel_range"
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator, vehicle, imperial_distance):
        if imperial_distance:
            self._attr_suggested_unit_of_measurement = UnitOfLength.MILES
        KamereonEntity.__init__(self, coordinator, vehicle)

    @property
    def native_value(self):
        """Return the state."""
        return self.vehicle.fuel_autonomy

    @property
    def icon(self):
        """Icon of the sensor."""
        return "mdi:gas-station"


class FuelQuantitySensor(KamereonEntity, SensorEntity):
    """Fuel currently in the tank."""
    _attr_translation_key = "fuel_quantity"
    _attr_device_class = SensorDeviceClass.VOLUME_STORAGE
    _attr_native_unit_of_measurement = UnitOfVolume.LITERS
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 1

    @property
    def native_value(self):
        """Return the state."""
        return self.vehicle.fuel_quantity

    @property
    def icon(self):
        """Icon of the sensor."""
        return "mdi:fuel"


class FuelLevelSensor(KamereonEntity, SensorEntity):
    """Fuel tank level as a percentage.

    There is no fuel equivalent of SensorDeviceClass.BATTERY, so this is a
    plain percentage sensor.
    """
    _attr_translation_key = "fuel_level"
    _attr_native_unit_of_measurement = PERCENTAGE
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    @property
    def native_value(self):
        """Return the state."""
        return self.vehicle.fuel_level

    @property
    def icon(self):
        """Icon of the sensor."""
        return "mdi:gauge"


class OdometerSensor(KamereonEntity, SensorEntity):
    _attr_translation_key = "odometer"
    _attr_device_class = SensorDeviceClass.DISTANCE
    _attr_native_unit_of_measurement = UnitOfLength.KILOMETERS
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_suggested_display_precision = 0

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
    _attr_suggested_unit_of_measurement = UnitOfTime.HOURS

    CHARGING_SPEED_NAME = {
        ChargingSpeed.FASTEST: '50kw',
        ChargingSpeed.FAST: '6kw',
        ChargingSpeed.NORMAL: '3kw',
        ChargingSpeed.SLOW: '1kw',
        ChargingSpeed.ADAPTIVE: 'adaptive'
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

