"""Diagnostics support for NissanConnect."""
import datetime
import enum

from homeassistant.components.diagnostics import async_redact_data

from .const import DOMAIN, DATA_VEHICLES, DATA_COORDINATOR_FETCH, DATA_COORDINATOR_POLL, DATA_COORDINATOR_STATISTICS

# Credentials, and anything that identifies the owner, the car or where it is
TO_REDACT = {
    "email",
    "password",
    "vin",
    "user_id",
    "nickname",
    "registration_number",
    "location",
    "picture_url",
}

COORDINATORS = {
    "fetch": DATA_COORDINATOR_FETCH,
    "poll": DATA_COORDINATOR_POLL,
    "statistics": DATA_COORDINATOR_STATISTICS,
}


def _serialize(value):
    """Turn the Kamereon enums and dates into plain JSON values."""
    if isinstance(value, enum.Enum):
        return value.name
    if isinstance(value, (datetime.datetime, datetime.date)):
        return value.isoformat()
    if isinstance(value, dict):
        return {_serialize(k): _serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_serialize(v) for v in value]
    return value


def _vehicle_diagnostics(vehicle):
    data = {
        key: _serialize(value)
        for key, value in vars(vehicle).items()
        if not key.startswith("_")
    }
    # Which cockpit API the car's gateway serves matters when debugging
    data["cockpit_version"] = _serialize(getattr(vehicle, "_cockpit_version", None))
    data["last_updated"] = _serialize(vehicle.last_updated)
    return data


async def async_get_config_entry_diagnostics(hass, entry):
    """Return diagnostics for a config entry."""
    data = hass.data.get(DOMAIN, {}).get(entry.data["email"], {})

    coordinators = {}
    for name, key in COORDINATORS.items():
        coordinator = data.get(key)
        if coordinator is None:
            continue
        coordinators[name] = {
            "last_update_success": coordinator.last_update_success,
            "update_interval_minutes": (
                coordinator.update_interval.total_seconds() / 60
                if coordinator.update_interval is not None else None
            ),
        }

    return {
        "entry": async_redact_data(dict(entry.data), TO_REDACT),
        "coordinators": coordinators,
        "vehicles": [
            async_redact_data(_vehicle_diagnostics(vehicle), TO_REDACT)
            for vehicle in data.get(DATA_VEHICLES, {}).values()
        ],
    }
