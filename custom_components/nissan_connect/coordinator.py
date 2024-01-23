from datetime import timedelta
import logging

from homeassistant.helpers.update_coordinator import (
    DataUpdateCoordinator,
    UpdateFailed
)
from time import time
from .const import DOMAIN, DATA_VEHICLES, DEFAULT_INTERVAL, DEFAULT_INTERVAL_CHARGING, DEFAULT_INTERVAL_STATISTICS
from .kamereon import Feature, PluggedStatus, HVACStatus, Period
_LOGGER = logging.getLogger(__name__)


class KamereonCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, config):
        """Initialise coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Kamereon Coordinator",
            # This interval is overwritten by _set_next_interval in the first run
            update_interval=timedelta(minutes=15),
        )
        self._hass = hass
        self._vehicles = hass.data[DOMAIN][DATA_VEHICLES]
        self._config = config

    def _set_next_interval(self):
        """Calculate the next update interval."""
        interval = self._config.get("interval", DEFAULT_INTERVAL)
        interval_charging = self._config.get("interval_charging", DEFAULT_INTERVAL_CHARGING)
        
        # Get the shortest interval from all vehicles
        for vehicle in self._vehicles:
            # EV, decide which time to use
            if Feature.BATTERY_STATUS in self._vehicles[vehicle].features and self._vehicles[vehicle].plugged_in == PluggedStatus.PLUGGED:
                interval = interval_charging if interval_charging < interval else interval

            # Update every minute if HVAC on
            if self._vehicles[vehicle].hvac_status == HVACStatus.ON:
                interval = 1
        
        if interval != (self.update_interval.seconds / 60):
            _LOGGER.debug(f"Changing next update interval to {interval} minutes")
            self.update_interval = timedelta(minutes=interval)

    async def _async_update_data(self):
        """Fetch data from API."""
        try:
            for vehicle in self._vehicles:
                await self._hass.async_add_executor_job(self._vehicles[vehicle].refresh)
                   
        except BaseException:
            _LOGGER.warning("Error communicating with API")
            return False
        
        self._set_next_interval()
        return True


class StatisticsCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, config):
        """Initialise coordinator."""
        super().__init__(
            hass,
            _LOGGER,
            name="Statistics Coordinator",
            update_interval=timedelta(minutes=config.get("interval_statistics", DEFAULT_INTERVAL_STATISTICS)),
        )
        self._hass = hass
        self._vehicles = hass.data[DOMAIN][DATA_VEHICLES]

    async def _async_update_data(self):
        """Fetch data from API."""
        output = {}
        try:
            for vehicle in self._vehicles:
                if not Feature.DRIVING_JOURNEY_HISTORY in self._vehicles[vehicle].features:
                    continue

                output[vehicle] = {
                    'daily': await self._hass.async_add_executor_job(self._vehicles[vehicle].fetch_trip_histories, Period.DAILY),
                    'monthly': await self._hass.async_add_executor_job(self._vehicles[vehicle].fetch_trip_histories, Period.MONTHLY)
                }
        except BaseException:
            _LOGGER.warning("Error communicating with statistics API")
        
        return output
