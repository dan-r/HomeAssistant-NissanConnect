"""
Support for Kamereon Platform
"""
import logging

from homeassistant.components.climate import ClimateDevice
from homeassistant.components.climate.const import (HVAC_MODE_HEAT_COOL, HVAC_MODE_OFF, SUPPORT_TARGET_TEMPERATURE)
from homeassistant.const import ATTR_TEMPERATURE, STATE_UNKNOWN, TEMP_CELSIUS

SUPPORT_HVAC = [HVAC_MODE_HEAT_COOL, HVAC_MODE_OFF]

from . import KamereonEntity
from .kamereon import Feature, HVACAction, HVACStatus

_LOGGER = logging.getLogger(__name__)


def setup_platform(hass, config, add_devices, vehicle=None):
    """ Setup the volkswagen climate."""
    if vehicle is None:
        return
    if Feature.TEMPERATURE in vehicle.features or Feature.INTERIOR_TEMP_SETTINGS in vehicle.features:
        add_devices([KamereonClimate(vehicle)])


class KamereonClimate(KamereonEntity, ClimateDevice):
    """Representation of a Kamereon Climate."""

    @property
    def supported_features(self):
        """Return the list of supported features."""
        return SUPPORT_TARGET_TEMPERATURE

    @property
    def hvac_mode(self):
        """Return hvac operation ie. heat, cool mode.
        Need to be one of HVAC_MODE_*.
        """
        if self.vehicle.hvac_status is None:
            return STATE_UNKNOWN
        elif self.vehicle.hvac_status is HVACStatus.ON:
            return HVAC_MODE_HEAT_COOL
        return HVAC_MODE_OFF


    @property
    def hvac_modes(self):
        """Return the list of available hvac operation modes.
        Need to be a subset of HVAC_MODES.
        """
        return SUPPORT_HVAC

    @property
    def temperature_unit(self):
        """Return the unit of measurement."""
        return TEMP_CELSIUS

    @property
    def current_temperature(self):
        """Return the current temperature."""
        if self.vehicle.internal_temperature:
            return float(self.vehicle.internal_temperature)
        return None

    @property
    def target_temperature(self):
        """Return the temperature we try to reach."""
        if self.vehicle.next_target_temperature is not None:
            return float(self.vehicle.next_target_temperature)
        return None

    def set_temperature(self, **kwargs):
        """Set new target temperatures."""
        if Feature.TEMPERATURE not in self.vehicle.features:
            raise NotImplementedError()

        _LOGGER.debug("Setting temperature for: %s", self.instrument.attr)
        temperature = kwargs.get(ATTR_TEMPERATURE)
        if temperature:
            self.vehicle.set_hvac_status(HVACAction.START, temperature)

    def set_hvac_mode(self, hvac_mode):
        """Set new target hvac mode."""
        if Feature.CLIMATE_ON_OFF not in self.vehicle.features:
            raise NotImplementedError()

        _LOGGER.debug("Setting mode for: %s", self.instrument.attr)
        if hvac_mode == HVAC_MODE_OFF:
            self.vehicle.set_hvac_status(HVACAction.STOP)
        elif hvac_mode == HVAC_MODE_HEAT_COOL:
            self.vehicle.set_hvac_status(HVACAction.START)