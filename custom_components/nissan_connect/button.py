"""Support for Kamereon cars."""
import logging
import asyncio

from homeassistant.components.button import ButtonEntity

from .base import CAR_COMMAND_ERRORS, KamereonEntity, car_command_error
from .kamereon import Feature
from .const import DOMAIN, DATA_VEHICLES, DATA_COORDINATOR_POLL, DATA_COORDINATOR_FETCH, DATA_COORDINATOR_STATISTICS

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass, config, async_add_entities):
    account_id = config.data['email']

    data = hass.data[DOMAIN][account_id][DATA_VEHICLES]
    coordinator = hass.data[DOMAIN][account_id][DATA_COORDINATOR_POLL]
    coordinator_fetch = hass.data[DOMAIN][account_id][DATA_COORDINATOR_FETCH]
    stats_coordinator = hass.data[DOMAIN][account_id][DATA_COORDINATOR_STATISTICS]

    entities = []

    for vehicle in data:
        entities.append(ForceUpdateButton(coordinator_fetch, data[vehicle], hass, stats_coordinator))
        if Feature.HORN_AND_LIGHTS in data[vehicle].features:
            entities += [
                HornLightsButtons(coordinator, data[vehicle], "flash_lights", "mdi:car-light-high", "lights"),
                HornLightsButtons(coordinator, data[vehicle], "honk_horn", "mdi:bullhorn", "horn_lights")
            ]
        if Feature.CHARGING_START in data[vehicle].features:
            entities.append(ChargeControlButtons(coordinator, data[vehicle], "charge_start", "mdi:play", "start"))

    async_add_entities(entities, update_before_add=True)


class ForceUpdateButton(KamereonEntity, ButtonEntity):
    _attr_translation_key = "update_data"

    def __init__(self, coordinator, vehicle, hass, stats_coordinator):
        KamereonEntity.__init__(self, coordinator, vehicle)
        self._hass = hass
        self.coordinator_statistics = stats_coordinator
    
    @property
    def icon(self):
        """Return the icon."""
        return 'mdi:update'

    async def async_press(self):
        loop = asyncio.get_running_loop()

        try:
            updated = await loop.run_in_executor(None, self.vehicle.refresh_fetch)
        except CAR_COMMAND_ERRORS as err:
            raise car_command_error("update vehicle data", err) from err
        if updated:
            self.coordinator.async_set_updated_data(True)

class HornLightsButtons(KamereonEntity, ButtonEntity):
    def __init__(self, coordinator, vehicle, translation_key, icon, action):
        self._attr_translation_key = translation_key
        self._icon = icon
        self._action = action
        KamereonEntity.__init__(self, coordinator, vehicle)
    
    @property
    def icon(self):
        return self._icon

    def press(self):
        description = {
            "lights": "flash the lights",
            "horn": "sound the horn",
            "horn_lights": "sound the horn and flash the lights",
        }.get(self._action, "use the horn or lights")
        try:
            self.vehicle.control_horn_lights('start', self._action)
        except CAR_COMMAND_ERRORS as err:
            raise car_command_error(description, err) from err

class ChargeControlButtons(KamereonEntity, ButtonEntity):
    def __init__(self, coordinator, vehicle, translation_key, icon, action):
        self._attr_translation_key = translation_key
        self._icon = icon
        self._action = action
        KamereonEntity.__init__(self, coordinator, vehicle)
    
    @property
    def icon(self):
        return self._icon

    def press(self):
        try:
            self.vehicle.control_charging(self._action)
        except CAR_COMMAND_ERRORS as err:
            raise car_command_error(f"{self._action} charging", err) from err

