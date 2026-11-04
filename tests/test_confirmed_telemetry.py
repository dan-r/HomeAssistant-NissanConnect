"""Optional vehicle telemetry from existing Nissan responses."""

from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, Mock, patch

import pytest

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import PERCENTAGE, UnitOfLength, UnitOfTime, UnitOfVolume
from homeassistant.helpers import entity_registry
from homeassistant.helpers.entity_platform import EntityPlatform
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nissan_connect.kamereon import Feature
from custom_components.nissan_connect.kamereon.kamereon import USERS, Vehicle, _registry
from custom_components.nissan_connect.diagnostics import TO_REDACT, _vehicle_diagnostics
from custom_components.nissan_connect.sensor import async_setup_entry
from custom_components.nissan_connect import sensor as sensor_module


@pytest.fixture
def qashqai(monkeypatch):
    """Representative, synthetic values based on the Qashqai response shape."""
    session = SimpleNamespace(
        unique_id="account",
        tenant="nissan",
        settings={
            "car_adapter_base_url": "https://nissan.invalid/",
        },
    )
    monkeypatch.setitem(_registry[USERS], "test-user", session)
    vehicle = Vehicle(
        {
            "vin": "TEST-VIN",
            "services": [],
            "modelName": "Qashqai",
            "modelCode": "J12",
            "modelYear": 2021,
            "vehicleNickName": "Car",
            "nickname": "Legacy",
            "energy": "gasoline",
            "color": "Blue",
            "pictureURL": "https://nissan.invalid/car.png",
            "ivc": {"swVersion": " IVC-1 ", "version": "IVC-V", "imei": "PRIVATE"},
            "ivi": {
                "supplierSwVersion": " IVI-2 ",
                "version": "IVI-V",
                "type": "ePower",
                "iviId": "PRIVATE",
            },
        },
        "test-user",
    )
    vehicle.features = [Feature.MY_CAR_FINDER, Feature.DRIVING_JOURNEY_HISTORY]
    vehicle.battery_level = 57
    vehicle.fuel_autonomy = 150
    vehicle._fetch_cockpit_attributes = Mock(
        return_value={"totalMileage": 65452, "dueMileage": 78085, "fuelAutonomy": 150}
    )
    vehicle.fetch_cockpit()
    vehicle._get = Mock(
        return_value=Mock(
            json=lambda: {
                "data": {
                    "attributes": {
                        "gpsLatitude": 1.0,
                        "gpsLongitude": 2.0,
                        "gpsDirection": 258.0,
                        "lastUpdateTime": "2026-10-26T10:00:00Z",
                    }
                }
            }
        )
    )
    vehicle.fetch_location()
    return vehicle


async def entities_for(vehicle, daily=None, monthly=None):
    today = datetime.now(timezone.utc).date()
    daily = daily or SimpleNamespace(
        start=today, end=today, consumed_fuel=1.25, total_duration=64
    )
    monthly = monthly or SimpleNamespace(
        start=today.replace(day=1), end=today, consumed_fuel=50.5, total_duration=1400
    )
    stats = MagicMock(
        data={vehicle.vin: {"daily": [daily], "monthly": [monthly]}},
        last_update_success=True,
    )
    fetch = MagicMock(last_update_success=True)
    hass = SimpleNamespace(
        data={
            "nissan_connect": {
                "test": {
                    "vehicles": {vehicle.vin: vehicle},
                    "coordinator_fetch": fetch,
                    "coordinator_statistics": stats,
                }
            }
        }
    )
    result = []
    await async_setup_entry(
        hass,
        SimpleNamespace(data={"email": "test"}),
        lambda entities, **kwargs: result.extend(entities),
    )
    return {entity._attr_translation_key: entity for entity in result}


async def test_qashqai_exposes_confirmed_fields(qashqai):
    entities = await entities_for(qashqai)
    expected = {
        "api_battery_level",
        "api_gps_direction",
        "service_due_mileage",
        "vehicle_information",
        "ivc_software_version",
        "ivi_supplier_software_version",
        "daily_consumed_fuel",
        "monthly_consumed_fuel",
        "daily_driving_duration",
        "monthly_driving_duration",
    }
    assert expected <= entities.keys()
    assert entities["api_battery_level"].native_value == 57
    assert entities["api_battery_level"].native_unit_of_measurement == PERCENTAGE
    assert entities["api_battery_level"].icon == "mdi:battery"
    assert (
        entities["api_battery_level"].extra_state_attributes["api_key"]
        == "batteryLevel"
    )
    assert entities["api_gps_direction"].native_value == 258.0
    assert entities["api_gps_direction"].native_unit_of_measurement is None
    assert entities["service_due_mileage"].native_value == 78085
    assert (
        entities["service_due_mileage"].native_unit_of_measurement
        == UnitOfLength.KILOMETERS
    )
    assert entities["ivc_software_version"].native_value == "IVC-1"
    assert (
        entities["ivc_software_version"].extra_state_attributes["api_key"]
        == "ivc.swVersion"
    )
    assert entities["ivi_supplier_software_version"].native_value == "IVI-2"
    metadata = entities["vehicle_information"].extra_state_attributes
    assert {
        key: metadata[key]
        for key in ("modelName", "vehicleNickName", "energy", "color", "pictureURL")
    } == {
        "modelName": "Qashqai",
        "vehicleNickName": "Car",
        "energy": "gasoline",
        "color": "Blue",
        "pictureURL": "https://nissan.invalid/car.png",
    }
    assert metadata["ivc"] == {"version": "IVC-V"}
    assert metadata["ivi"] == {"version": "IVI-V", "type": "ePower"}
    assert "imei" not in str(metadata) and "iviId" not in str(metadata)
    for key, value, unit in (
        ("daily_consumed_fuel", 1.25, UnitOfVolume.LITERS),
        ("monthly_consumed_fuel", 50.5, UnitOfVolume.LITERS),
        ("daily_driving_duration", 64, UnitOfTime.MINUTES),
        ("monthly_driving_duration", 1400, UnitOfTime.MINUTES),
    ):
        entities[key].async_write_ha_state = Mock()
        entities[key]._handle_coordinator_update()
        assert entities[key].native_value == value
        assert entities[key].native_unit_of_measurement == unit


async def test_optional_values_zero_and_no_duplicate_battery(qashqai):
    qashqai.battery_level = 0
    qashqai.gps_direction = 0
    qashqai.due_mileage = 0
    entities = await entities_for(qashqai)
    assert entities["api_battery_level"].native_value == 0
    assert entities["api_gps_direction"].native_value == 0
    assert entities["service_due_mileage"].native_value == 0
    assert entities["api_battery_level"].available
    entities["api_battery_level"].coordinator.last_update_success = False
    assert not entities["api_battery_level"].available
    fuel = entities["daily_consumed_fuel"]
    fuel.async_write_ha_state = Mock()
    fuel._handle_coordinator_update()
    assert fuel.available
    fuel.coordinator.last_update_success = False
    assert not fuel.available
    qashqai.features.append(Feature.BATTERY_STATUS)
    entities = await entities_for(qashqai)
    assert "battery_level" in entities
    assert "api_battery_level" not in entities
    qashqai.features.remove(Feature.BATTERY_STATUS)
    qashqai.battery_level = qashqai.gps_direction = qashqai.due_mileage = None
    entities = await entities_for(qashqai)
    assert (
        not {"api_battery_level", "api_gps_direction", "service_due_mileage"}
        & entities.keys()
    )


async def test_new_entity_identities_and_sensor_classes(qashqai):
    entities = await entities_for(qashqai)
    assert (
        entities["api_battery_level"].unique_id == "account_TEST-VIN_api_battery_level"
    )
    assert entities["api_battery_level"].device_class == SensorDeviceClass.BATTERY
    assert entities["service_due_mileage"].device_class == SensorDeviceClass.DISTANCE
    assert entities["daily_driving_duration"].device_class == SensorDeviceClass.DURATION
    qashqai.session.unique_id = None
    assert entities["api_battery_level"].unique_id == "TEST-VIN_api_battery_level"


def test_location_and_cockpit_missing_values_are_not_invented(qashqai):
    qashqai._fetch_cockpit_attributes.return_value = {"totalMileage": 0}
    qashqai.fetch_cockpit()
    assert qashqai.due_mileage is None
    qashqai._get.return_value = Mock(
        json=lambda: {
            "data": {
                "attributes": {
                    "gpsLatitude": 0,
                    "gpsLongitude": 0,
                    "lastUpdateTime": "2026-10-26T10:00:00Z",
                }
            }
        }
    )
    qashqai.fetch_location()
    assert qashqai.gps_direction is None
    assert qashqai.location == (0, 0)


async def test_current_trip_totals_distinguish_empty_missing_and_stale(qashqai):
    entities = await entities_for(qashqai)
    entity = entities["daily_consumed_fuel"]
    entity.async_write_ha_state = Mock()
    summaries = entity.coordinator.data[qashqai.vin]
    entity._handle_coordinator_update()
    assert entity.native_value == 1.25
    summaries["daily"] = []
    entity._handle_coordinator_update()
    assert entity.native_value == 0
    summaries.pop("daily")
    entity._handle_coordinator_update()
    assert entity.native_value is None
    yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
    summaries["daily"] = [
        SimpleNamespace(start=yesterday, end=yesterday, consumed_fuel=4)
    ]
    entity._handle_coordinator_update()
    assert entity.native_value is None
    today = datetime.now(timezone.utc).date()
    summaries["daily"] = [
        SimpleNamespace(start=today, end="malformed", consumed_fuel=4)
    ]
    entity._handle_coordinator_update()
    assert entity.native_value is None
    summaries["daily"] = [SimpleNamespace(start=today, end=today, consumed_fuel=None)]
    entity._handle_coordinator_update()
    assert entity.native_value is None


def test_diagnostics_do_not_export_new_private_metadata(qashqai):
    diagnostics = async_redact_data(_vehicle_diagnostics(qashqai), TO_REDACT)
    text = str(diagnostics)
    assert "PRIVATE" not in text
    assert "nissan.invalid/car.png" not in text
    assert "Car" not in text


@pytest.mark.parametrize("language", ["en", "it"])
async def test_new_entities_register_with_english_ids(hass, qashqai, language):
    """Use Home Assistant's real entity registry and translation handling."""
    hass.config.language = language
    today = datetime.now(timezone.utc).date()
    daily = SimpleNamespace(
        start=today, end=today, consumed_fuel=1.25, total_duration=64
    )
    monthly = SimpleNamespace(
        start=today.replace(day=1), end=today, consumed_fuel=50.5, total_duration=1400
    )
    fetch = SimpleNamespace(
        last_update_success=True, async_add_listener=Mock(return_value=lambda: None)
    )
    stats = SimpleNamespace(
        last_update_success=True,
        async_add_listener=Mock(return_value=lambda: None),
        data={qashqai.vin: {"daily": [daily], "monthly": [monthly]}},
    )
    hass.data["nissan_connect"] = {
        "test": {
            "vehicles": {qashqai.vin: qashqai},
            "coordinator_fetch": fetch,
            "coordinator_statistics": stats,
        }
    }
    entry = MockConfigEntry(
        domain="nissan_connect",
        title="Synthetic Nissan",
        data={"email": "test"},
        unique_id="account",
    )
    entry.add_to_hass(hass)
    platform = EntityPlatform(
        hass=hass,
        logger=logging.getLogger(__name__),
        domain="sensor",
        platform_name="nissan_connect",
        platform=sensor_module,
        scan_interval=timedelta(seconds=30),
        entity_namespace=None,
    )
    try:
        original_load = platform.platform_data.async_load_translations

        async def load_translations():
            await original_load()
            platform.platform_data.object_id_platform_translations = (
                platform.platform_data.platform_translations
            )

        with patch.object(
            platform.platform_data, "async_load_translations", load_translations
        ):
            await platform.async_setup_entry(entry)
        entities = {
            entity._attr_translation_key: entity
            for entity in platform.entities.values()
        }
        registry = entity_registry.async_get(hass)
        translations = Path("custom_components/nissan_connect/translations")
        names = json.loads((translations / f"{language}.json").read_text())["entity"][
            "sensor"
        ]
        for key in (
            "api_battery_level",
            "api_gps_direction",
            "service_due_mileage",
            "vehicle_information",
            "ivc_software_version",
            "ivi_supplier_software_version",
            "daily_consumed_fuel",
            "monthly_consumed_fuel",
            "daily_driving_duration",
            "monthly_driving_duration",
        ):
            entity = entities[key]
            record = registry.async_get(entity.entity_id)
            assert entity.entity_id.endswith("_" + key)
            assert record.unique_id == f"account_TEST-VIN_{key}"
            assert record.translation_key == key
            assert entity.name == names[key]["name"]
            assert entity.name[0].isupper()
    finally:
        await platform.async_reset()
