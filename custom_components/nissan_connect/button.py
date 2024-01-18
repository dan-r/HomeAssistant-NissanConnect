"""Support for Kamereon cars."""
import logging

from homeassistant.components.button import ButtonEntity

from .base import KamereonEntity
from .kamereon import ChargingStatus, PluggedStatus, Feature
from .const import DOMAIN, DATA_VEHICLES, DATA_COORDINATOR

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config, async_add_entities):
    data = hass.data[DOMAIN][DATA_VEHICLES]
    coordinator = hass.data[DOMAIN][DATA_COORDINATOR]

    entities = []

    for vehicle in data:
        entities.append(ForceUpdateButton(coordinator, data[vehicle], hass))

    async_add_entities(entities, update_before_add=True)


class ForceUpdateButton(KamereonEntity, ButtonEntity):
    _attr_name = "Update Data"

    def __init__(self, coordinator, vehicle, hass):
        KamereonEntity.__init__(self, coordinator, vehicle)
        self._hass = hass
    
    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:update'

    async def async_press(self):
        await self._hass.async_add_executor_job(self.vehicle.refresh)
