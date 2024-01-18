from homeassistant.helpers.entity import Entity, DeviceInfo
from .const import DOMAIN

class KamereonEntity(Entity):
    """Base class for all Kamereon car entities."""

    def __init__(self, vehicle):
        """Initialize the entity."""
        self.vehicle = vehicle

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:car'

    @property
    def _entity_name(self):
        return None

    @property
    def _vehicle_name(self):
        return self.vehicle.nickname or self.vehicle.model_name

    @property
    def name(self):
        """Return full name of the entity."""
        if not self._entity_name:
            return self._vehicle_name
        return f"{self._vehicle_name} {self._entity_name}"

    @property
    def unique_id(self):
        """Return unique ID of the entity."""
        if not self._entity_name:
            return None
        return f"{self._vehicle_name}_{self._entity_name}"

    @property
    def should_poll(self):
        """Return the polling state."""
        return False

    @property
    def assumed_state(self):
        """Return true if unable to access real state of entity."""
        return True

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, self.vehicle.session.tenant, self.vehicle.vin)},
            name=self.vehicle.nickname or self.vehicle.model_name,
            manufacturer=self.vehicle.session.tenant,
            serial_number=self.vehicle.vin,
        )