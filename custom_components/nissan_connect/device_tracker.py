"""Support for tracking a Kamereon car."""
import logging

from homeassistant.components.device_tracker import TrackerEntity
from homeassistant.components.device_tracker.const import SourceType
from .base import KamereonEntity
from .kamereon import Feature
from .const import DOMAIN, DATA_COORDINATOR_FETCH, DATA_VEHICLES

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(hass, entry, async_add_entities):
    data = hass.data[DOMAIN][DATA_VEHICLES]
    coordinator = hass.data[DOMAIN][DATA_COORDINATOR_FETCH]

    entities = []

    for vehicle in data:
        if Feature.MY_CAR_FINDER in data[vehicle].features:
            entities.append(KamereonDeviceTracker(coordinator, data[vehicle]))

    async_add_entities(entities, update_before_add=True)

    return True

class KamereonDeviceTracker(KamereonEntity, TrackerEntity):
    _attr_translation_key = "location"

    @property
    def latitude(self) -> float:
        """Return latitude value of the device."""
        if not self.vehicle or not self.vehicle.location:
            return None
        
        return self.vehicle.location[0]

    @property
    def longitude(self) -> float:
        """Return longitude value of the device."""
        if not self.vehicle or not self.vehicle.location:
            return None
        
        return self.vehicle.location[1]

    @property
    def source_type(self):
        """Return the source type, eg gps or router, of the device."""
        return SourceType.GPS

    @property
    def icon(self):
        """Return the icon."""
        return "mdi:car"
