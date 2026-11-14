import pytest
import requests
from unittest.mock import AsyncMock, MagicMock
from homeassistant.exceptions import HomeAssistantError
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
    vehicle.refresh_fetch.return_value = True
    hass = AsyncMock()
    stats_coordinator = MagicMock()

    button = ForceUpdateButton(coordinator, vehicle, hass, stats_coordinator)

    await button.async_press()
    vehicle.refresh_fetch.assert_called_once()
    coordinator.async_set_updated_data.assert_called_once_with(True)


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


def test_charge_control_button_reports_request_failures():
    """Automations need HomeAssistantError so continue_on_error can catch it."""
    vehicle = MagicMock()
    vehicle.control_charging.side_effect = requests.ConnectionError(
        "('Connection aborted.', ConnectionResetError(104, 'Connection reset by peer'))"
    )
    button = ChargeControlButtons(
        MagicMock(), vehicle, "charge_start", "mdi:play", "start")

    with pytest.raises(HomeAssistantError, match="Unable to start charging"):
        button.press()


def test_horn_button_reports_request_failures():
    vehicle = MagicMock()
    vehicle.control_horn_lights.side_effect = requests.ConnectionError("aborted")
    button = HornLightsButtons(
        MagicMock(), vehicle, "flash_lights", "mdi:car-light-high", "lights")

    with pytest.raises(HomeAssistantError, match="Unable to flash the lights"):
        button.press()


@pytest.mark.asyncio
async def test_force_update_button_reports_request_failures():
    vehicle = MagicMock()
    vehicle.refresh_fetch.side_effect = requests.Timeout("read timed out")
    button = ForceUpdateButton(AsyncMock(), vehicle, AsyncMock(), MagicMock())

    with pytest.raises(HomeAssistantError, match="Unable to update vehicle data"):
        await button.async_press()
