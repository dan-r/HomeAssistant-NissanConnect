import logging
from .kamereon import NCISession
from .coordinator import KamereonCoordinator
from .const import *

_LOGGER = logging.getLogger(__name__)

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
         DATA_VEHICLES: {}
    }

    _LOGGER.info("Logging in to service")
    await hass.async_add_executor_job(kamereon_session.login,
        config.get("email"),
        config.get("password")
    )

    _LOGGER.debug("Finding vehicles")
    for vehicle in await hass.async_add_executor_job(kamereon_session.fetch_vehicles):
        await hass.async_add_executor_job(vehicle.refresh)
        if vehicle.vin not in data[DATA_VEHICLES]:
            data[DATA_VEHICLES][vehicle.vin] = vehicle

    coordinator = data[DATA_COORDINATOR] = KamereonCoordinator(hass=hass)

    await coordinator.async_config_entry_first_refresh()

    _LOGGER.debug("Initialising entities")
    for component in ('binary_sensor',):
            hass.async_create_task(
                hass.config_entries.async_forward_entry_setup(entry, component)
            )

    return True
