"""Support for tracking a Kamereon car."""
import logging

from homeassistant.components.device_tracker import SOURCE_TYPE_GPS
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.util import slugify

_LOGGER = logging.getLogger(__name__)


async def async_setup_scanner(hass, config, async_see, vehicle=None):
    """Set up the Kamereon tracker."""
    if vehicle is None:
        return

    async def see_vehicle():
        """Handle the reporting of the vehicle position."""
        host_name = slugify(vehicle.nickname or vehicle.model_name)
        await async_see(
            dev_id=host_name,
            host_name=host_name,
            source_type=SOURCE_TYPE_GPS,
            gps=vehicle.location,
            attributes={
                'last_updated': vehicle.location_last_updated.isoformat(),
                'manufacturer': vehicle.session.tenant,
                'vin': vehicle.vin,
                'name': vehicle.nickname or vehicle.model_name,
                'model': vehicle.model_name,
                'registration_number': vehicle.registration_number,
            },
            icon="mdi:car",
        )

    return True