"""Support for Kamereon cars."""
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.const import STATE_UNKNOWN

from .base import KamereonEntity
from .kamereon import ChargingStatus, PluggedStatus, LockStatus, Feature
from .const import DOMAIN, DATA_VEHICLES, DATA_COORDINATOR_FETCH

async def async_setup_entry(hass, config, async_add_entities):
    """Set up the Kamereon sensors."""
    account_id = config.data['email']

    data = hass.data[DOMAIN][account_id][DATA_VEHICLES]
    coordinator = hass.data[DOMAIN][account_id][DATA_COORDINATOR_FETCH]

    entities = []

    for vehicle in data:
        if Feature.BATTERY_STATUS in data[vehicle].features:
            entities += [ChargingStatusEntity(coordinator, data[vehicle]),
                         PluggedStatusEntity(coordinator, data[vehicle])]
        if Feature.LOCK_STATUS_CHECK in data[vehicle].features:
            entities += [LockStatusEntity(coordinator, data[vehicle])]
        if Feature.VEHICLE_STATUS_CHECK in data[vehicle].features:
            entities += [
                WarningBinarySensor(coordinator, data[vehicle], 'warning_abs',           'ABS Warning',           'mdi:car-brake-abs',         'mdi:car-brake-abs'),
                WarningBinarySensor(coordinator, data[vehicle], 'warning_airbag',        'Airbag Warning',        'mdi:airbag',                'mdi:airbag'),
                WarningBinarySensor(coordinator, data[vehicle], 'warning_brake_fluid',   'Brake Fluid Warning',   'mdi:car-brake-fluid-level', 'mdi:car-brake-fluid-level'),
                WarningBinarySensor(coordinator, data[vehicle], 'warning_oil_pressure',  'Oil Pressure Warning',  'mdi:oil-level',             'mdi:oil-level'),
                WarningBinarySensor(coordinator, data[vehicle], 'warning_tyre_pressure', 'Tyre Pressure Warning', 'mdi:tire-alert',            'mdi:tire'),
                WarningBinarySensor(coordinator, data[vehicle], 'warning_check_engine',  'Check Engine Warning',  'mdi:engine-outline',        'mdi:engine'),
                WarningBinarySensor(coordinator, data[vehicle], 'warning_service',       'Service Warning',       'mdi:wrench-clock',          'mdi:wrench-clock'),
                WarningBinarySensor(coordinator, data[vehicle], 'warning_battery_low',   'Battery Low Warning',   'mdi:car-battery',           'mdi:car-battery'),
            ]

    async_add_entities(entities, update_before_add=True)


class ChargingStatusEntity(KamereonEntity, BinarySensorEntity):
    """Representation of charging status."""
    _attr_device_class = BinarySensorDeviceClass.BATTERY_CHARGING
    _attr_translation_key = "charging"

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
    def device_state_attributes(self):
        a = KamereonEntity.device_state_attributes.fget(self)
        a.update({
            'charging_speed': self.vehicle.charging_speed.value,
            'last_updated': self.vehicle.battery_status_last_updated,
        })
        return a


class PluggedStatusEntity(KamereonEntity, BinarySensorEntity):
    """Representation of plugged status."""
    _attr_device_class = BinarySensorDeviceClass.PLUG
    _attr_translation_key = "plugged"

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
    def device_state_attributes(self):
        a = KamereonEntity.device_state_attributes.fget(self)
        a.update({
            'plugged_in_time': self.vehicle.plugged_in_time,
            'unplugged_time': self.vehicle.unplugged_time,
            'last_updated': self.vehicle.battery_status_last_updated,
        })
        return a


class LockStatusEntity(KamereonEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.LOCK
    _attr_translation_key = "doors_locked"

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:car-door-lock' if self.vehicle.lock_status == LockStatus.LOCKED else 'mdi:car-door-lock-open'

    @property
    def is_on(self):
        return self.vehicle.lock_status == LockStatus.UNLOCKED


class WarningBinarySensor(KamereonEntity, BinarySensorEntity):
    """A dashboard warning lamp (on = warning active)."""
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, vehicle, attribute, name, icon_on, icon_off):
        self._attribute = attribute
        self._attr_name = name
        self._icon_on = icon_on
        self._icon_off = icon_off
        KamereonEntity.__init__(self, coordinator, vehicle)

    @property
    def unique_id(self):
        base = self.vehicle.session.unique_id or self.vehicle.nickname or self.vehicle.model_name
        return f"{base}_{self.vehicle.vin}_{self._attribute}"

    @property
    def is_on(self):
        val = getattr(self.vehicle, self._attribute, None)
        if val is None:
            return None
        return bool(val)

    @property
    def icon(self):
        return self._icon_on if self.is_on else self._icon_off
