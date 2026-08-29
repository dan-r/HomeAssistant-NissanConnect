from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

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
            "country_code": "DE",
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
            "country_code": "DE",
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