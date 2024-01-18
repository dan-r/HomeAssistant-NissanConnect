from datetime import timedelta
import logging

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed
)

from .const import DOMAIN, DATA_VEHICLES

_LOGGER = logging.getLogger(__name__)


class KamereonCoordinator(DataUpdateCoordinator):
    """Coordinator to pull main charge state and power/current draw."""

    def __init__(self, hass):
        """Initialise coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Kamereon Coordinator",
            update_interval=timedelta(minutes=1),
        )
        self._hass = hass
        self._vehicles = hass.data[DOMAIN][DATA_VEHICLES]

    async def _async_update_data(self):
        """Fetch data from API."""
        try:
            for vehicle in self._vehicles:
                return await self._hass.async_add_executor_job(self._vehicles[vehicle].refresh)
        except BaseException:
            raise UpdateFailed("Error communicating with API")
