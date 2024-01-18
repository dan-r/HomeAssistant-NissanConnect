from datetime import timedelta
import logging

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed
)
from time import time
from .const import DOMAIN, DATA_VEHICLES
from .kamereon import Feature, PluggedStatus, HVACStatus
_LOGGER = logging.getLogger(__name__)


class KamereonCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, config):
        """Initialise coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Kamereon Coordinator",
            update_interval=timedelta(minutes=1),
        )
        self._hass = hass
        self._vehicles = hass.data[DOMAIN][DATA_VEHICLES]

        self._interval = config.get("interval", 60)
        self._interval_charging = config.get("interval_charging", 15)
        self._last_update = {}

    async def force_update(self):
        self._last_update = {}
        await self.async_refresh()

    async def _async_update_data(self):
        """Fetch data from API."""
        try:
            for vehicle in self._vehicles:
                if not vehicle in self._last_update:
                    self._last_update[vehicle] = 0
                
                interval = 2 or self._interval

                # EV, decide which time to use
                if Feature.BATTERY_STATUS in self._vehicles[vehicle].features and self._vehicles[vehicle].plugged_in == PluggedStatus.PLUGGED:
                    interval = self._interval_charging

                # Update on every cycle if HVAC on
                if self._vehicles[vehicle].hvac_status == HVACStatus.ON:
                    interval = 0

                # If we are overdue an update
                if time() > self._last_update[vehicle] + (interval * 60):
                    await self._hass.async_add_executor_job(self._vehicles[vehicle].refresh)
                    self._last_update[vehicle] = time()
                   
        except BaseException:
            _LOGGER.warning("Error communicating with API")
        return True
