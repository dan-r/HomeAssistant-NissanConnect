"""Support for Kamereon cars."""
import logging

from homeassistant.components.button import ButtonEntity

from .base import KamereonEntity
from .kamereon import ChargingStatus, PluggedStatus, Feature
from .const import DOMAIN, DATA_VEHICLES, DATA_COORDINATOR, DATA_COORDINATOR_STATISTICS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config, async_add_entities):
    data = hass.data[DOMAIN][DATA_VEHICLES]
    coordinator = hass.data[DOMAIN][DATA_COORDINATOR]
    stats_coordinator = hass.data[DOMAIN][DATA_COORDINATOR_STATISTICS]

    entities = []

    for vehicle in data:
        entities.append(ForceUpdateButton(coordinator, data[vehicle], hass, stats_coordinator))

    async_add_entities(entities, update_before_add=True)


class ForceUpdateButton(KamereonEntity, ButtonEntity):
    _attr_name = "Update Data"

    def __init__(self, coordinator, vehicle, hass, stats_coordinator):
        KamereonEntity.__init__(self, coordinator, vehicle)
        self._hass = hass
        self.coordinator_statistics = stats_coordinator
    
    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:update'

    async def async_press(self):
        await self.coordinator.force_update()
        await self.coordinator_statistics.async_refresh()
        
