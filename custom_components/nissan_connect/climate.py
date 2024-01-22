"""
Support for Kamereon Platform
"""
import logging
import asyncio
from time import sleep
from homeassistant.components.climate import ClimateEntity
from homeassistant.components.climate.const import (HVACMode, ClimateEntityFeature)
from homeassistant.components.climate.const import HVACAction as HASSHVACAction
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
        if Feature.CLIMATE_ON_OFF in data[vehicle].features:
            async_add_entities([KamereonClimate(coordinator, data[vehicle], hass)], update_before_add=True)


class KamereonClimate(KamereonEntity, ClimateEntity):
    """Representation of a Kamereon Climate."""
    _attr_supported_features = ClimateEntityFeature.TARGET_TEMPERATURE
    _attr_hvac_modes = SUPPORT_HVAC
    _attr_temperature_unit = UnitOfTemperature.CELSIUS
    _attr_translation_key = "climate"
    _attr_min_temp = 16
    _attr_max_temp = 26
    _attr_target_temperature_step = 1
    _target = 20
    _loop_mutex = False

    def __init__(self, coordinator, vehicle, hass):
        KamereonEntity.__init__(self, coordinator, vehicle)
        self._hass = hass

    @property
    def hvac_mode(self):
        if self.vehicle.hvac_status is None:
            return HVACMode.OFF
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
    
    @property
    def hvac_action(self):
        """Shows heating or cooling depending on temperature."""
        if self.vehicle.hvac_status is not None and self.vehicle.hvac_status is HVACStatus.ON:
            if self._target < self.vehicle.internal_temperature:
                return HASSHVACAction.COOLING
            else:
                return HASSHVACAction.HEATING
        return HASSHVACAction.OFF

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
            self._fetch_loop(HVACStatus.OFF)
        elif hvac_mode == HVACMode.HEAT_COOL:
            self.vehicle.set_hvac_status(HVACAction.START, int(self._target))
            self._fetch_loop(HVACStatus.ON)

    def _fetch_loop(self, target_state):
        """Fetch every 5 seconds for 30s so we get a timely state update."""
        if self._loop_mutex:
            return
        
        _LOGGER.debug("Beginning HVAC fetch loop")
        self._loop_mutex = True
        for _ in range(6):
            asyncio.run_coroutine_threadsafe(
                self.coordinator.force_update(), self._hass.loop
            ).result()

            # We have our update, break out
            if target_state == self.vehicle.hvac_status:
                _LOGGER.debug("Breaking out of HVAC fetch loop")
                break

            sleep(5)
        
        _LOGGER.debug("Ending HVAC fetch loop")
        self._loop_mutex = False
