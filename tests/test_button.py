import pytest
from unittest.mock import AsyncMock, MagicMock
from homeassistant.helpers import entity_registry as er
from custom_components.nissan_connect.const import DOMAIN, DATA_VEHICLES, DATA_COORDINATOR_POLL, DATA_COORDINATOR_FETCH, DATA_COORDINATOR_STATISTICS
from custom_components.nissan_connect.kamereon.kamereon_const import Feature

from custom_components.nissan_connect.button import (
    async_setup_entry,
    ForceUpdateButton,
    HornLightsButtons,
    ChargeControlButtons,
)


@pytest.fixture
def mock_hass():
    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            'test_account': {
                DATA_VEHICLES: {
                    'vehicle_1': MagicMock(features=[Feature.HORN_AND_LIGHTS, Feature.CHARGING_START])
                },
                DATA_COORDINATOR_POLL: MagicMock(),
                DATA_COORDINATOR_FETCH: MagicMock(),
                DATA_COORDINATOR_STATISTICS: MagicMock(),
            }
        }
    }
    return hass


@pytest.fixture
def mock_config():
    return MagicMock(data={'email': 'test_account'})


@pytest.fixture
def mock_async_add_entities():
    return AsyncMock()


@pytest.mark.asyncio
async def test_async_setup_entry(mock_hass, mock_config, mock_async_add_entities):
    await async_setup_entry(mock_hass, mock_config, mock_async_add_entities)
    assert mock_async_add_entities.call_count == 1
    entities = mock_async_add_entities.call_args[0][0]
    assert len(entities) == 4
    assert isinstance(entities[0], ForceUpdateButton)
    assert isinstance(entities[1], HornLightsButtons)
    assert isinstance(entities[2], HornLightsButtons)
    assert isinstance(entities[3], ChargeControlButtons)


@pytest.mark.asyncio
async def test_force_update_button():
    coordinator = AsyncMock()
    vehicle = MagicMock()
    hass = AsyncMock()
    stats_coordinator = MagicMock()

    button = ForceUpdateButton(coordinator, vehicle, hass, stats_coordinator)

    await button.async_press()
    vehicle.refresh.assert_called_once()
    coordinator.async_refresh.assert_called_once()


def test_horn_lights_buttons():
    coordinator = MagicMock()
    vehicle = MagicMock()
    button = HornLightsButtons(
        coordinator, vehicle, "flash_lights", "mdi:car-light-high", "lights")

    button.press()
    vehicle.control_horn_lights.assert_called_once_with('start', "lights")


def test_charge_control_buttons():
    coordinator = MagicMock()
    vehicle = MagicMock()
    button = ChargeControlButtons(
        coordinator, vehicle, "charge_start", "mdi:play", "start")

    button.press()
    vehicle.control_charging.assert_called_once_with("start")
