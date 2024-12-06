import pytest
from unittest.mock import AsyncMock, MagicMock
from homeassistant.components.climate.const import HVACMode, HVACAction as HASSHVACAction
from homeassistant.const import ATTR_TEMPERATURE, UnitOfTemperature
from custom_components.nissan_connect.climate import KamereonClimate
from custom_components.nissan_connect.kamereon.kamereon_const import Feature, HVACAction

@pytest.fixture
def mock_vehicle():
    vehicle = MagicMock()
    vehicle.features = [Feature.CLIMATE_ON_OFF, Feature.TEMPERATURE]
    vehicle.hvac_status = False
    vehicle.internal_temperature = 22
    return vehicle

@pytest.fixture
def mock_coordinator():
    return MagicMock()

@pytest.fixture
def mock_hass():
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock()
    hass.async_create_task = AsyncMock()
    return hass

@pytest.fixture
def climate_entity(mock_coordinator, mock_vehicle, mock_hass):
    return KamereonClimate(mock_coordinator, mock_vehicle, mock_hass)

def test_hvac_mode(climate_entity, mock_vehicle):
    mock_vehicle.hvac_status = True
    assert climate_entity.hvac_mode == HVACMode.HEAT_COOL
    mock_vehicle.hvac_status = False
    assert climate_entity.hvac_mode == HVACMode.OFF

def test_current_temperature(climate_entity, mock_vehicle):
    mock_vehicle.internal_temperature = 22
    assert climate_entity.current_temperature == 22
    mock_vehicle.internal_temperature = None
    assert climate_entity.current_temperature is None

def test_target_temperature(climate_entity):
    assert climate_entity.target_temperature == 20
    climate_entity.set_temperature(**{ATTR_TEMPERATURE: 25})
    assert climate_entity.target_temperature == 25

def test_hvac_action(climate_entity, mock_vehicle):
    mock_vehicle.hvac_status = True
    mock_vehicle.internal_temperature = 18
    climate_entity._target = 20
    assert climate_entity.hvac_action == HASSHVACAction.HEATING
    mock_vehicle.internal_temperature = 22
    assert climate_entity.hvac_action == HASSHVACAction.COOLING
    mock_vehicle.hvac_status = False
    assert climate_entity.hvac_action == HASSHVACAction.OFF

@pytest.mark.asyncio
async def test_async_set_hvac_mode(climate_entity, mock_hass, mock_vehicle):
    await climate_entity.async_set_hvac_mode(HVACMode.OFF)
    mock_hass.async_add_executor_job.assert_called_with(mock_vehicle.set_hvac_status, HVACAction.STOP)
    mock_hass.async_create_task.assert_called_once()

    await climate_entity.async_set_hvac_mode(HVACMode.HEAT_COOL)
    mock_hass.async_add_executor_job.assert_called_with(mock_vehicle.set_hvac_status, HVACAction.START, 20)
    assert mock_hass.async_create_task.call_count == 2

@pytest.mark.asyncio
async def test_async_turn_off(climate_entity):
    await climate_entity.async_turn_off()
    assert climate_entity.hvac_mode == HVACMode.OFF
