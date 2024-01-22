from homeassistant.helpers.entity import Entity, DeviceInfo
from homeassistant.core import callback
from .const import DOMAIN

class KamereonEntity(Entity):
    """Base class for all Kamereon car entities."""

    _attr_has_entity_name = True

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
        self.async_write_ha_state()

    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:car'

    @property
    def _vehicle_name(self):
        return self.vehicle.nickname or self.vehicle.model_name

    @property
    def unique_id(self):
        """Return unique ID of the entity."""
        return f"{self._vehicle_name}_{self._attr_translation_key}"

    @property
    def device_info(self):
        return DeviceInfo(
            identifiers={(DOMAIN, self.vehicle.session.tenant, self.vehicle.vin)},
            name=self.vehicle.nickname or self.vehicle.model_name,
            manufacturer=self.vehicle.session.tenant.capitalize(),
            model=f"{self.vehicle.model_year} {self.vehicle.model_name}",
            hw_version=self.vehicle.model_code,
            serial_number=self.vehicle.vin,
        )
