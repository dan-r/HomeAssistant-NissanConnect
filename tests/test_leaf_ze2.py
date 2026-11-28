"""Battery and entity discovery for the EU third-generation Leaf and its ZE1 sibling."""
from unittest.mock import Mock

import pytest
from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.const import EntityCategory, UnitOfPressure

from custom_components.nissan_connect import binary_sensor, device_tracker, sensor
from custom_components.nissan_connect.kamereon import NCISession


async def test_repeat_timers_and_shared_settings(requests_mock, leaf_session):
    new, old = leaf_session.fetch_vehicles()
    endpoint = leaf_session.settings["car_adapter_base_url"] + "v1/cars/NEW/hvac-settings"
    days = ("monday", "tuesday", "wednesday", "thursday", "friday")
    settings = {
        "globalTargetTemperature": 22.0, "frontLeftSeatControl": 1, "frontRightSeatControl": 1,
        "steeringHeaterControl": 1, "frontDefrostMode": 1, "rearDefrostMode": 0,
        "schedules": [
            {"id": slot, "activated": slot <= 2, **dict.fromkeys(days, {"readyAtTime": time})}
            for slot, time in enumerate(("T07:00Z", "T15:30Z", "T00:00Z", "T00:00Z", "T00:00Z"), 1)
        ],
    }
    endpoint_mock = requests_mock.get(endpoint, json={"data": {"attributes": settings}})
    old.fetch_climate_timers()
    assert not endpoint_mock.called
    new.fetch_climate_timers()
    assert endpoint_mock.call_count == 1
    hass = Mock(data={"nissan_connect": {"owner": {
        "vehicles": {"NEW": new, "OLD": old}, "coordinator_fetch": Mock(), "coordinator_statistics": Mock(),
    }}})
    entities = {}
    timers = {}
    for platform in (sensor, binary_sensor):
        add = Mock()
        await platform.async_setup_entry(hass, Mock(data={"email": "owner"}), add)
        for entity in add.call_args.args[0]:
            if entity.vehicle is old:
                assert not entity.translation_key.startswith(("climate_timer", "scheduled_", "repeat_climate_"))
            elif entity.translation_key == "climate_timer":
                slot = int(entity.translation_placeholders["slot"])
                timers[slot] = entity
                assert entity.unique_id == f"Leaf_climate_timer_{slot}"
            else:
                entities[entity.translation_key] = entity
    assert [timers[i].is_on for i in range(1, 6)] == [True, True, False, False, False]
    assert timers[2].extra_state_attributes == dict.fromkeys(days, "15:30Z")
    assert entities["repeat_climate_target"].native_value == 22
    assert entities["scheduled_front_left_seat_heat"].is_on is True
    assert entities["scheduled_front_right_seat_heat"].is_on is True
    assert entities["scheduled_rear_defrost"].is_on is False

    requests_mock.get(endpoint, json={"data": {"attributes": {
        "frontLeftSeatControl": -1, "schedules": [{"id": 1, "activated": False}],
    }}})
    new.fetch_climate_timers()
    assert timers[1].is_on is False
    assert timers[2].is_on is None
    assert timers[2].extra_state_attributes == {}
    assert entities["scheduled_front_left_seat_heat"].is_on is None
    assert entities["repeat_climate_target"].native_value is None


@pytest.fixture(params=("ZE2", "ZE2-1"))
def leaf_session(requests_mock, request):
    session = NCISession(region="EU")
    session._install_kamereon_token({
        "access_token": "test", "token_type": "Bearer", "expires_in": 1800,
    })
    requests_mock.get(session.settings["user_adapter_base_url"] + "v1/users/current",
                      json={"userId": "owner"})
    requests_mock.get(session.settings["user_base_url"] + "v5/users/owner/cars", json={"data": [
        {"vin": "NEW", "modelName": "Leaf", "modelCode": request.param, "iceEvFlag": "EV",
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


async def test_ze2_reads_optional_status_without_legacy_services(requests_mock, leaf_session):
    new, old = leaf_session.fetch_vehicles()
    base = leaf_session.settings["car_adapter_base_url"] + "v1/cars/NEW/"
    timestamp = {"lastUpdateTime": "2026-01-01T12:00:00Z"}
    for resource, fields in {
        "location": {"gpsLatitude": 12.3, "gpsLongitude": 45.6},
        "hvac-status": {"internalTemperature": 25, "hvacStatus": "off",
                        "steeringHeaterControl": 0, "thirdLeftSeatControl": -1},
        "lock-status": {"lockStatus": "locked", "doorStatusFrontLeft": "open",
                        "trunkLockStatus": "locked", "hazardLampStatus": "off",
                        "windowStatusFrontRight": "closed", "windowStatusRearLeft": "invalid"},
        "health-status": {"malfunctionIndicatorLamps": {
            "absWarning": 0, "airbagWarning": 1, "powerLimitationAlert": 3,
            "evAlertCrbsFailureDisplay": 7, "batteryLowWarning": 0}},
        "pressure": {"flPressure": 2760, "flStatus": 0, "rrStatus": 2},
    }.items():
        requests_mock.get(base + resource, json={"data": {"attributes": fields | timestamp}})
    for vehicle in (new, old):
        vehicle.fetch_location()
        vehicle.fetch_hvac_status()
        vehicle.fetch_lock_status()
        vehicle.fetch_health_status()
        vehicle.fetch_tyre_pressure()
    assert old.location is None
    assert old.internal_temperature is None
    hass = Mock(data={"nissan_connect": {"owner": {
        "vehicles": {"NEW": new}, "coordinator_fetch": Mock(), "coordinator_statistics": Mock(),
    }}})
    entities = {}
    for platform in (sensor, binary_sensor, device_tracker):
        add = Mock()
        await platform.async_setup_entry(hass, Mock(data={"email": "owner"}), add)
        entities.update({e.translation_key: e for e in add.call_args.args[0]})
    assert entities["location"].latitude == 12.3
    assert entities["location"].longitude == 45.6
    assert entities["internal_temperature"].native_value is None
    assert entities["climate_active"].is_on is False
    assert entities["climate_active"].extra_state_attributes == {"steeringHeaterControl": 0}
    for hvac_status, temperature, expected in (
        ("on", 1, 1), ("on", 25, 25), ("off", 25, None), ("off", 0, 0)
    ):
        requests_mock.get(base + "hvac-status", json={"data": {"attributes": {
            "hvacStatus": hvac_status, "internalTemperature": temperature,
        }}})
        new.fetch_hvac_status()
        assert entities["internal_temperature"].native_value == expected
    assert entities["doors_locked"].is_on is False  # HA's lock binary sensor is on when unlocked
    assert entities["front_left_door"].is_on is True
    assert entities["any_door"].is_on is True
    assert entities["any_window"].is_on is None
    assert entities["hazard_lamps"].is_on is False
    assert entities["boot_lock"].is_on is False
    assert entities["abs_warning"].is_on is False
    assert entities["airbag_warning"].is_on is True
    assert entities["power_limitation_warning"].is_on is None
    assert entities["power_limitation_warning"].extra_state_attributes == {"raw_code": 3}
    assert entities["battery_low_warning_raw"].native_value == 0
    assert entities["ev_alert_crbs_failure_display_raw"].native_value == 7
    pressure = entities["front_left_tyre_pressure_raw"]
    assert pressure.native_value == 2.76
    assert pressure.native_unit_of_measurement == UnitOfPressure.BAR
    assert pressure.suggested_unit_of_measurement == UnitOfPressure.BAR
    assert pressure.device_class == SensorDeviceClass.PRESSURE
    assert pressure.state_class == SensorStateClass.MEASUREMENT
    for key in ("front_left_tyre_pressure_raw", "rear_right_tyre_status_raw", "abs_warning", "battery_low_warning_raw"):
        assert entities[key].entity_category == EntityCategory.DIAGNOSTIC
    assert entities["any_door"].entity_category is None
    for invalid in ("invalid", -1, False, None):
        new.tyre_readings["flPressure"] = invalid
        assert pressure.native_value is None
    new.tyre_readings["flPressure"] = 0
    assert pressure.native_value == 0
    assert entities["rear_right_tyre_status_raw"].native_value == 2
    assert entities["rear_right_tyre_pressure_raw"].native_value is None
    assert entities["front_right_window"].is_on is False
    assert "rear_left_window" not in entities
    requests_mock.get(base + "lock-status", json={"data": {"attributes": timestamp}})
    new.fetch_lock_status()
    assert entities["doors_locked"].is_on is None
    assert entities["front_left_door"].is_on is None
    assert entities["boot_lock"].is_on is None
    requests_mock.get(base + "health-status", json={"errors": []}, status_code=503)
    from requests.exceptions import HTTPError
    with pytest.raises(HTTPError):
        new.fetch_health_status()
    assert entities["abs_warning"].is_on is None
    assert entities["ev_alert_crbs_failure_display_raw"].native_value is None
    assert all(r.method == "GET" for r in requests_mock.request_history)
