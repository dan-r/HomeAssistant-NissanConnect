from unittest.mock import MagicMock

import pytest
from homeassistant import config_entries
from homeassistant.exceptions import ConfigEntryAuthFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Importing the config flow registers the handler, which is what
# async_start_reauth_if_available checks before starting a reauth flow.
from custom_components.nissan_connect import config_flow  # noqa: F401
from custom_components.nissan_connect.const import (
    DATA_COORDINATOR_POLL,
    DATA_VEHICLES,
    DOMAIN,
)
from custom_components.nissan_connect.coordinator import KamereonFetchCoordinator
from custom_components.nissan_connect.kamereon import NissanAuthError


@pytest.fixture
def coordinator(hass):
    """A fetch coordinator with one vehicle whose fetch_all we control."""
    vehicle = MagicMock()
    hass.data[DOMAIN] = {
        "test@example.com": {
            DATA_VEHICLES: {"test-vin": vehicle},
            DATA_COORDINATOR_POLL: MagicMock(),
        }
    }
    return KamereonFetchCoordinator(hass, {"email": "test@example.com"}), vehicle


async def test_auth_failure_triggers_reauth(coordinator):
    """Stale credentials must reach Home Assistant, not be logged and dropped."""
    fetch_coordinator, vehicle = coordinator
    vehicle.fetch_all.side_effect = NissanAuthError("Invalid credentials")

    with pytest.raises(ConfigEntryAuthFailed):
        await fetch_coordinator._async_update_data()


async def test_transient_failure_is_swallowed(coordinator, caplog):
    """Network errors keep the old behaviour: log and carry on."""
    fetch_coordinator, vehicle = coordinator
    vehicle.fetch_all.side_effect = RuntimeError("Connection reset")

    assert await fetch_coordinator._async_update_data() is False
    assert "Error communicating with API" in caplog.text


async def test_auth_failure_actually_starts_a_reauth_flow(hass):
    """End-to-end: the coordinator must reach HA's reauth machinery.

    DataUpdateCoordinator only calls async_start_reauth_if_available when it
    has a config_entry, which it picks up from a ContextVar set during setup.
    """
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="test@example.com",
        data={
            "email": "test@example.com",
            "password": "stale-password",
            "region": "EU",
        },
    )
    entry.add_to_hass(hass)

    vehicle = MagicMock()
    vehicle.fetch_all.side_effect = NissanAuthError("Invalid credentials")
    hass.data[DOMAIN] = {
        "test@example.com": {
            DATA_VEHICLES: {"test-vin": vehicle},
            DATA_COORDINATOR_POLL: MagicMock(),
        }
    }

    # Coordinators are built inside async_setup_entry, where HA has set this.
    token = config_entries.current_entry.set(entry)
    try:
        fetch_coordinator = KamereonFetchCoordinator(
            hass, {"email": "test@example.com"})
    finally:
        config_entries.current_entry.reset(token)

    assert fetch_coordinator.config_entry is entry

    await fetch_coordinator.async_refresh()
    await hass.async_block_till_done()

    reauth_flows = [
        flow for flow in hass.config_entries.flow.async_progress()
        if flow["context"].get("source") == config_entries.SOURCE_REAUTH
    ]
    assert len(reauth_flows) == 1
    assert reauth_flows[0]["step_id"] == "reauth_confirm"
