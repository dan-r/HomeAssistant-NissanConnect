from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.nissan_connect import (
    async_migrate_entry,
    async_setup_entry,
    async_update_listener,
)
from custom_components.nissan_connect.const import (
    CONFIG_VERSION,
    DATA_COORDINATOR_FETCH,
    DATA_COORDINATOR_STATISTICS,
    DATA_VEHICLES,
    DOMAIN,
)
from custom_components.nissan_connect.kamereon import NissanAuthError
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_setup_entry_raises_auth_failed_for_invalid_credentials(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="test@example.com",
        data={
            "email": "test@example.com",
            "password": "wrong-password",
            "region": "EU",
        },
    )
    entry.add_to_hass(hass)
    login_error = NissanAuthError("Invalid credentials")

    with patch("custom_components.nissan_connect.NCISession") as mock_session:
        mock_session.return_value.login.side_effect = login_error
        with pytest.raises(ConfigEntryAuthFailed) as error_info:
            await async_setup_entry(hass, entry)

    assert error_info.value.__cause__ is login_error


async def test_setup_entry_retries_transient_login_failure(hass, caplog):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="test@example.com",
        data={
            "email": "test@example.com",
            "password": "test-password",
            "region": "EU",
        },
    )
    entry.add_to_hass(hass)
    login_error = RuntimeError("Unable to contact Nissan login")

    with patch("custom_components.nissan_connect.NCISession") as mock_session:
        mock_session.return_value.login.side_effect = login_error
        with pytest.raises(ConfigEntryNotReady) as error_info:
            await async_setup_entry(hass, entry)

    assert error_info.value.__cause__ is login_error
    assert "Login failed, will retry: Unable to contact Nissan login" in caplog.text


async def test_update_listener_logs_in_shared_session_once():
    session = MagicMock()
    fetch_coordinator = MagicMock()
    fetch_coordinator.async_refresh = AsyncMock()
    statistics_coordinator = MagicMock()
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock()
    hass.data = {
        DOMAIN: {
            "test@example.com": {
                DATA_VEHICLES: {
                    "vin-1": MagicMock(session=session),
                    "vin-2": MagicMock(session=session),
                },
                DATA_COORDINATOR_FETCH: fetch_coordinator,
                DATA_COORDINATOR_STATISTICS: statistics_coordinator,
            }
        }
    }
    entry = MagicMock(data={
        "email": "test@example.com",
        "password": "test-password",
        "interval_fetch": 10,
        "interval_statistics": 60,
    })

    await async_update_listener(hass, entry)

    hass.async_add_executor_job.assert_awaited_once_with(
        session.login,
        "test@example.com",
        "test-password",
    )
    assert fetch_coordinator.update_interval == timedelta(minutes=10)
    assert statistics_coordinator.update_interval == timedelta(minutes=60)
    fetch_coordinator.async_refresh.assert_awaited_once_with()


async def test_migrate_entry_leaves_current_version_alone(hass):
    data = {
        "email": "test@example.com",
        "password": "test-password",
        "region": "EU",
    }
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=CONFIG_VERSION,
        data=data,
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == CONFIG_VERSION
    assert entry.data == data


async def test_migrate_entry_refuses_backwards_migration(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=CONFIG_VERSION + 1,
        data={"email": "test@example.com", "region": "EU"},
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is False


async def test_setup_rewrites_legacy_device_identifiers(hass):
    """(domain, tenant, vin) becomes (domain, vin), in place.

    Updating rather than recreating the device is what keeps its entities,
    their entity IDs and the user's rename.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="a@b.c",
        data={"email": "a@b.c", "password": "p", "region": "EU"},
    )
    entry.add_to_hass(hass)
    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, "nissan", "TEST-VIN")},
        name="Car",
    )
    device_registry.async_update_device(device.id, name_by_user="My Leaf")
    entity = entity_registry.async_get_or_create(
        "sensor", DOMAIN, "a@b.c_TEST-VIN_battery_level",
        config_entry=entry, device_id=device.id,
        suggested_object_id="my_leaf_battery_level",
    )

    coordinator = MagicMock()
    coordinator.async_config_entry_first_refresh = AsyncMock()
    with (
        patch("custom_components.nissan_connect.NCISession") as mock_session,
        patch(
            "homeassistant.config_entries.ConfigEntries.async_forward_entry_setups"
        ),
        patch("custom_components.nissan_connect.KamereonFetchCoordinator",
              return_value=coordinator),
        patch("custom_components.nissan_connect.KamereonPollCoordinator",
              return_value=coordinator),
        patch("custom_components.nissan_connect.StatisticsCoordinator",
              return_value=coordinator),
    ):
        mock_session.return_value.fetch_vehicles.return_value = [
            MagicMock(vin="TEST-VIN")
        ]
        assert await async_setup_entry(hass, entry) is True

    migrated_device = device_registry.async_get(device.id)
    assert migrated_device.id == device.id, "updated, not replaced"
    assert migrated_device.identifiers == {(DOMAIN, "TEST-VIN")}
    assert migrated_device.name_by_user == "My Leaf"

    migrated_entity = entity_registry.async_get(entity.entity_id)
    assert migrated_entity is not None
    assert migrated_entity.device_id == device.id
    assert migrated_entity.entity_id == "sensor.my_leaf_battery_level"
