from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from homeassistant import config_entries
from homeassistant.exceptions import ConfigEntryAuthFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

# Importing the config flow registers the handler, which is what
# async_start_reauth_if_available checks before starting a reauth flow.
from custom_components.nissan_connect import config_flow  # noqa: F401
from custom_components.nissan_connect.const import (
    DATA_COORDINATOR_FETCH,
    DATA_COORDINATOR_POLL,
    DATA_VEHICLES,
    DOMAIN,
)
from custom_components.nissan_connect.coordinator import (
    KamereonFetchCoordinator,
    KamereonPollCoordinator,
)
from custom_components.nissan_connect.kamereon import (
    ChargingStatus,
    Feature,
    NissanAuthError,
    PluggedStatus,
)


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


@pytest.fixture
def poll_coordinator(hass):
    """A poll coordinator with one vehicle, built the way __init__.py builds it."""

    def _build(config):
        vehicle = MagicMock()
        vehicle.features = []
        vehicle.hvac_status = False
        hass.data[DOMAIN] = {
            "test@example.com": {
                DATA_VEHICLES: {"test-vin": vehicle},
                DATA_COORDINATOR_FETCH: MagicMock(),
            }
        }
        coordinator = KamereonPollCoordinator(
            hass, {"email": "test@example.com", **config})
        # __init__.py keeps a no-op listener so the coordinator stays scheduled.
        coordinator.async_add_listener(lambda *args: None, None)
        return coordinator

    return _build


def _seconds_until_next_refresh(hass, coordinator):
    """When the coordinator's timer is due, relative to now."""
    handles = [
        handle for handle in hass.loop._scheduled
        if not handle._cancelled
        and "handle_refresh_interval" in str(handle._callback)
    ]
    if not handles:
        return None
    return handles[-1].when() - hass.loop.time()


async def test_polling_disabled_schedules_nothing(hass, poll_coordinator):
    """An interval of 0 means polling is off, not 'poll continuously'."""
    coordinator = poll_coordinator({"interval": 0})

    coordinator.set_next_interval()

    assert coordinator.update_interval == timedelta(0)
    assert _seconds_until_next_refresh(hass, coordinator) is None


async def test_negative_interval_is_clamped(hass, poll_coordinator):
    """A negative interval would be permanently overdue and refresh in a loop."""
    coordinator = poll_coordinator({"interval": -1, "interval_charging": -5})

    coordinator.set_next_interval()

    assert coordinator.update_interval == timedelta(0)
    assert _seconds_until_next_refresh(hass, coordinator) is None


async def test_long_interval_is_not_rearmed_on_every_call(hass, poll_coordinator):
    """timedelta.seconds drops whole days, so >=24h intervals never settled."""
    coordinator = poll_coordinator({"interval": 1440})

    coordinator.set_next_interval()
    due_first = _seconds_until_next_refresh(hass, coordinator)
    unsub_first = coordinator._unsub_refresh

    # The fetch coordinator calls this on every update; it must be a no-op now
    # that the interval has settled, otherwise the timer restarts from scratch
    # and a 24h poll never actually fires.
    coordinator.set_next_interval()

    assert coordinator.update_interval == timedelta(minutes=1440)
    assert due_first == pytest.approx(24 * 60 * 60, abs=2)
    assert coordinator._unsub_refresh is unsub_first

    coordinator._async_unsub_refresh()


async def test_interval_change_still_rearms_the_timer(hass, poll_coordinator):
    """Switching to the charging interval must take effect immediately."""
    coordinator = poll_coordinator(
        {"interval": 60, "interval_charging": 15})

    coordinator.set_next_interval()
    assert coordinator.update_interval == timedelta(minutes=60)

    vehicle = coordinator._vehicles["test-vin"]
    vehicle.features = [Feature.BATTERY_STATUS]
    vehicle.plugged_in = PluggedStatus.PLUGGED
    vehicle.charging = ChargingStatus.CHARGING

    coordinator.set_next_interval()

    assert coordinator.update_interval == timedelta(minutes=15)
    assert _seconds_until_next_refresh(hass, coordinator) == pytest.approx(
        15 * 60, abs=2)

    coordinator._async_unsub_refresh()
