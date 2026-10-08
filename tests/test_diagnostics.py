import json
from datetime import timedelta
from unittest.mock import MagicMock

from homeassistant.components.diagnostics import REDACTED
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.nissan_connect.const import (
    DATA_COORDINATOR_FETCH,
    DATA_COORDINATOR_POLL,
    DATA_VEHICLES,
    DOMAIN,
)
from custom_components.nissan_connect.diagnostics import async_get_config_entry_diagnostics
from tests.test_micra import _micra


async def test_diagnostics_redact_and_serialize(hass, requests_mock):
    vehicle = _micra(requests_mock)
    vehicle.nickname = "My Micra"
    vehicle.registration_number = "AB-123-CD"
    vehicle.fetch_all()

    entry = MockConfigEntry(domain=DOMAIN, unique_id="test@example.com", data={
        "email": "test@example.com",
        "password": "test-password",
        "region": "EU",
        "interval": 0,
    })
    hass.data[DOMAIN] = {"test@example.com": {
        DATA_VEHICLES: {vehicle.vin: vehicle},
        DATA_COORDINATOR_FETCH: MagicMock(
            last_update_success=True, update_interval=timedelta(minutes=10)),
        DATA_COORDINATOR_POLL: MagicMock(
            last_update_success=False, update_interval=None),
    }}

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    dumped = json.dumps(diagnostics)
    for secret in ("test@example.com", "test-password", "TEST-VIN", "test-user",
                   "My Micra", "AB-123-CD", "12.34", "56.78"):
        assert secret not in dumped

    assert diagnostics["entry"]["email"] == REDACTED
    assert diagnostics["entry"]["region"] == "EU"
    assert diagnostics["coordinators"] == {
        "fetch": {"last_update_success": True, "update_interval_minutes": 10},
        "poll": {"last_update_success": False, "update_interval_minutes": None},
    }

    [car] = diagnostics["vehicles"]
    assert car["vin"] == REDACTED
    assert car["location"] == REDACTED
    assert car["model_name"] == "MICRA"
    assert car["vehicle_gateway"] == "RVG"
    assert car["cockpit_version"] == "v2"
    assert "MY_CAR_FINDER" in car["features"]
    assert car["battery_level"] == 57
    assert car["total_mileage"] == 12345.0
    assert car["location_last_updated"] == "2026-01-01T06:00:00+00:00"
