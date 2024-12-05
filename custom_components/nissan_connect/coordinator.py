import logging

from datetime import timedelta
from time import time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from .const import DOMAIN, DATA_VEHICLES, DEFAULT_INTERVAL_POLL, DEFAULT_INTERVAL_CHARGING, DEFAULT_INTERVAL_STATISTICS, DEFAULT_INTERVAL_FETCH, DATA_COORDINATOR_FETCH, DATA_COORDINATOR_POLL
from .kamereon import Feature, PluggedStatus, ChargingStatus, Period

_LOGGER = logging.getLogger(__name__)


class KamereonFetchCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, config):
        """Coordinator to fetch the latest states."""
        super().__init__(
            hass,
            _LOGGER,
            name="Update Coordinator",
            update_interval=timedelta(minutes=config.get("interval_fetch", DEFAULT_INTERVAL_FETCH)),
        )
        self._hass = hass
        self._account_id = config['email']
        self._vehicles = hass.data[DOMAIN][self._account_id][DATA_VEHICLES]

    async def _async_update_data(self):
        """Fetch data from API."""
        try:
            for vehicle in self._vehicles:
                await self._hass.async_add_executor_job(self._vehicles[vehicle].fetch_all)
        except BaseException:
            _LOGGER.warning("Error communicating with API")
            return False
        
        # Set interval for polling (the other coordinator)
        self._hass.data[DOMAIN][self._account_id][DATA_COORDINATOR_POLL].set_next_interval()

        return True


class KamereonPollCoordinator(DataUpdateCoordinator):
    def __init__(self, hass, config):
        """Coordinator to poll the car for updates."""
        super().__init__(
            hass,
            _LOGGER,
            name="Poll Coordinator",
            # This interval is overwritten by _set_next_interval in the first run
            update_interval=timedelta(minutes=15),
        )
        self._hass = hass
        self._account_id = config['email']
        self._vehicles = hass.data[DOMAIN][self._account_id][DATA_VEHICLES]
        self._config = config
        
        self._pluggednotcharging = {key: 0 for key in self._vehicles}
        self._intervals = {key: 0 for key in self._vehicles}
        self._last_updated = {key: 0 for key in self._vehicles}
        self._force_update = {key: False for key in self._vehicles}

    def set_next_interval(self):
        """Calculate the next update interval."""
        interval = self._config.get("interval", DEFAULT_INTERVAL_POLL)
        interval_charging = self._config.get("interval_charging", DEFAULT_INTERVAL_CHARGING)
        
        # Get the shortest interval from all vehicles
        for vehicle in self._vehicles:
            # Initially set interval to default
            new_interval = interval

            # EV, decide which time to use based on whether we are plugged in or not
            if Feature.BATTERY_STATUS in self._vehicles[vehicle].features and self._vehicles[vehicle].plugged_in == PluggedStatus.PLUGGED:
                # If we are plugged in but not charging, increment a counter
                if self._vehicles[vehicle].charging != ChargingStatus.CHARGING:
                    self._pluggednotcharging[vehicle] += 1
                else: # If we are plugged in and charging, reset counter
                    self._pluggednotcharging[vehicle] = 0

                # If we haven't hit the counter limit, use the shorter interval
                if self._pluggednotcharging[vehicle] < 5:
                    new_interval = interval_charging

            # Update every minute if HVAC on
            if self._vehicles[vehicle].hvac_status:
                new_interval = 1

            # If the interval has changed, force next update
            if new_interval != self._intervals[vehicle]:
                _LOGGER.debug(f"Changing #{vehicle[-3:]} update interval to {new_interval} minutes")
                self._force_update[vehicle] = True
            
            self._intervals[vehicle] = new_interval
        
        # Set the coordinator to update at the shortest interval
        shortest_interval = min(self._intervals.values())

        if shortest_interval != (self.update_interval.seconds / 60):
            _LOGGER.debug(f"Changing coordinator update interval to {shortest_interval} minutes")
            self.update_interval = timedelta(minutes=shortest_interval)
            self._async_unsub_refresh()
            if self._listeners:
                self._schedule_refresh()

    async def _async_update_data(self):
        """Fetch data from API."""
        try:
            for vehicle in self._vehicles:
                time_since_updated = round((time() - self._last_updated[vehicle]) / 60)
                if self._force_update[vehicle] or time_since_updated >= self._intervals[vehicle]:
                    _LOGGER.debug("Polling #%s as %d mins have elapsed (interval %d)", vehicle[-3:], time_since_updated, self._intervals[vehicle])
                    self._last_updated[vehicle] = int(time())
                    self._force_update[vehicle] = False
                    await self._hass.async_add_executor_job(self._vehicles[vehicle].refresh)
                else:
                    _LOGGER.debug("NOT polling #%s as %d mins have elapsed (interval %d)", vehicle[-3:], time_since_updated, self._intervals[vehicle])                   
        except BaseException:
            _LOGGER.warning("Error communicating with API")
            return False
        
        self._hass.async_create_task(self._hass.data[DOMAIN][self._account_id][DATA_COORDINATOR_FETCH].async_refresh())
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
        self._account_id = config['email']
        self._vehicles = hass.data[DOMAIN][self._account_id][DATA_VEHICLES]

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
