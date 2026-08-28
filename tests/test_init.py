from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

from custom_components.nissan_connect import async_migrate_entry, async_update_listener
from custom_components.nissan_connect.const import (
    CONFIG_VERSION,
    DATA_COORDINATOR_FETCH,
    DATA_COORDINATOR_STATISTICS,
    DATA_VEHICLES,
    DOMAIN,
)
from pytest_homeassistant_custom_component.common import MockConfigEntry


async def test_update_listener_logs_in_shared_session_once():
    session = MagicMock()
    fetch_coordinator = MagicMock()
    fetch_coordinator.async_refresh = AsyncMock()
    statistics_coordinator = MagicMock()
    hass = MagicMock()
    hass.config.country = "DE"
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
        "DE",
    )
    assert fetch_coordinator.update_interval == timedelta(minutes=10)
    assert statistics_coordinator.update_interval == timedelta(minutes=60)
    fetch_coordinator.async_refresh.assert_awaited_once_with()


async def test_migrate_entry_adds_home_assistant_country(hass):
    hass.config.country = "DE"
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        data={
            "email": "test@example.com",
            "password": "test-password",
            "region": "EU",
        },
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == CONFIG_VERSION
    assert entry.data["country_code"] == "DE"