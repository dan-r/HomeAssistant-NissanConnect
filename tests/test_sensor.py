import pytest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.const import (
    PERCENTAGE, UnitOfLength, UnitOfVolume)
from custom_components.nissan_connect.kamereon import ChargingSpeed, Feature
from custom_components.nissan_connect.const import DOMAIN

from custom_components.nissan_connect.sensor import (
    BatteryLevelSensor,
    InternalTemperatureSensor,
    ExternalTemperatureSensor,
    RangeSensor,
    OdometerSensor,
    ChargeTimeRequiredSensor,
    TimestampSensor,
    FuelRangeSensor,
    FuelQuantitySensor,
    FuelLevelSensor,
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
    vehicle.battery_status_last_updated = datetime(2026, 1, 1, 10, 0, tzinfo=timezone.utc)
    assert sensor.state == "2026-01-01T10:00:00+00:00"
    vehicle.battery_status_last_updated = None
    assert sensor.state is None


@pytest.fixture
def ice_vehicle():
    """A petrol Townstar: cockpit data, no EV features at all.

    Values are from a real 2021 Townstar (dan-r/HomeAssistant-NissanConnect#109),
    whose v2 cockpit response carries fuelAutonomy, fuelQuantity and
    totalMileage but no fuelLevel.
    """
    return MagicMock(
        fuel_autonomy=671.0,
        fuel_quantity=52.0,
        fuel_level=None,
        total_mileage=2580.0,
        internal_temperature=None,
        external_temperature=None,
        range_hvac_on=None,
        range_hvac_off=None,
        charge_time_required_to_full={
            ChargingSpeed.NORMAL: None, ChargingSpeed.FAST: None,
            ChargingSpeed.ADAPTIVE: None},
        features=[Feature.MY_CAR_FINDER],
    )


def test_fuel_range_sensor(ice_vehicle):
    sensor = FuelRangeSensor(MagicMock(), ice_vehicle, False)
    assert sensor.native_value == 671.0
    assert sensor.native_unit_of_measurement == UnitOfLength.KILOMETERS
    assert sensor.device_class == SensorDeviceClass.DISTANCE


def test_fuel_range_sensor_honours_imperial(ice_vehicle):
    sensor = FuelRangeSensor(MagicMock(), ice_vehicle, True)
    assert sensor.suggested_unit_of_measurement == UnitOfLength.MILES


def test_fuel_quantity_sensor(ice_vehicle):
    sensor = FuelQuantitySensor(MagicMock(), ice_vehicle)
    assert sensor.native_value == 52.0
    assert sensor.native_unit_of_measurement == UnitOfVolume.LITERS
    assert sensor.device_class == SensorDeviceClass.VOLUME_STORAGE


def test_fuel_level_sensor(ice_vehicle):
    ice_vehicle.fuel_level = 62
    sensor = FuelLevelSensor(MagicMock(), ice_vehicle)
    assert sensor.native_value == 62
    assert sensor.native_unit_of_measurement == PERCENTAGE


async def test_ice_vehicle_gets_fuel_sensors(mock_hass, mock_config,
                                             mock_async_add_entities, ice_vehicle):
    """A petrol car must surface the cockpit data it already fetches."""
    mock_hass.data['nissan_connect']['test_account']['vehicles'] = {
        'townstar': ice_vehicle}

    await async_setup_entry(mock_hass, mock_config, mock_async_add_entities)

    keys = {e._attr_translation_key for e in mock_async_add_entities.call_args[0][0]}
    assert 'fuel_range' in keys
    assert 'fuel_quantity' in keys
    # No fuelLevel in this car's response, so no percentage sensor
    assert 'fuel_level' not in keys
    # and still nothing EV-shaped
    assert not {'battery_level', 'range_ac_on', 'range_ac_off'} & keys


async def test_ev_reporting_a_zero_fuel_quantity_gets_no_fuel_sensor(mock_hass, mock_config,
                                                                    mock_async_add_entities):
    """The new Micra EV answers fuelQuantity 0.0 in its cockpit."""
    vehicle = mock_hass.data['nissan_connect']['test_account']['vehicles']['test_vehicle']
    vehicle.fuel_autonomy = None
    vehicle.fuel_quantity = 0.0
    vehicle.fuel_level = None

    await async_setup_entry(mock_hass, mock_config, mock_async_add_entities)

    keys = {e._attr_translation_key for e in mock_async_add_entities.call_args[0][0]}
    assert 'fuel_quantity' not in keys


async def test_ev_does_not_gain_fuel_sensors(mock_hass, mock_config,
                                             mock_async_add_entities):
    """The EV fixture has no cockpit fuel data, so nothing new appears."""
    vehicle = mock_hass.data['nissan_connect']['test_account']['vehicles']['test_vehicle']
    vehicle.fuel_autonomy = None
    vehicle.fuel_quantity = None
    vehicle.fuel_level = None

    await async_setup_entry(mock_hass, mock_config, mock_async_add_entities)

    keys = {e._attr_translation_key for e in mock_async_add_entities.call_args[0][0]}
    assert not {'fuel_range', 'fuel_quantity', 'fuel_level'} & keys


@pytest.fixture
async def sensor_component(hass):
    import logging
    from homeassistant.helpers.entity_component import EntityComponent
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    entry = MockConfigEntry(domain=DOMAIN, data={})
    entry.add_to_hass(hass)
    component = EntityComponent(logging.getLogger(__name__), "sensor", hass)
    component._platforms["sensor"].config_entry = entry
    yield component
    await component._async_reset()


async def test_odometer_availability_updates_without_mileage_change(
    hass, sensor_component
):
    """Failure and recovery must reach HA even while the car is parked."""
    coordinator = MagicMock(last_update_success=True)
    vehicle = SimpleNamespace(
        vin="test-vin",
        total_mileage=5000,
        nickname="Test car",
        model_name="Leaf",
        model_year=2025,
        model_code="TEST",
        session=SimpleNamespace(unique_id="test-only", tenant="nissan"),
    )
    sensor = OdometerSensor(coordinator, vehicle, False)
    sensor.entity_id = "sensor.test_odometer"
    await sensor_component.async_add_entities([sensor])
    sensor._handle_coordinator_update()
    assert hass.states.get(sensor.entity_id).state == "5000"
    for success, state in ((False, "unavailable"), (True, "5000")):
        coordinator.last_update_success = success
        sensor._handle_coordinator_update()
        assert hass.states.get(sensor.entity_id).state == state
    vehicle.total_mileage = 4999
    sensor._handle_coordinator_update()
    assert hass.states.get(sensor.entity_id).state == "5000"


async def test_statistics_availability_updates_before_first_data(
    hass, sensor_component
):
    """A failed first refresh must publish unavailable with no cached summary."""
    from custom_components.nissan_connect.sensor import StatisticSensor

    coordinator = MagicMock(last_update_success=True, data=None)
    vehicle = SimpleNamespace(
        vin="test-vin",
        nickname="Test car",
        model_name="Leaf",
        model_year=2025,
        model_code="TEST",
        session=SimpleNamespace(unique_id="test-only", tenant="nissan"),
    )
    sensor = StatisticSensor(
        coordinator,
        vehicle,
        "daily",
        lambda row: row["distance"],
        "distance",
        "mdi:map-marker-distance",
        None,
        None,
        0,
    )
    sensor.entity_id = "sensor.test_statistics"
    await sensor_component.async_add_entities([sensor])
    coordinator.last_update_success = False
    sensor._handle_coordinator_update()
    assert hass.states.get(sensor.entity_id).state == "unavailable"
    coordinator.data = {"test-vin": {"daily": [{"distance": 12}]}}
    coordinator.last_update_success = True
    sensor._handle_coordinator_update()
    assert hass.states.get(sensor.entity_id).state == "12"
