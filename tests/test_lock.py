"""Tests for Nissan remote lock entities."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.exceptions import HomeAssistantError

from custom_components.nissan_connect.const import (
    CONF_REMOTE_LOCK,
    CONF_REMOTE_LOCK_DEVICE_ID,
    CONF_REMOTE_LOCK_STATUS,
    DATA_COORDINATOR_FETCH,
    DATA_VEHICLES,
    DOMAIN,
    REMOTE_LOCK_STATUS_ENABLED,
)
from custom_components.nissan_connect.kamereon import (
    LockStatus,
    RemoteLockRejected,
)
from custom_components.nissan_connect.lock import NissanLock, async_setup_entry


@pytest.mark.parametrize(
    "supports_remote_lock_setup, status, expected_count",
    [
        (True, REMOTE_LOCK_STATUS_ENABLED, 1),
        (False, REMOTE_LOCK_STATUS_ENABLED, 0),
        (True, "configured", 0),
        (True, None, 0),
    ],
)
async def test_remote_lock_entity_capability_and_configuration_gate(
        supports_remote_lock_setup, status, expected_count):
    vehicle = MagicMock(
        supports_remote_lock_setup=supports_remote_lock_setup,
    )
    coordinator = MagicMock()
    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            "test@example.com": {
                DATA_VEHICLES: {"TEST-VIN": vehicle},
                DATA_COORDINATOR_FETCH: coordinator,
            }
        }
    }
    remote_lock = {}
    if status is not None:
        remote_lock["TEST-VIN"] = {
            CONF_REMOTE_LOCK_DEVICE_ID: "0123456789abcdef",
            CONF_REMOTE_LOCK_STATUS: status,
        }
    config = MagicMock(data={
        "email": "test@example.com",
        CONF_REMOTE_LOCK: remote_lock,
    })
    async_add_entities = MagicMock()

    await async_setup_entry(hass, config, async_add_entities)

    entities = async_add_entities.call_args.args[0]
    assert len(entities) == expected_count
    if entities:
        assert isinstance(entities[0], NissanLock)


def test_remote_lock_state_uses_cached_vehicle_status():
    vehicle = MagicMock(lock_status=None)
    entity = NissanLock(MagicMock(), vehicle, MagicMock(), "device-id")

    assert entity.is_locked is None
    vehicle.lock_status = LockStatus.LOCKED
    assert entity.is_locked is True
    vehicle.lock_status = LockStatus.UNLOCKED
    assert entity.is_locked is False


async def test_remote_unlock_runs_in_executor_and_refreshes_status():
    vehicle = MagicMock(lock_status=LockStatus.LOCKED)
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock()
    coordinator = MagicMock()
    coordinator.async_refresh = AsyncMock()
    entity = NissanLock(coordinator, vehicle, hass, "0123456789abcdef")
    entity.async_write_ha_state = MagicMock()

    await entity.async_unlock(code="1234")

    hass.async_add_executor_job.assert_awaited_once_with(
        vehicle.unlock,
        "1234",
        "0123456789abcdef",
    )
    coordinator.async_refresh.assert_awaited_once_with()
    assert entity.is_unlocking is False
    assert entity.async_write_ha_state.call_count == 2


async def test_remote_lock_runs_in_executor_and_refreshes_status():
    vehicle = MagicMock(lock_status=LockStatus.UNLOCKED)
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock()
    coordinator = MagicMock()
    coordinator.async_refresh = AsyncMock()
    entity = NissanLock(coordinator, vehicle, hass, "0123456789abcdef")
    entity.async_write_ha_state = MagicMock()

    await entity.async_lock(code="1234")

    hass.async_add_executor_job.assert_awaited_once_with(
        vehicle.lock,
        "1234",
        "0123456789abcdef",
    )
    coordinator.async_refresh.assert_awaited_once_with()
    assert entity.is_locking is False
    assert entity.async_write_ha_state.call_count == 2


async def test_remote_lock_failure_does_not_refresh_status():
    vehicle = MagicMock(lock_status=LockStatus.UNLOCKED)
    hass = MagicMock()
    hass.async_add_executor_job = AsyncMock(
        side_effect=RemoteLockRejected("remote lock ended with REJECTED"))
    coordinator = MagicMock()
    coordinator.async_refresh = AsyncMock()
    entity = NissanLock(coordinator, vehicle, hass, "0123456789abcdef")
    entity.async_write_ha_state = MagicMock()

    with pytest.raises(HomeAssistantError, match="REJECTED"):
        await entity.async_lock(code="1234")

    coordinator.async_refresh.assert_not_awaited()
    assert entity.is_locking is False


async def test_remote_lock_requires_transient_pin():
    entity = NissanLock(MagicMock(), MagicMock(), MagicMock(), "device-id")

    with pytest.raises(HomeAssistantError, match="four-digit"):
        await entity.async_lock()

    assert entity.code_format == r"^\d{4}$"