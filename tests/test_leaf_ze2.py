"""Battery and entity discovery for the EU ZE2-1 and its older ZE1 sibling."""
from unittest.mock import Mock

import pytest

from custom_components.nissan_connect import binary_sensor, sensor
from custom_components.nissan_connect.kamereon import NCISession


@pytest.fixture
def leaf_session(requests_mock):
    session = NCISession(region="EU")
    session._install_kamereon_token({
        "access_token": "test", "token_type": "Bearer", "expires_in": 1800,
    })
    requests_mock.get(session.settings["user_adapter_base_url"] + "v1/users/current",
                      json={"userId": "owner"})
    requests_mock.get(session.settings["user_base_url"] + "v5/users/owner/cars", json={"data": [
        {"vin": "NEW", "modelName": "Leaf", "modelCode": "ZE2-1", "iceEvFlag": "EV",
         "canGeneration": "C1A_HS EVO", "services": [{"id": 420, "activationState": "ACTIVATED"}]},
        {"vin": "OLD", "modelName": "Leaf", "modelCode": "ZE1", "iceEvFlag": "EV",
         "canGeneration": "GEN3", "services": [{"id": 319, "activationState": "ACTIVATED"}]},
    ]})
    return session


@pytest.mark.parametrize("level,km,status", [(69, 364, 0), (0, 0, 1), (69, 364, None)])
async def test_leaf_battery_entities(requests_mock, leaf_session, level, km, status):
    new, old = leaf_session.fetch_vehicles()
    bff = leaf_session.settings["user_base_url"]
    adapter = leaf_session.settings["car_adapter_base_url"]
    attrs = {"batteryLevel": level, "batteryAutonomy": km, "chargingRemainingTime": 0}
    if status is not None:
        attrs.update(chargingStatus=status, plugStatus=status)
    requests_mock.get(bff + "v3/cars/NEW/battery-status?canGen=C1A_HS%20EVO",
                      complete_qs=True, json={"data": {"attributes": attrs}})
    requests_mock.get(adapter + "v1/cars/OLD/battery-status",
                      json={"data": {"attributes": {"batteryLevel": 81, "rangeHvacOff": 200}}})
    requests_mock.get(adapter + "v1/cars/NEW/cockpit", json={"data": {"attributes": {
        "fuelAutonomy": 0, "fuelQuantity": 0.0, "totalMileage": 88}}})
    new.fetch_battery_status()
    old.fetch_battery_status()
    new.fetch_cockpit()
    assert old.battery_level == 81
    assert old.range_hvac_off == 200

    hass = Mock(data={"nissan_connect": {"owner": {
        "vehicles": {"NEW": new}, "coordinator_fetch": Mock(), "coordinator_statistics": Mock(),
    }}})
    entities = {}
    for platform in (sensor, binary_sensor):
        add_entities = Mock()
        await platform.async_setup_entry(hass, Mock(data={"email": "owner"}), add_entities)
        entities.update({e.translation_key: e for e in add_entities.call_args.args[0]})

    assert entities["battery_level"].state == level
    assert entities["range_ac_on"].native_value == km
    assert entities["charge_time_adaptive"].native_value == 0
    assert "odometer" in entities
    assert not {"fuel_quantity", "fuel_level", "fuel_range"} & entities.keys()
    if status is None:
        assert not {"charging", "plugged"} & entities.keys()
    else:
        assert entities["charging"].is_on is bool(status)
        assert entities["plugged"].is_on is bool(status)
        # A later partial response must not leave stale or falsely active states.
        requests_mock.get(bff + "v3/cars/NEW/battery-status",
                          json={"data": {"attributes": {"batteryLevel": level}}})
        new.fetch_battery_status()
        assert entities["charging"].is_on is None
        assert entities["plugged"].is_on is None
