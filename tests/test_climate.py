import datetime
import importlib
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import homeassistant.components.climate as climate_platform
from custom_components.nissan_connect import climate
from homeassistant.components.climate.const import HVACMode, HVACAction as HASSHVACAction
from homeassistant.const import ATTR_TEMPERATURE
from homeassistant.exceptions import ServiceValidationError
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
    assert climate_entity.native_current_temperature == 22
    mock_vehicle.internal_temperature = None
    assert climate_entity.native_current_temperature is None

def test_target_temperature(climate_entity):
    assert climate_entity.native_target_temperature == 20
    climate_entity.set_temperature(**{ATTR_TEMPERATURE: 25})
    assert climate_entity.native_target_temperature == 25

def test_temperature_api_does_not_warn_on_import(caplog):
    with caplog.at_level('WARNING'):
        importlib.reload(climate)
    assert not any('deprecated' in record.message for record in caplog.records)

def test_legacy_temperature_api(mock_coordinator, mock_vehicle, mock_hass):
    class LegacyClimate:
        """Climate interface before the native temperature properties existed."""

    try:
        with patch.object(climate_platform, 'ClimateEntity', LegacyClimate):
            module = importlib.reload(climate)
            entity = module.KamereonClimate(mock_coordinator, mock_vehicle, mock_hass)
            assert entity._attr_temperature_unit == '°C'
            assert entity.current_temperature == 22
            assert entity.target_temperature == 20
            entity.set_temperature(**{ATTR_TEMPERATURE: 25})
            assert entity.target_temperature == 25
    finally:
        importlib.reload(climate)

def test_target_temperature_refused_while_running_without_temperature_service(climate_entity, mock_vehicle):
    mock_vehicle.features = [Feature.CLIMATE_ON_OFF]
    mock_vehicle.hvac_status = True
    with pytest.raises(ServiceValidationError):
        climate_entity.set_temperature(**{ATTR_TEMPERATURE: 25})
    assert climate_entity.native_target_temperature == 20
    mock_vehicle.set_hvac_status.assert_not_called()

def test_target_temperature_sent_while_running_with_temperature_service(climate_entity, mock_vehicle):
    mock_vehicle.hvac_status = True
    climate_entity.set_temperature(**{ATTR_TEMPERATURE: 25})
    mock_vehicle.set_hvac_status.assert_called_once_with(HVACAction.START, 25)

def test_hvac_action(climate_entity, mock_vehicle):
    mock_vehicle.hvac_status = True
    mock_vehicle.internal_temperature = 18
    climate_entity._target = 20
    assert climate_entity.hvac_action == HASSHVACAction.HEATING
    mock_vehicle.internal_temperature = 22
    assert climate_entity.hvac_action == HASSHVACAction.COOLING
    mock_vehicle.hvac_status = False
    assert climate_entity.hvac_action == HASSHVACAction.OFF

def test_hvac_action_without_interior_temperature(climate_entity, mock_vehicle):
    mock_vehicle.hvac_status = True
    mock_vehicle.internal_temperature = None
    assert climate_entity.hvac_action is None
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


def test_hvac_status_last_updated_attribute(climate_entity, mock_vehicle):
    mock_vehicle.hvac_status_last_updated = datetime.datetime(2026, 11, 14, 20, 37, 18, tzinfo=datetime.timezone.utc)
    assert climate_entity.extra_state_attributes == {"hvac_status_last_updated": "2026-11-14T20:37:18+00:00"}
    mock_vehicle.hvac_status_last_updated = None
    assert climate_entity.extra_state_attributes == {"hvac_status_last_updated": None}


def _utc_now(**offset):
    return datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(**offset)


@pytest.fixture
def fetch_loop(climate_entity, mock_coordinator):
    """Runs the post-command fetch loop without real sleeps."""
    mock_coordinator.async_refresh = AsyncMock()

    async def run(target_state):
        with patch("custom_components.nissan_connect.climate.asyncio.sleep", new=AsyncMock()):
            await climate_entity._async_fetch_loop(target_state)

    return run


@pytest.mark.asyncio
async def test_fetch_loop_ignores_a_stale_matching_status(fetch_loop, mock_vehicle, mock_coordinator):
    """An "on" left over from an earlier session is not a confirmation."""
    mock_vehicle.hvac_status = True
    mock_vehicle.hvac_status_last_updated = _utc_now(minutes=-10)

    await fetch_loop(True)

    assert mock_coordinator.async_refresh.call_count == 10
    assert mock_vehicle.refresh_hvac_status.call_count == 3
    mock_vehicle.refresh.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_loop_stops_on_a_fresh_status(fetch_loop, mock_vehicle, mock_coordinator):
    mock_vehicle.hvac_status = False
    mock_vehicle.hvac_status_last_updated = _utc_now(minutes=-10)

    async def car_reports_on():
        if mock_coordinator.async_refresh.call_count == 2:
            mock_vehicle.hvac_status = True
            mock_vehicle.hvac_status_last_updated = _utc_now()
    mock_coordinator.async_refresh.side_effect = car_reports_on

    await fetch_loop(True)

    assert mock_coordinator.async_refresh.call_count == 2
    assert mock_vehicle.refresh_hvac_status.call_count == 1


@pytest.mark.asyncio
async def test_fetch_loop_accepts_a_naive_timestamp_as_utc(fetch_loop, mock_vehicle, mock_coordinator):
    mock_vehicle.hvac_status = True
    mock_vehicle.hvac_status_last_updated = _utc_now().replace(tzinfo=None)

    await fetch_loop(True)

    assert mock_coordinator.async_refresh.call_count == 1


@pytest.mark.asyncio
async def test_fetch_loop_keeps_going_when_hvac_refresh_fails(fetch_loop, climate_entity, mock_vehicle, mock_coordinator, caplog):
    mock_vehicle.vin = "TEST-VIN"
    mock_vehicle.hvac_status = False
    mock_vehicle.hvac_status_last_updated = None
    mock_vehicle.refresh_hvac_status.side_effect = ValueError(
        "Not supported Feature for /v1/cars/TEST-VIN/actions/refresh-hvac-status")

    with caplog.at_level("DEBUG", logger="custom_components.nissan_connect.climate"):
        await fetch_loop(True)

    assert mock_coordinator.async_refresh.call_count == 10
    assert climate_entity._loop_mutex is False
    assert "refresh_hvac_status failed for #VIN" in caplog.text
    assert "TEST-VIN" not in caplog.text
