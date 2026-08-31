import logging
from datetime import timedelta
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from .kamereon import NCISession, NissanAuthError
from .coordinator import KamereonFetchCoordinator, KamereonPollCoordinator, StatisticsCoordinator
from .const import *

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass, config) -> bool:
    return True


async def async_update_listener(hass, entry):
    """Handle options flow credentials update."""
    config = entry.data
    account_id = config['email']

    sessions = {
        vehicle.session
        for vehicle in hass.data[DOMAIN][account_id][DATA_VEHICLES].values()
    }
    for session in sessions:
        await hass.async_add_executor_job(
            session.login,
            config.get("email"),
            config.get("password"),
        )

    # Update intervals for coordinators
    hass.data[DOMAIN][account_id][DATA_COORDINATOR_STATISTICS].update_interval = timedelta(minutes=config.get("interval_statistics", DEFAULT_INTERVAL_STATISTICS))
    hass.data[DOMAIN][account_id][DATA_COORDINATOR_FETCH].update_interval = timedelta(minutes=config.get("interval_fetch", DEFAULT_INTERVAL_FETCH))
    
    # Refresh fetch coordinator
    await hass.data[DOMAIN][account_id][DATA_COORDINATOR_FETCH].async_refresh()


async def async_setup_entry(hass, entry):
    """This is called from the config flow."""
    account_id = entry.data['email']

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(account_id, {})

    config = dict(entry.data)

    # Devices were once registered with a (domain, tenant, vin) identifier.
    # This rewrites them to (domain, vin) in place without affecting the device.
    device_registry = dr.async_get(hass)
    for device in dr.async_entries_for_config_entry(device_registry, entry.entry_id):
        legacy = {i for i in device.identifiers if i[0] == DOMAIN and len(i) == 3}
        if legacy:
            device_registry.async_update_device(
                device.id,
                new_identifiers={(DOMAIN, i[2]) for i in legacy}
                | (device.identifiers - legacy),
            )

    kamereon_session = NCISession(
        region=config["region"],
        unique_id=entry.unique_id
    )

    data = hass.data[DOMAIN][account_id] = {
        DATA_VEHICLES: {}
    }

    _LOGGER.info("Logging in to service")
    try:
        await hass.async_add_executor_job(kamereon_session.login,
                                          config.get("email"),
                                          config.get("password")
                                          )
    except NissanAuthError as error:
        raise ConfigEntryAuthFailed("Nissan authentication failed") from error
    except Exception as error:
        _LOGGER.warning("Login failed, will retry: %s", error)
        raise ConfigEntryNotReady("Could not reach the Nissan API") from error

    _LOGGER.debug("Finding vehicles")
    try:
        for vehicle in await hass.async_add_executor_job(kamereon_session.fetch_vehicles):
            await hass.async_add_executor_job(vehicle.fetch_all)
            if vehicle.vin not in data[DATA_VEHICLES]:
                data[DATA_VEHICLES][vehicle.vin] = vehicle
    except NissanAuthError as error:
        raise ConfigEntryAuthFailed("Nissan authentication failed") from error
    except Exception as error:
        _LOGGER.warning("Could not fetch vehicles, will retry: %s", error)
        raise ConfigEntryNotReady("Could not reach the Nissan API") from error

    coordinator = data[DATA_COORDINATOR_FETCH] = KamereonFetchCoordinator(hass, config)
    poll_coordinator = data[DATA_COORDINATOR_POLL] = KamereonPollCoordinator(hass, config)
    stats_coordinator = data[DATA_COORDINATOR_STATISTICS] = StatisticsCoordinator(
        hass, config)

    _LOGGER.debug("Initialising entities")
    await hass.config_entries.async_forward_entry_setups(entry, ENTITY_TYPES)

    # Init fetch and state coordinators
    await coordinator.async_config_entry_first_refresh()
    await stats_coordinator.async_config_entry_first_refresh()

    # Init poll coordinator and ensure it runs
    entry.async_on_unload(
            poll_coordinator.async_add_listener(
                lambda *args: None, None
            )
    )
    await poll_coordinator.async_config_entry_first_refresh()

    entry.async_on_unload(entry.add_update_listener(async_update_listener))

    return True


async def async_unload_entry(hass, entry):
    """Unload a config entry."""

    return await hass.config_entries.async_unload_platforms(entry, ENTITY_TYPES)


async def async_migrate_entry(hass, config_entry) -> bool:
    """Migrate old entry."""
    # Version number has gone backwards
    if CONFIG_VERSION < config_entry.version:
        _LOGGER.error(
            "Backwards migration not possible. Please update the integration.")
        return False

    # Version number has gone up
    if config_entry.version < CONFIG_VERSION:
        _LOGGER.debug("Migrating from version %s", config_entry.version)
        new_data = dict(config_entry.data)

        hass.config_entries.async_update_entry(
            config_entry,
            data=new_data,
            version=CONFIG_VERSION,
        )

        _LOGGER.debug("Migration to version %s successful",
                      config_entry.version)

    return True
