"""Support for Kamereon cars."""
import logging
import asyncio

from homeassistant.components.button import ButtonEntity

from .base import KamereonEntity
from .kamereon import ChargingStatus, PluggedStatus, Feature, LockableDoorGroup
from .const import DOMAIN, DATA_VEHICLES, DATA_COORDINATOR_POLL, DATA_COORDINATOR_FETCH, DATA_COORDINATOR_STATISTICS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config, async_add_entities):
    account_id = config.data['email']

    data = hass.data[DOMAIN][account_id][DATA_VEHICLES]
    coordinator = hass.data[DOMAIN][account_id][DATA_COORDINATOR_POLL]
    coordinator_fetch = hass.data[DOMAIN][account_id][DATA_COORDINATOR_FETCH]
    stats_coordinator = hass.data[DOMAIN][account_id][DATA_COORDINATOR_STATISTICS]

    entities = []

    for vehicle in data:
        entities.append(ForceUpdateButton(coordinator_fetch, data[vehicle], hass, stats_coordinator))
        if Feature.HORN_AND_LIGHTS in data[vehicle].features:
            entities += [
                HornLightsButtons(coordinator, data[vehicle], "flash_lights", "mdi:car-light-high", "lights"),
                HornLightsButtons(coordinator, data[vehicle], "honk_horn", "mdi:bullhorn", "horn_lights")
            ]
        if Feature.CHARGING_START in data[vehicle].features:
            entities.append(ChargeControlButtons(coordinator, data[vehicle], "charge_start", "mdi:play", "start"))
        if Feature.APP_DOOR_LOCKING in data[vehicle].features:
            entities += [
                LockUnlockButton(coordinator, data[vehicle], "lock_doors", "mdi:car-door-lock", "lock"),
                LockUnlockButton(coordinator, data[vehicle], "unlock_doors", "mdi:car-door", "unlock"),
            ]
        # Wake-up is always useful (no specific feature flag required)
        entities.append(WakeUpVehicleButton(coordinator, data[vehicle]))

    async_add_entities(entities, update_before_add=True)


class ForceUpdateButton(KamereonEntity, ButtonEntity):
    _attr_translation_key = "update_data"

    def __init__(self, coordinator, vehicle, hass, stats_coordinator):
        KamereonEntity.__init__(self, coordinator, vehicle)
        self._hass = hass
        self.coordinator_statistics = stats_coordinator
    
    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:update'

    async def async_press(self):
        loop = asyncio.get_running_loop()
        
        await loop.run_in_executor(None, self.vehicle.refresh)
        await self.coordinator.async_refresh()

class HornLightsButtons(KamereonEntity, ButtonEntity):
    def __init__(self, coordinator, vehicle, translation_key, icon, action):
        self._attr_translation_key = translation_key
        self._icon = icon
        self._action = action
        KamereonEntity.__init__(self, coordinator, vehicle)
    
    @property
    def icon(self):
        return self._icon

    def press(self):
        self.vehicle.control_horn_lights('start', self._action)

class ChargeControlButtons(KamereonEntity, ButtonEntity):
    def __init__(self, coordinator, vehicle, translation_key, icon, action):
        self._attr_translation_key = translation_key
        self._icon = icon
        self._action = action
        KamereonEntity.__init__(self, coordinator, vehicle)
    
    @property
    def icon(self):
        return self._icon

    def press(self):
        self.vehicle.control_charging(self._action)


class LockUnlockButton(KamereonEntity, ButtonEntity):
    """Lock or unlock the vehicle doors."""

    def __init__(self, coordinator, vehicle, translation_key, icon, action):
        self._attr_name = 'Lock Doors' if action == 'lock' else 'Unlock Doors'
        self._icon = icon
        self._action = action
        KamereonEntity.__init__(self, coordinator, vehicle)

    @property
    def unique_id(self):
        base = self.vehicle.session.unique_id or self.vehicle.nickname or self.vehicle.model_name
        return f"{base}_{self.vehicle.vin}_{self._action}_doors"

    @property
    def icon(self):
        return self._icon

    def press(self):
        self.vehicle.lock_unlock(self._action)


class WakeUpVehicleButton(KamereonEntity, ButtonEntity):
    """Wake up a sleeping/disconnected vehicle before sending remote commands."""
    _attr_name = 'Wake Up Vehicle'

    @property
    def unique_id(self):
        base = self.vehicle.session.unique_id or self.vehicle.nickname or self.vehicle.model_name
        return f"{base}_{self.vehicle.vin}_wake_up_vehicle"

    @property
    def icon(self):
        return 'mdi:car-wireless'

    def press(self):
        self.vehicle.wake_up_vehicle()

