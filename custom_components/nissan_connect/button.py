"""Support for Kamereon cars."""
import logging
import asyncio

from homeassistant.components.button import ButtonEntity

from .base import KamereonEntity
from .kamereon import ChargingStatus, PluggedStatus, Feature
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

    async_add_entities(entities, update_before_add=True)


class KamereonButton(KamereonEntity, ButtonEntity):
    """A button stays available whatever the last data update did.

    Commands go straight to the car and report their own errors, so a failed
    fetch says nothing about whether they will work. Above all, the update
    button is how the user retries after a failed fetch.
    """

    @property
    def available(self):
        return True


class ForceUpdateButton(KamereonButton):
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
        
        updated = await loop.run_in_executor(None, self.vehicle.refresh_fetch)
        if updated:
            self.coordinator.failed_vins.discard(self.vehicle.vin)
            self.coordinator.async_set_updated_data(True)

class HornLightsButtons(KamereonButton):
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

class ChargeControlButtons(KamereonButton):
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

