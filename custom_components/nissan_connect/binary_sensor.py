"""Support for Kamereon cars."""
from homeassistant.components.binary_sensor import BinarySensorEntity, BinarySensorDeviceClass
from homeassistant.const import EntityCategory

from .base import KamereonEntity
from .kamereon import ChargingStatus, PluggedStatus, LockStatus, Feature
from .const import DOMAIN, DATA_VEHICLES, DATA_COORDINATOR_FETCH

OPENINGS = {
    "doorStatusFrontLeft": ("front_left_door", BinarySensorDeviceClass.DOOR),
    "doorStatusFrontRight": ("front_right_door", BinarySensorDeviceClass.DOOR),
    "doorStatusRearLeft": ("rear_left_door", BinarySensorDeviceClass.DOOR),
    "doorStatusRearRight": ("rear_right_door", BinarySensorDeviceClass.DOOR),
    "engineHoodStatus": ("bonnet", BinarySensorDeviceClass.OPENING),
    "hatchStatus": ("hatch", BinarySensorDeviceClass.OPENING),
    "windowStatusFrontLeft": ("front_left_window", BinarySensorDeviceClass.WINDOW),
    "windowStatusFrontRight": ("front_right_window", BinarySensorDeviceClass.WINDOW),
    "windowStatusRearLeft": ("rear_left_window", BinarySensorDeviceClass.WINDOW),
    "windowStatusRearRight": ("rear_right_window", BinarySensorDeviceClass.WINDOW),
}

REPEAT_CLIMATE_OPTIONS = {
    "frontLeftSeatControl": "scheduled_front_left_seat_heat",
    "frontRightSeatControl": "scheduled_front_right_seat_heat",
    "steeringHeaterControl": "scheduled_steering_wheel_heat",
    "frontDefrostMode": "scheduled_front_defrost",
    "rearDefrostMode": "scheduled_rear_defrost",
}

LOCKS = {
    "doorLockStatusDriver": "driver_door_lock",
    "doorLockStatusPassenger": "passenger_door_lock",
    "doorLockStatusRearLeft": "rear_left_door_lock",
    "doorLockStatusRearRight": "rear_right_door_lock",
    "trunkLockStatus": "boot_lock",
}

PROBLEM_LAMPS = {
    "absWarning": "abs_warning",
    "airbagWarning": "airbag_warning",
    "powerSteeringWarning": "power_steering_warning",
    "tyrePressureWarning": "tyre_pressure_warning",
    "powerLimitationAlert": "power_limitation_warning",
}

async def async_setup_entry(hass, config, async_add_entities):
    """Set up the Kamereon sensors."""
    account_id = config.data['email']

    data = hass.data[DOMAIN][account_id][DATA_VEHICLES]
    coordinator = hass.data[DOMAIN][account_id][DATA_COORDINATOR_FETCH]

    entities = []

    for vehicle in data.values():
        has_battery_service = Feature.BATTERY_STATUS in vehicle.features
        if has_battery_service or (vehicle.is_ze2_leaf and vehicle.charging is not None):
            entities.append(ChargingStatusEntity(coordinator, vehicle))
        if has_battery_service or (vehicle.is_ze2_leaf and vehicle.plugged_in is not None):
            entities.append(PluggedStatusEntity(coordinator, vehicle))
        if Feature.LOCK_STATUS_CHECK in vehicle.features or (vehicle.is_ze2_leaf and vehicle.lock_status is not None):
            entities.append(LockStatusEntity(coordinator, vehicle))
        if vehicle.is_ze2_leaf:
            for slot in range(1, 6):
                entities.append(ClimateTimerEntity(coordinator, vehicle, slot))
            for field, name in REPEAT_CLIMATE_OPTIONS.items():
                entities.append(RepeatClimateOptionEntity(coordinator, vehicle, field, name))
            for key, (name, device_class) in OPENINGS.items():
                if vehicle.security_status.get(key) in ("open", "closed"):
                    entities.append(SecurityEntity(coordinator, vehicle, key, name, device_class, "open", "closed"))
            for key, name in LOCKS.items():
                entities.append(SecurityEntity(coordinator, vehicle, key, name, BinarySensorDeviceClass.LOCK, "unlocked", "locked"))
            for name, device_class in (("any_door", BinarySensorDeviceClass.DOOR),
                                       ("any_window", BinarySensorDeviceClass.WINDOW)):
                entities.append(OpeningGroupEntity(coordinator, vehicle, name, device_class))
            entities.append(SecurityEntity(coordinator, vehicle, "hazardLampStatus", "hazard_lamps",
                                           BinarySensorDeviceClass.LIGHT, "on", "off"))
            for key, name in PROBLEM_LAMPS.items():
                entities.append(WarningLampEntity(coordinator, vehicle, key, name))
            if vehicle.hvac_status is not None:
                entities.append(ClimateActiveEntity(coordinator, vehicle))

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
            return None
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
            return None
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


class ClimateTimerEntity(KamereonEntity, BinarySensorEntity):
    """Whether a departure timer is enabled, with Nissan's per-day times."""

    _attr_translation_key = "climate_timer"

    def __init__(self, coordinator, vehicle, slot):
        super().__init__(coordinator, vehicle)
        self._slot = slot
        self._attr_translation_placeholders = {"slot": str(slot)}

    @property
    def unique_id(self):
        # Preserve the original climate_timer_1 through climate_timer_5 IDs.
        return f"{super().unique_id}_{self._slot}"

    @property
    def is_on(self):
        enabled = self.vehicle.climate_timers.get(self._slot, {}).get("activated")
        return enabled if isinstance(enabled, bool) else None

    @property
    def extra_state_attributes(self):
        timer = self.vehicle.climate_timers.get(self._slot, {})
        departures = {}
        for day in ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"):
            entry = timer.get(day)
            if isinstance(entry, dict) and isinstance(entry.get("readyAtTime"), str):
                departures[day] = entry["readyAtTime"].removeprefix("T")
        # Home Assistant translates top-level attribute names for each viewer.
        return departures


class RepeatClimateOptionEntity(KamereonEntity, BinarySensorEntity):
    """An equipment selection shared by the repeat timers."""

    def __init__(self, coordinator, vehicle, field, name):
        super().__init__(coordinator, vehicle)
        self._field = field
        self._attr_translation_key = name

    @property
    def is_on(self):
        return {0: False, 1: True}.get(self.vehicle.repeat_climate_settings.get(self._field))


class SecurityEntity(KamereonEntity, BinarySensorEntity):
    def __init__(self, coordinator, vehicle, key, name, device_class, on, off):
        super().__init__(coordinator, vehicle)
        self._key = key
        self._attr_translation_key = name
        self._attr_device_class = device_class
        self._states = {on: True, off: False}

    @property
    def is_on(self):
        return self._states.get(self.vehicle.security_status.get(self._key))


class OpeningGroupEntity(KamereonEntity, BinarySensorEntity):
    """A single open panel is conclusive; closed requires all four readings."""

    def __init__(self, coordinator, vehicle, name, device_class):
        super().__init__(coordinator, vehicle)
        self._attr_translation_key = name
        self._attr_device_class = device_class
        self._keys = [key for key, (_, kind) in OPENINGS.items() if kind == device_class]

    @property
    def is_on(self):
        states = [self.vehicle.security_status.get(key) for key in self._keys]
        if "open" in states:
            return True
        if all(state == "closed" for state in states):
            return False
        return None


class WarningLampEntity(KamereonEntity, BinarySensorEntity):
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, coordinator, vehicle, key, name):
        super().__init__(coordinator, vehicle)
        self._key = key
        self._attr_translation_key = name

    @property
    def is_on(self):
        # Zero matched the app's OK state. Preserve any non-binary Nissan codes
        # as attributes rather than classifying them as an active fault.
        return {0: False, 1: True}.get(self.vehicle.warning_lamps.get(self._key))

    @property
    def extra_state_attributes(self):
        return {"raw_code": self.vehicle.warning_lamps.get(self._key)}


class ClimateActiveEntity(KamereonEntity, BinarySensorEntity):
    _attr_translation_key = "climate_active"
    _attr_device_class = BinarySensorDeviceClass.RUNNING

    @property
    def is_on(self):
        return self.vehicle.hvac_status

    @property
    def extra_state_attributes(self):
        return self.vehicle.hvac_equipment


class LockStatusEntity(KamereonEntity, BinarySensorEntity):
    _attr_device_class = BinarySensorDeviceClass.LOCK
    _attr_translation_key = "doors_locked"

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:car-door-lock' if self.vehicle.lock_status == LockStatus.LOCKED else 'mdi:car-door-lock-open'

    @property
    def is_on(self):
        if self.vehicle.is_ze2_leaf and self.vehicle.lock_status is None:
            return None
        return self.vehicle.lock_status == LockStatus.UNLOCKED
