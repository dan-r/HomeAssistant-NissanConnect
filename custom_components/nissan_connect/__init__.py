import logging

from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.dispatcher import (
    async_dispatcher_send
)
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util.dt import utcnow

from .kamereon import NCISession
_LOGGER = logging.getLogger(__name__)

from .const import *

async def async_setup(hass, config) -> bool:
    return True

async def async_setup_entry(hass, entry):
    """This is called from the config flow."""
    hass.data.setdefault(DOMAIN, {})

    config = dict(entry.data)

    kamereon_session = NCISession(
        region=config["region"]
    )

    interval = config["interval"]

    data = hass.data[DOMAIN] = {
         'vehicles': {}
    }

    _LOGGER.info("Logging in to service")
    await hass.async_add_executor_job(kamereon_session.login,
        config.get("email"),
        config.get("password")
    )

    _LOGGER.debug("Finding vehicles")
    for vehicle in await hass.async_add_executor_job(kamereon_session.fetch_vehicles):
        await hass.async_add_executor_job(vehicle.refresh)
        if vehicle.vin not in data['vehicles']:
            data['vehicles'][vehicle.vin] = vehicle

    _LOGGER.debug("Initialising entities")
    for component in ('binary_sensor',):
            hass.async_create_task(
                hass.config_entries.async_forward_entry_setup(entry, component)
            )

    return True
