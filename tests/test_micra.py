"""New Micra EV (carGateway RVG): which endpoints fetch_all() must reach.

The payload shapes below are copied from a real 2025 Micra (EU), with made up
values. The service list is the one that car reports.
"""
import pytest

from custom_components.nissan_connect.kamereon import NCISession
from custom_components.nissan_connect.kamereon.kamereon_const import Feature

BFF_BASE_URL = "https://nci-bff-web-prod.apps.eu2.kamereon.io/bff-web/"
CAR_BASE_URL = (
    "https://alliance-platform-caradapter-prod.apps.eu2.kamereon.io/car-adapter/"
)
USER_URL = (
    "https://alliance-platform-usersadapter-prod.apps.eu2.kamereon.io/"
    "user-adapter/v1/users/current"
)

# Services listed by a real Micra: no 307, no 2042, no 2021, no 27, no 303
MICRA_SERVICES = [12, 97, 107, 202, 299, 308, 317, 319, 344, 366]

GATEWAY_NOT_IMPLEMENTED = {"errors": [{
    "status": "Not Implemented", "code": "501", "title": "Not supported Feature",
    "detail": "This feature is not technically supported by this gateway"}]}


def _micra(requests_mock, services=MICRA_SERVICES, model="MICRA"):
    """A Micra whose session is already authenticated, with every endpoint mocked
    the way the real car answers."""
    requests_mock.get(USER_URL, json={"userId": "test-user"})
    requests_mock.get(f"{BFF_BASE_URL}v5/users/test-user/cars", json={"data": [{
        "vin": "test-vin",
        "modelName": model,
        "modelYear": 2025,
        "carGateway": "RVG",
        "canGeneration": "C1A_HS EVO",
        "services": [{"id": s, "activationState": "ACTIVATED"} for s in services],
    }]})
    requests_mock.get(f"{BFF_BASE_URL}v3/cars/TEST-VIN/battery-status", json={"data": {
        "type": "Car", "id": "TEST-VIN", "attributes": {
            "lastUpdateTime": "2026-01-01T10:00:00.000Z", "batteryLevel": 57,
            "batteryTemperature": 0, "batteryAutonomy": 244, "plugStatus": 0,
            "chargingStatus": 0.0, "chargingRemainingTime": 1}}})
    requests_mock.get(f"{CAR_BASE_URL}v1/cars/TEST-VIN/location", json={"data": {
        "type": "Car", "id": "TEST-VIN", "attributes": {
            "gpsLatitude": 12.34, "gpsLongitude": 56.78,
            "lastUpdateTime": "2026-01-01T06:00:00.000Z"}}})
    requests_mock.get(f"{CAR_BASE_URL}v1/cars/TEST-VIN/hvac-status", json={"data": {
        "type": "Car", "id": "TEST-VIN", "attributes": {
            "internalTemperature": 21.0, "hvacStatus": "off",
            "lastUpdateTime": "2026-01-01T04:00:00.000Z"}}})
    requests_mock.get(f"{CAR_BASE_URL}v1/cars/TEST-VIN/cockpit",
                      json=GATEWAY_NOT_IMPLEMENTED, status_code=501)
    requests_mock.get(f"{CAR_BASE_URL}v2/cars/TEST-VIN/cockpit", json={"data": {
        "type": "Car", "id": "TEST-VIN", "attributes": {
            "fuelQuantity": 0.0, "totalMileage": 12345.0}}})
    # What the real car answers if the lock status is requested anyway
    requests_mock.get(f"{CAR_BASE_URL}v1/cars/TEST-VIN/lock-status", status_code=404,
                      json={"errors": [{"status": "Not Found", "code": "404"}]})

    session = NCISession(region="EU")
    session._install_kamereon_token({
        "access_token": "kamereon-access-token",
        "token_type": "Bearer",
        "expires_in": 1800,
    })
    return session.fetch_vehicles()[0]


def _requested(requests_mock):
    return [r.path for r in requests_mock.request_history
            if "/cars/test-vin/" in r.path]


def test_micra_features_are_parsed(requests_mock):
    vehicle = _micra(requests_mock)

    assert Feature.MY_CAR_FINDER in vehicle.features
    assert Feature.CLIMATE_ON_OFF in vehicle.features
    assert Feature.INTERIOR_TEMP_SETTINGS not in vehicle.features
    assert Feature.TEMPERATURE not in vehicle.features


def test_micra_fetch_all_reads_location(requests_mock):
    vehicle = _micra(requests_mock)

    vehicle.fetch_all()

    assert vehicle.location == (12.34, 56.78)
    assert vehicle.location_last_updated is not None


def test_micra_fetch_all_reads_hvac_status(requests_mock):
    """The Micra has CLIMATE_ON_OFF (366) but neither 307 nor 2042."""
    vehicle = _micra(requests_mock)

    vehicle.fetch_all()

    assert vehicle.internal_temperature == 21.0
    assert vehicle.hvac_status is False
    # The Micra does not report an exterior temperature
    assert vehicle.external_temperature is None


def test_micra_fetch_all_reads_odometer_from_v2_cockpit(requests_mock):
    vehicle = _micra(requests_mock)

    vehicle.fetch_all()

    assert vehicle.total_mileage == 12345.0


def test_micra_fetch_all_keeps_reading_the_battery(requests_mock):
    vehicle = _micra(requests_mock)

    vehicle.fetch_all()

    assert vehicle.battery_level == 57
    assert vehicle.range_hvac_on is not None


def test_micra_fetch_all_does_not_request_lock_status(requests_mock):
    """No lock service (2021) on this car, so the endpoint must not be requested."""
    vehicle = _micra(requests_mock)

    vehicle.fetch_all()

    assert not [p for p in _requested(requests_mock) if "lock-status" in p]


def test_micra_without_car_finder_does_not_request_location(requests_mock):
    services = [s for s in MICRA_SERVICES if s != 12]
    vehicle = _micra(requests_mock, services=services)

    vehicle.fetch_all()

    assert vehicle.location is None
    assert not [p for p in _requested(requests_mock) if p.endswith("/location")]


def test_model_name_casing_does_not_matter(requests_mock):
    """The API sends MICRA in capitals, but a mixed case name must behave the same."""
    vehicle = _micra(requests_mock, model="Micra")

    vehicle.fetch_all()

    assert vehicle.location == (12.34, 56.78)
    assert vehicle.internal_temperature == 21.0


@pytest.mark.parametrize("service", ["INTERIOR_TEMP_SETTINGS", "TEMPERATURE"])
def test_hvac_status_is_still_read_with_the_services_it_used_to_require(requests_mock, service):
    """Cars that have 307 or 2042 must keep working, with or without 366."""
    services = [s for s in MICRA_SERVICES if s != 366] + [Feature[service].value]
    vehicle = _micra(requests_mock, services=[int(s) for s in services])

    vehicle.fetch_hvac_status()

    assert vehicle.internal_temperature == 21.0


def test_hvac_status_is_read_with_climate_on_off_alone(requests_mock):
    """366 only, like the Micra: neither 307 nor 2042."""
    vehicle = _micra(requests_mock)
    assert Feature.INTERIOR_TEMP_SETTINGS not in vehicle.features
    assert Feature.TEMPERATURE not in vehicle.features

    vehicle.fetch_hvac_status()

    assert vehicle.internal_temperature == 21.0


def test_hvac_status_is_not_requested_without_any_climate_service(requests_mock):
    services = [s for s in MICRA_SERVICES if s != 366]
    vehicle = _micra(requests_mock, services=services)

    vehicle.fetch_hvac_status()

    assert vehicle.internal_temperature is None
    assert not [p for p in _requested(requests_mock) if "hvac-status" in p]
