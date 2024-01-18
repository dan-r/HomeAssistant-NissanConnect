from homeassistant.helpers.entity import Entity, DeviceInfo
from homeassistant.core import HomeAssistant, callback
from .const import DOMAIN

class KamereonEntity(Entity):
    """Base class for all Kamereon car entities."""

    def __init__(self, cooordinator, vehicle):
        """Initialize the entity."""
        self.vehicle = vehicle
        self.coordinator = cooordinator

    async def async_added_to_hass(self) -> None:
        """When entity is added to hass."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.coordinator.async_add_listener(
                self._handle_coordinator_update, None
            )
        )
    
    @callback
    def _handle_coordinator_update(self) -> None:
        return

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:car'

    @property
    def _vehicle_name(self):
        return self.vehicle.nickname or self.vehicle.model_name

    @property
    def name(self):
        """Return full name of the entity."""
        if not self._attr_name:
            return self._vehicle_name
        return f"{self._vehicle_name} {self._attr_name}"

    @property
    def unique_id(self):
        """Return unique ID of the entity."""
        if not self._attr_name:
            return None
        return f"{self._vehicle_name}_{self._attr_name}"

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
            manufacturer=self.vehicle.session.tenant.capitalize(),
            serial_number=self.vehicle.vin,
        )