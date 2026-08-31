import pytest
from unittest.mock import AsyncMock, MagicMock

from custom_components.nissan_connect.const import DOMAIN, DATA_VEHICLES, DATA_COORDINATOR_FETCH
from custom_components.nissan_connect.kamereon.kamereon_const import Feature, LockStatus

from custom_components.nissan_connect.lock import (
    async_setup_entry,
    KamereonLock,
)


@pytest.fixture
def mock_hass():
    hass = MagicMock()
    hass.data = {
        DOMAIN: {
            'test_account': {
                DATA_VEHICLES: {
                    'vehicle_1': MagicMock(features=[Feature.APP_DOOR_LOCKING])
                },
                DATA_COORDINATOR_FETCH: MagicMock(),
            }
        }
    }
    return hass


@pytest.fixture
def mock_async_add_entities():
    return AsyncMock()


@pytest.mark.asyncio
async def test_async_setup_entry_creates_lock_when_configured(mock_hass, mock_async_add_entities):
    mock_config = MagicMock(data={
        'email': 'test_account', 'srp_pincode': '1234', 'remote_lock_enabled': True
    })

    await async_setup_entry(mock_hass, mock_config, mock_async_add_entities)

    assert mock_async_add_entities.call_count == 1
    entities = mock_async_add_entities.call_args[0][0]
    assert len(entities) == 1
    assert isinstance(entities[0], KamereonLock)


@pytest.mark.asyncio
async def test_async_setup_entry_skips_without_feature(mock_hass, mock_async_add_entities):
    mock_hass.data[DOMAIN]['test_account'][DATA_VEHICLES]['vehicle_1'] = MagicMock(features=[])
    mock_config = MagicMock(data={
        'email': 'test_account', 'srp_pincode': '1234', 'remote_lock_enabled': True
    })

    await async_setup_entry(mock_hass, mock_config, mock_async_add_entities)

    entities = mock_async_add_entities.call_args[0][0]
    assert len(entities) == 0


@pytest.mark.asyncio
async def test_async_setup_entry_skips_without_pincode(mock_hass, mock_async_add_entities):
    # Feature is supported, but remote lock/unlock hasn't been set up (no PIN
    # configured via the options flow) - the entity must not be created.
    mock_config = MagicMock(data={'email': 'test_account', 'remote_lock_enabled': True})

    await async_setup_entry(mock_hass, mock_config, mock_async_add_entities)

    entities = mock_async_add_entities.call_args[0][0]
    assert len(entities) == 0


@pytest.mark.asyncio
async def test_async_setup_entry_skips_when_disabled_again(mock_hass, mock_async_add_entities):
    # device_id/srp_pincode are deliberately kept around after the user
    # unticks "Enable remote lock/unlock" - the entity must still disappear.
    mock_config = MagicMock(data={
        'email': 'test_account', 'srp_pincode': '1234', 'remote_lock_enabled': False
    })

    await async_setup_entry(mock_hass, mock_config, mock_async_add_entities)

    entities = mock_async_add_entities.call_args[0][0]
    assert len(entities) == 0


def test_is_locked():
    coordinator = MagicMock()
    hass = MagicMock()

    vehicle = MagicMock(lock_status=LockStatus.LOCKED)
    lock = KamereonLock(coordinator, vehicle, hass, '1234')
    assert lock.is_locked is True

    vehicle.lock_status = LockStatus.UNLOCKED
    assert lock.is_locked is False

    vehicle.lock_status = None
    assert lock.is_locked is None


@pytest.mark.asyncio
async def test_async_lock_calls_vehicle_with_pincode():
    coordinator = MagicMock()
    vehicle = MagicMock()
    hass = AsyncMock()
    hass.async_create_task = MagicMock()

    lock = KamereonLock(coordinator, vehicle, hass, 'my-pin')

    await lock.async_lock()

    hass.async_add_executor_job.assert_called_once_with(vehicle.lock, 'my-pin')
    hass.async_create_task.assert_called_once()


@pytest.mark.asyncio
async def test_async_unlock_calls_vehicle_with_pincode():
    coordinator = MagicMock()
    vehicle = MagicMock()
    hass = AsyncMock()
    hass.async_create_task = MagicMock()

    lock = KamereonLock(coordinator, vehicle, hass, 'my-pin')

    await lock.async_unlock()

    hass.async_add_executor_job.assert_called_once_with(vehicle.unlock, 'my-pin')
    hass.async_create_task.assert_called_once()
