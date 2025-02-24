import pytest
from unittest.mock import AsyncMock, MagicMock
from homeassistant.const import PERCENTAGE, UnitOfTemperature, UnitOfLength, UnitOfTime
from custom_components.nissan_connect.base import KamereonEntity
from custom_components.nissan_connect.kamereon import ChargingSpeed, Feature

from custom_components.nissan_connect.sensor import (
    BatteryLevelSensor,
    InternalTemperatureSensor,
    ExternalTemperatureSensor,
    RangeSensor,
    OdometerSensor,
    StatisticSensor,
    ChargeTimeRequiredSensor,
    TimestampSensor,
    async_setup_entry
)

@pytest.fixture
def mock_hass():
    hass = MagicMock()
    hass.data = {
        'nissan_connect': {
            'test_account': {
                'vehicles': {
                    'test_vehicle': MagicMock(
                        battery_level=80,
                        internal_temperature=22.5,
                        external_temperature=15.0,
                        range_hvac_on=100,
                        range_hvac_off=120,
                        total_mileage=5000,
                        charge_time_required_to_full={ChargingSpeed.NORMAL: 60, ChargingSpeed.FAST: 30, ChargingSpeed.ADAPTIVE: None},
                        features=[Feature.BATTERY_STATUS, Feature.DRIVING_JOURNEY_HISTORY]
                    )
                },
                'coordinator_fetch': AsyncMock(),
                'coordinator_statistics': AsyncMock()
            }
        }
    }
    return hass

@pytest.fixture
def mock_config():
    return MagicMock(data={'email': 'test_account', 'imperial_distance': False})

@pytest.fixture
def mock_async_add_entities():
    return AsyncMock()

@pytest.mark.asyncio
async def test_async_setup_entry(mock_hass, mock_config, mock_async_add_entities):
    await async_setup_entry(mock_hass, mock_config, mock_async_add_entities)
    assert mock_async_add_entities.call_count == 1
    entities = mock_async_add_entities.call_args[0][0]
    assert len(entities) > 0

def test_battery_level_sensor(mock_hass):
    vehicle = mock_hass.data['nissan_connect']['test_account']['vehicles']['test_vehicle']
    coordinator = mock_hass.data['nissan_connect']['test_account']['coordinator_fetch']
    sensor = BatteryLevelSensor(coordinator, vehicle)
    assert sensor.state == 80

def test_internal_temperature_sensor(mock_hass):
    vehicle = mock_hass.data['nissan_connect']['test_account']['vehicles']['test_vehicle']
    coordinator = mock_hass.data['nissan_connect']['test_account']['coordinator_fetch']
    sensor = InternalTemperatureSensor(coordinator, vehicle)
    assert sensor.native_value == 22.5

def test_external_temperature_sensor(mock_hass):
    vehicle = mock_hass.data['nissan_connect']['test_account']['vehicles']['test_vehicle']
    coordinator = mock_hass.data['nissan_connect']['test_account']['coordinator_fetch']
    sensor = ExternalTemperatureSensor(coordinator, vehicle)
    assert sensor.native_value == 15.0

def test_range_sensor(mock_hass):
    vehicle = mock_hass.data['nissan_connect']['test_account']['vehicles']['test_vehicle']
    coordinator = mock_hass.data['nissan_connect']['test_account']['coordinator_fetch']
    sensor = RangeSensor(coordinator, vehicle, True, False)
    assert sensor.native_value == 100

def test_odometer_sensor(mock_hass):
    vehicle = mock_hass.data['nissan_connect']['test_account']['vehicles']['test_vehicle']
    coordinator = mock_hass.data['nissan_connect']['test_account']['coordinator_fetch']
    sensor = OdometerSensor(coordinator, vehicle, False)
    sensor.async_write_ha_state = MagicMock()
    sensor._handle_coordinator_update()
    assert sensor.native_value == 5000

def test_charge_time_required_sensor(mock_hass):
    vehicle = mock_hass.data['nissan_connect']['test_account']['vehicles']['test_vehicle']
    coordinator = mock_hass.data['nissan_connect']['test_account']['coordinator_fetch']
    sensor = ChargeTimeRequiredSensor(coordinator, vehicle, ChargingSpeed.NORMAL)
    assert sensor.native_value == 60

def test_timestamp_sensor(mock_hass):
    vehicle = mock_hass.data['nissan_connect']['test_account']['vehicles']['test_vehicle']
    coordinator = mock_hass.data['nissan_connect']['test_account']['coordinator_fetch']
    sensor = TimestampSensor(coordinator, vehicle, 'battery_status_last_updated', 'last_updated', 'mdi:clock-time-eleven-outline')
