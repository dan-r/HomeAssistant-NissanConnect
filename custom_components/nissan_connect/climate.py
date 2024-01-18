"""
Support for Kamereon Platform
"""
import logging
import asyncio
from time import sleep
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (HVACMode, ClimateEntityFeature)
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature

SUPPORT_HVAC = [HVACMode.HEAT_COOL, HVACMode.OFF]

from .base import KamereonEntity
from .kamereon import Feature, HVACAction, HVACStatus
from .const import DOMAIN, DATA_VEHICLES, DATA_COORDINATOR

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config, async_add_entities):
    data = hass.data[DOMAIN][DATA_VEHICLES]
    coordinator = hass.data[DOMAIN][DATA_COORDINATOR]

    for vehicle in data:
        if Feature.TEMPERATURE in data[vehicle].features or Feature.INTERIOR_TEMP_SETTINGS in data[vehicle].features:
            async_add_entities([KamereonClimate(coordinator, data[vehicle], hass)], update_before_add=True)


class KamereonClimate(KamereonEntity, ClimateEntity):
    """Representation of a Kamereon Climate."""
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_hvac_modes = SUPPORT_HVAC
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_name = "Climate"
    _target = 20
    _loop_mutex = False

    def __init__(self, coordinator, vehicle, hass):
        KamereonEntity.__init__(self, coordinator, vehicle)
        self._hass = hass

    @property
    def hvac_mode(self):
        """Return hvac operation ie. heat, cool mode.
        Need to be one of HVAC_MODE_*.
        """
        if self.vehicle.hvac_status is None:
            return None
        elif self.vehicle.hvac_status is HVACStatus.ON:
            return HVACMode.HEAT_COOL
        return HVACMode.OFF

    @property
    def current_temperature(self):
        """Return the current temperature."""
        if self.vehicle.internal_temperature:
            return float(self.vehicle.internal_temperature)
        return None

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        return float(self._target)

    def set_temperature(self, **kwargs):
        """Set new target temperatures."""
        if Feature.TEMPERATURE not in self.vehicle.features:
            raise NotImplementedError()

        temperature = kwargs.get(ATTR_TEMPERATURE)
        if not temperature:
            return
        
        if self.vehicle.hvac_status == HVACStatus.ON:
            self._target = temperature
            self.vehicle.set_hvac_status(HVACAction.START, temperature)
        else:
            self._target = temperature

    def set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        if Feature.CLIMATE_ON_OFF not in self.vehicle.features:
            raise NotImplementedError()

        if hvac_mode == HVACMode.OFF:
            self.vehicle.set_hvac_status(HVACAction.STOP)
            self._fetch_loop()
        elif hvac_mode == HVACMode.HEAT_COOL:
            self.vehicle.set_hvac_status(HVACAction.START)
            self._fetch_loop()

    def _fetch_loop(self):
        """Fetch every 5 seconds for 30s so we get a timely state update."""
        if self._loop_mutex:
            return
        
        _LOGGER.debug("Beginning HVAC fetch loop")
        self._loop_mutex = True
        for _ in range(6):
            asyncio.run_coroutine_threadsafe(
                self.coordinator.force_update(), self._hass.loop
            ).result()
            sleep(5)
        
        _LOGGER.debug("Ending HVAC fetch loop")
        self._loop_mutex = False
