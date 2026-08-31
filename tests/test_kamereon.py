import base64
import hashlib
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import pytest
import requests

from custom_components.nissan_connect.kamereon import NCISession, NissanAuthError, SRP
from custom_components.nissan_connect.kamereon.kamereon_const import Feature


AUTH_BASE_URL = "https://login.mynissan-account.com/"
BFF_BASE_URL = "https://nci-bff-web-prod.apps.eu2.kamereon.io/bff-web/"
REDIRECT_URI = "com://wso2.service.nci"


def login_form():
    return """
        <html><body>
        <form action="../commonauth" method="post" id="loginForm">
            <input type="hidden" name="regionCode" value="NG">
            <input type="hidden" name="username" value="">
            <input type="hidden" name="sessionDataKey" value="test-session">
            <input type="text" name="userName">
            <input type="password" name="password">
        </form>
        </body></html>
    """


def register_successful_login(requests_mock):
    requests_mock.get(
        f"{AUTH_BASE_URL}oauth2/authorize",
        status_code=302,
        headers={
            "Location": (
                f"{AUTH_BASE_URL}authenticationendpoint/login.do"
                "?sessionDataKey=test-session"
            )
        },
    )
    requests_mock.get(
        f"{AUTH_BASE_URL}authenticationendpoint/login.do",
        text=login_form(),
    )
    requests_mock.post(
        f"{AUTH_BASE_URL}commonauth",
        status_code=302,
        headers={"Location": f"{REDIRECT_URI}?code=test-code&state=test-state"},
    )
    requests_mock.post(
        f"{AUTH_BASE_URL}oauth2/token",
        json={
            "access_token": "wso2-access-token",
            "refresh_token": "wso2-refresh-token",
            "id_token": "wso2-id-token",
            "token_type": "Bearer",
            "expires_in": 3600,
        },
    )
    requests_mock.post(
        f"{BFF_BASE_URL}v1/oauth2/access_token",
        json={
            "access_token": "kamereon-access-token",
            "refresh_token": "kamereon-refresh-token",
            "id_token": "kamereon-id-token",
            "token_type": "Bearer",
            "expires_in": 1800,
        },
    )


def test_login_exchanges_oneid_for_kamereon_token(requests_mock):
    register_successful_login(requests_mock)
    session = NCISession(region="EU")

    with patch(
        "custom_components.nissan_connect.kamereon.kamereon.secrets.token_urlsafe",
        side_effect=["v" * 64, "test-state"],
    ):
        session.login("test@example.com", "test-password")

    authorize_request = requests_mock.request_history[0]
    authorize_query = parse_qs(urlparse(authorize_request.url).query)
    expected_challenge = base64.urlsafe_b64encode(
        hashlib.sha256(("v" * 64).encode("ascii")).digest()
    ).rstrip(b"=").decode("ascii")
    assert authorize_query["code_challenge"] == [expected_challenge]
    assert authorize_query["code_challenge_method"] == ["S256"]
    assert authorize_query["locale"] == ["en_GB"]

    login_request = next(
        request for request in requests_mock.request_history
        if request.path == "/commonauth"
    )
    login_data = parse_qs(login_request.text)
    assert login_data["userName"] == ["test@example.com"]
    assert login_data["username"] == ["NG/test@example.com"]
    assert login_data["regionCode"] == ["NG"]

    wso2_request = next(
        request for request in requests_mock.request_history
        if request.path == "/oauth2/token"
    )
    wso2_data = parse_qs(wso2_request.text)
    assert wso2_data["code_verifier"] == ["v" * 64]
    assert wso2_data["code"] == ["test-code"]

    kamereon_request = next(
        request for request in requests_mock.request_history
        if request.path == "/bff-web/v1/oauth2/access_token"
    )
    assert kamereon_request.headers["Authorization"] == "wso2-id-token"
    assert parse_qs(urlparse(kamereon_request.url).query)["platform"] == ["Android"]
    assert session.oauth.token["access_token"] == "kamereon-access-token"
    assert session.oauth.token["refresh_token"] == "kamereon-refresh-token"


def test_login_rejects_invalid_credentials(requests_mock):
    requests_mock.get(
        f"{AUTH_BASE_URL}oauth2/authorize",
        status_code=302,
        headers={
            "Location": f"{AUTH_BASE_URL}authenticationendpoint/login.do"
        },
    )
    requests_mock.get(
        f"{AUTH_BASE_URL}authenticationendpoint/login.do",
        text=login_form(),
    )
    requests_mock.post(
        f"{AUTH_BASE_URL}commonauth",
        status_code=302,
        headers={
            "Location": (
                f"{AUTH_BASE_URL}authenticationendpoint/login.do"
                "?authFailure=true"
            )
        },
    )

    session = NCISession(region="EU")
    with patch(
        "custom_components.nissan_connect.kamereon.kamereon.secrets.token_urlsafe",
        side_effect=["v" * 64, "test-state"],
    ), pytest.raises(NissanAuthError, match="Invalid credentials"):
        session.login("test@example.com", "wrong-password")


def test_login_rejects_callback_without_code(requests_mock):
    requests_mock.get(
        f"{AUTH_BASE_URL}oauth2/authorize",
        status_code=302,
        headers={
            "Location": f"{AUTH_BASE_URL}authenticationendpoint/login.do"
        },
    )
    requests_mock.get(
        f"{AUTH_BASE_URL}authenticationendpoint/login.do",
        text=login_form(),
    )
    requests_mock.post(
        f"{AUTH_BASE_URL}commonauth",
        status_code=302,
        headers={"Location": f"{REDIRECT_URI}?error=access_denied&state=test-state"},
    )

    session = NCISession(region="EU")
    with patch(
        "custom_components.nissan_connect.kamereon.kamereon.secrets.token_urlsafe",
        side_effect=["v" * 64, "test-state"],
    ), pytest.raises(NissanAuthError, match="Invalid credentials"):
        session.login("test@example.com", "wrong-password")


def test_login_transport_error_is_not_auth_error(requests_mock):
    requests_mock.get(
        f"{AUTH_BASE_URL}oauth2/authorize",
        exc=requests.ConnectionError,
    )
    session = NCISession(region="EU")

    with pytest.raises(
        RuntimeError, match="Unable to contact Nissan login"
    ) as error_info:
        session.login("test@example.com", "test-password")

    assert not isinstance(error_info.value, NissanAuthError)


def test_login_rejects_external_form_target(requests_mock):
    external_url = "https://example.invalid/collect"
    requests_mock.get(
        f"{AUTH_BASE_URL}oauth2/authorize",
        text=login_form().replace("../commonauth", external_url),
    )
    session = NCISession(region="EU")

    with patch(
        "custom_components.nissan_connect.kamereon.kamereon.secrets.token_urlsafe",
        side_effect=["v" * 64, "test-state"],
    ), pytest.raises(RuntimeError, match="Unexpected Nissan login form target"):
        session.login("test@example.com", "test-password")

    assert all(request.url != external_url for request in requests_mock.request_history)


def test_login_rejects_external_authorization_redirect(requests_mock):
    register_successful_login(requests_mock)
    external_url = "https://example.invalid/callback"
    requests_mock.post(
        f"{AUTH_BASE_URL}commonauth",
        status_code=302,
        headers={"Location": external_url},
    )
    session = NCISession(region="EU")

    with patch(
        "custom_components.nissan_connect.kamereon.kamereon.secrets.token_urlsafe",
        side_effect=["v" * 64, "test-state"],
    ), pytest.raises(RuntimeError, match="Unexpected Nissan authorization redirect"):
        session.login("test@example.com", "test-password")

    assert all(request.url != external_url for request in requests_mock.request_history)


def test_token_exchange_rejects_external_redirect(requests_mock):
    register_successful_login(requests_mock)
    external_url = "https://example.invalid/token"
    requests_mock.post(
        f"{AUTH_BASE_URL}oauth2/token",
        status_code=307,
        headers={"Location": external_url},
    )
    session = NCISession(region="EU")

    with patch(
        "custom_components.nissan_connect.kamereon.kamereon.secrets.token_urlsafe",
        side_effect=["v" * 64, "test-state"],
    ), pytest.raises(RuntimeError, match="Nissan OneID token"):
        session.login("test@example.com", "test-password")

    assert all(request.url != external_url for request in requests_mock.request_history)


def test_refreshes_kamereon_token_and_preserves_refresh_token(requests_mock):
    requests_mock.post(
        f"{BFF_BASE_URL}v1/oauth2/refresh-token",
        json={
            "access_token": "new-access-token",
            "token_type": "Bearer",
            "expires_in": 1800,
        },
    )
    session = NCISession(region="EU")
    session._kamereon_refresh_token = "existing-refresh-token"

    session._refresh_kamereon_token()

    request = requests_mock.last_request
    assert request.headers["Authorization"] == "existing-refresh-token"
    assert request.json() == {"scope": "openid profile vehicles"}
    assert session.oauth.token["access_token"] == "new-access-token"
    assert session.oauth.token["refresh_token"] == "existing-refresh-token"


def test_request_retries_with_refreshed_kamereon_token(requests_mock):
    user_url = (
        "https://alliance-platform-usersadapter-prod.apps.eu2.kamereon.io/"
        "user-adapter/v1/users/current"
    )
    requests_mock.get(
        user_url,
        [
            {"status_code": 401},
            {"json": {"userId": "test-user"}},
        ],
    )
    requests_mock.post(
        f"{BFF_BASE_URL}v1/oauth2/refresh-token",
        json={
            "access_token": "new-access-token",
            "token_type": "Bearer",
            "expires_in": 1800,
        },
    )
    session = NCISession(region="EU")
    session._kamereon_refresh_token = "existing-refresh-token"
    session._install_kamereon_token({
        "access_token": "old-access-token",
        "refresh_token": "existing-refresh-token",
        "token_type": "Bearer",
        "expires_in": 1800,
    })

    response = session.request("GET", user_url)

    assert response.json() == {"userId": "test-user"}
    user_requests = [
        request for request in requests_mock.request_history
        if request.url == user_url
    ]
    assert [request.headers["Authorization"] for request in user_requests] == [
        "Bearer old-access-token",
        "Bearer new-access-token",
    ]


def test_fetch_vehicles_uses_kamereon_bearer_token(requests_mock):
    user_url = (
        "https://alliance-platform-usersadapter-prod.apps.eu2.kamereon.io/"
        "user-adapter/v1/users/current"
    )
    vehicles_url = f"{BFF_BASE_URL}v5/users/test-user/cars"
    requests_mock.get(user_url, json={"userId": "test-user"})
    requests_mock.get(vehicles_url, json={"data": [{"vin": "test-vin"}]})
    session = NCISession(region="EU")
    session._install_kamereon_token({
        "access_token": "kamereon-access-token",
        "refresh_token": "kamereon-refresh-token",
        "token_type": "Bearer",
        "expires_in": 1800,
    })

    vehicles = session.fetch_vehicles()

    assert [vehicle.vin for vehicle in vehicles] == ["TEST-VIN"]
    assert [request.headers["Authorization"] for request in requests_mock.request_history] == [
        "Bearer kamereon-access-token",
        "Bearer kamereon-access-token",
    ]


def test_login_requires_credentials():
    session = NCISession(region="EU")

    with pytest.raises(RuntimeError, match="Credentials are required"):
        session.login()


def _fetch_test_vehicle(requests_mock):
    user_url = (
        "https://alliance-platform-usersadapter-prod.apps.eu2.kamereon.io/"
        "user-adapter/v1/users/current"
    )
    vehicles_url = f"{BFF_BASE_URL}v5/users/test-user/cars"
    requests_mock.get(user_url, json={"userId": "test-user"})
    requests_mock.get(vehicles_url, json={"data": [{"vin": "test-vin"}]})
    session = NCISession(region="EU")
    session._install_kamereon_token({
        "access_token": "kamereon-access-token",
        "refresh_token": "kamereon-refresh-token",
        "token_type": "Bearer",
        "expires_in": 1800,
    })
    return session.fetch_vehicles()[0]


def test_register_device_treats_already_registered_as_success(requests_mock):
    """A previous attempt may already have registered this device_id (e.g. it
    got this far before failing on a later step like SRP enrollment) - retrying
    must not fail just because the device is already there."""
    vehicle = _fetch_test_vehicle(requests_mock)
    register_url = f"{BFF_BASE_URL}v1/users/test-user/vehicles/TEST-VIN/register-device"
    requests_mock.post(
        register_url,
        status_code=409,
        json={
            "errors": [{
                "status": "Conflict",
                "code": "409010",
                "title": "Device already exists",
                "detail": "Device  - some-device-id already exists for requested user vehicle",
            }]
        },
    )

    # Must not raise.
    vehicle.register_device("some-device-id", "123456")


def test_register_device_raises_on_other_conflicts(requests_mock):
    """A 409 with a different error code is a real failure, not idempotent
    re-registration, and must still surface."""
    vehicle = _fetch_test_vehicle(requests_mock)
    register_url = f"{BFF_BASE_URL}v1/users/test-user/vehicles/TEST-VIN/register-device"
    requests_mock.post(
        register_url,
        status_code=409,
        json={"errors": [{"status": "Conflict", "code": "409999", "title": "Some other conflict"}]},
    )

    with pytest.raises(ValueError, match="409999"):
        vehicle.register_device("some-device-id", "123456")


def test_register_device_raises_on_invalid_otp(requests_mock):
    vehicle = _fetch_test_vehicle(requests_mock)
    register_url = f"{BFF_BASE_URL}v1/users/test-user/vehicles/TEST-VIN/register-device"
    requests_mock.post(
        register_url,
        status_code=400,
        json={"errors": [{"status": "Bad Request", "code": "400001", "title": "Invalid OTP"}]},
    )

    with pytest.raises(ValueError, match="Invalid OTP"):
        vehicle.register_device("some-device-id", "000000")


def test_register_device_succeeds(requests_mock):
    vehicle = _fetch_test_vehicle(requests_mock)
    register_url = f"{BFF_BASE_URL}v1/users/test-user/vehicles/TEST-VIN/register-device"
    requests_mock.post(register_url, status_code=200, json={})

    vehicle.register_device("some-device-id", "123456")

    request = requests_mock.last_request
    assert request.json() == {
        "data": {
            "type": "RegisterDevice",
            "attributes": {
                "deviceId": "some-device-id",
                "otp": "123456",
                "modelName": "Home Assistant",
            },
        }
    }


def test_poll_action_status_tolerates_early_404(requests_mock):
    """actions/status lives on a separate microservice from the one that
    creates the action, so a 404 shortly after creation means "not indexed
    yet", not "will never exist" - it must be retried, not raised."""
    vehicle = _fetch_test_vehicle(requests_mock)
    status_url = (
        "https://alliance-platform-action-status-polling-prod.apps.eu2.kamereon.io/"
        "v1/cars/TEST-VIN/actions/status"
    )
    requests_mock.get(
        status_url,
        [
            {"status_code": 404, "json": {"errors": [{"code": "404", "title": "Not found exception"}]}},
            {"status_code": 200, "json": {"data": {"attributes": {"status": "COMPLETED"}}}},
        ],
    )

    attributes = next(vehicle._poll_action_status(
        "some-action-id", timeout=5, interval=0.01, initial_delay=0
    ))

    assert attributes == {"status": "COMPLETED"}


def test_poll_action_status_raises_on_other_errors(requests_mock):
    vehicle = _fetch_test_vehicle(requests_mock)
    status_url = (
        "https://alliance-platform-action-status-polling-prod.apps.eu2.kamereon.io/"
        "v1/cars/TEST-VIN/actions/status"
    )
    requests_mock.get(
        status_url,
        status_code=500,
        json={"errors": [{"code": "500", "title": "Internal error"}]},
    )

    with pytest.raises(ValueError, match="Internal error"):
        next(vehicle._poll_action_status(
            "some-action-id", timeout=5, interval=0.01, initial_delay=0
        ))


def test_initiate_srp_sends_correct_body_and_headers(requests_mock):
    vehicle = _fetch_test_vehicle(requests_mock)
    srp_initiates_url = (
        "https://alliance-platform-caradapter-prod.apps.eu2.kamereon.io/"
        "car-adapter/v1/cars/TEST-VIN/actions/srp-initiates"
    )
    requests_mock.post(srp_initiates_url, status_code=200, json={"data": {"type": "SrpInitiates"}})

    vehicle.initiate_srp("1234")

    request = next(r for r in requests_mock.request_history if r.url == srp_initiates_url)
    assert request.headers["Content-Type"] == "application/vnd.api+json"
    body = request.json()
    attrs = body["data"]["attributes"]
    assert body["data"]["type"] == "SrpInitiates"
    assert attrs["i"] == "test-user"
    assert len(attrs["s"]) == 20  # 10 random bytes, hex-encoded
    assert len(attrs["v"]) == 512  # 256-byte verifier, hex-encoded


def test_validate_srp_sends_correct_body_and_headers(requests_mock):
    vehicle = _fetch_test_vehicle(requests_mock)
    srp_sets_url = (
        "https://alliance-platform-caradapter-prod.apps.eu2.kamereon.io/"
        "car-adapter/v1/cars/TEST-VIN/actions/srp-sets"
    )
    requests_mock.post(
        srp_sets_url, status_code=200,
        json={"data": {"type": "SrpSets", "id": "action-abc"}},
    )
    srp_session = SRP()

    action_id = vehicle.validate_srp(srp_session)

    assert action_id == "action-abc"
    request = next(r for r in requests_mock.request_history if r.url == srp_sets_url)
    assert request.headers["Content-Type"] == "application/vnd.api+json"
    body = request.json()
    assert body["data"]["type"] == "SrpSets"
    assert body["data"]["attributes"]["i"] == "test-user"
    assert len(body["data"]["attributes"]["a"]) == 512  # 256-byte A, hex-encoded


def _lock_unlock_urls(vin="TEST-VIN"):
    lock_unlock_url = (
        "https://alliance-platform-caradapter-prod.apps.eu2.kamereon.io/"
        f"car-adapter/v1/cars/{vin}/actions/lock-unlock"
    )
    status_url = (
        "https://alliance-platform-action-status-polling-prod.apps.eu2.kamereon.io/"
        f"v1/cars/{vin}/actions/status"
    )
    return lock_unlock_url, status_url


def _wake_up_url(vin="TEST-VIN"):
    return (
        "https://alliance-platform-caradapter-prod.apps.eu2.kamereon.io/"
        f"car-adapter/v1/cars/{vin}/actions/wake-up-vehicle"
    )


def test_wake_up_vehicle_posts_expected_body(requests_mock):
    vehicle = _fetch_test_vehicle(requests_mock)
    wake_up_url = _wake_up_url()
    requests_mock.post(wake_up_url, status_code=200, json={"data": {"type": "WakeUpVehicle"}})

    vehicle.wake_up_vehicle()

    request = requests_mock.last_request
    assert request.url == wake_up_url
    assert request.json() == {"data": {"type": "WakeUpVehicle"}}
    assert request.headers["Content-Type"] == "application/vnd.api+json"


def test_wake_up_vehicle_does_not_raise_on_error(requests_mock):
    """Best-effort - a failure here shouldn't block the lock/unlock attempt
    that follows it."""
    vehicle = _fetch_test_vehicle(requests_mock)
    requests_mock.post(
        _wake_up_url(), status_code=500,
        json={"errors": [{"code": "500", "title": "Internal error"}]},
    )

    vehicle.wake_up_vehicle()  # must not raise


def test_wake_up_vehicle_does_not_raise_on_transport_error(requests_mock):
    vehicle = _fetch_test_vehicle(requests_mock)
    requests_mock.post(_wake_up_url(), exc=requests.ConnectionError)

    vehicle.wake_up_vehicle()  # must not raise


def test_lock_unlock_wakes_up_vehicle_first(requests_mock):
    vehicle = _fetch_test_vehicle(requests_mock)
    vehicle.features.append(Feature.APP_DOOR_LOCKING)
    wake_up_url = _wake_up_url()
    requests_mock.post(wake_up_url, status_code=200, json={"data": {"type": "WakeUpVehicle"}})

    with patch.object(vehicle, "srp_proof", side_effect=RuntimeError("stop here")):
        with pytest.raises(RuntimeError, match="stop here"):
            vehicle.lock_unlock("1234", "unlock")

    wake_up_requests = [r for r in requests_mock.request_history if r.url == wake_up_url]
    assert len(wake_up_requests) == 1


def test_lock_unlock_sends_correct_body_and_confirms_completion(requests_mock):
    vehicle = _fetch_test_vehicle(requests_mock)
    vehicle.features.append(Feature.APP_DOOR_LOCKING)
    lock_unlock_url, status_url = _lock_unlock_urls()
    requests_mock.post(_wake_up_url(), status_code=200, json={"data": {"type": "WakeUpVehicle"}})
    requests_mock.post(
        lock_unlock_url, status_code=200, json={"data": {"type": "LockUnlock", "id": "action-123"}}
    )
    requests_mock.get(
        status_url, status_code=200,
        json={"data": {"attributes": {"status": "COMPLETED"}}},
    )

    with patch.object(vehicle, "srp_proof", return_value="test-srp-proof") as mock_srp_proof:
        vehicle.lock_unlock("1234", "unlock")

    mock_srp_proof.assert_called_once_with("1234", "TEST-VIN/RLU/Unlock")
    request = next(r for r in requests_mock.request_history if r.url == lock_unlock_url)
    assert request.headers["Content-Type"] == "application/vnd.api+json"
    status_request = next(r for r in requests_mock.request_history if r.url.startswith(status_url))
    assert status_request.headers["Content-Type"] == "application/vnd.api+json"
    assert request.json() == {
        "data": {
            "type": "LockUnlock",
            "attributes": {
                "action": "unlock",
                "target": "doors_hatch",
                "srp": "test-srp-proof",
            },
        }
    }


def test_lock_unlock_raises_if_action_does_not_complete(requests_mock):
    """The initial POST only means 'accepted for processing' - a vehicle
    that rejects/cancels the actual command afterwards must surface as a
    failure, not a silent no-op success."""
    vehicle = _fetch_test_vehicle(requests_mock)
    vehicle.features.append(Feature.APP_DOOR_LOCKING)
    lock_unlock_url, status_url = _lock_unlock_urls()
    requests_mock.post(_wake_up_url(), status_code=200, json={"data": {"type": "WakeUpVehicle"}})
    requests_mock.post(
        lock_unlock_url, status_code=200, json={"data": {"type": "LockUnlock", "id": "action-123"}}
    )
    requests_mock.get(
        status_url, status_code=200,
        json={"data": {"attributes": {"status": "CANCELLED", "errorCode": "12"}}},
    )

    with patch.object(vehicle, "srp_proof", return_value="test-srp-proof"):
        with pytest.raises(ValueError, match="status=CANCELLED"):
            vehicle.lock_unlock("1234", "unlock")


def test_lock_unlock_succeeds_without_action_id(requests_mock):
    """Defensive fallback: if the response has no action id to confirm
    against, treat acceptance as done rather than failing outright."""
    vehicle = _fetch_test_vehicle(requests_mock)
    vehicle.features.append(Feature.APP_DOOR_LOCKING)
    lock_unlock_url, _ = _lock_unlock_urls()
    requests_mock.post(_wake_up_url(), status_code=200, json={"data": {"type": "WakeUpVehicle"}})
    requests_mock.post(lock_unlock_url, status_code=200, json={"data": {"type": "LockUnlock"}})

    with patch.object(vehicle, "srp_proof", return_value="test-srp-proof"):
        vehicle.lock_unlock("1234", "lock")  # must not raise


def test_poll_srp_challenge_raises_immediately_on_rejection(requests_mock):
    """A CANCELLED/REJECTED status with a KO/errorCode payload (empty
    srpLoginB/srpLoginS) is a definitive rejection from the vehicle and must
    raise immediately - not be polled until the overall timeout elapses just
    because the response happens to carry a 'data' array."""
    vehicle = _fetch_test_vehicle(requests_mock)
    status_url = (
        "https://alliance-platform-action-status-polling-prod.apps.eu2.kamereon.io/"
        "v1/cars/TEST-VIN/actions/status"
    )
    requests_mock.get(
        status_url,
        status_code=200,
        json={
            "data": {
                "attributes": {
                    "status": "CANCELLED",
                    "ruleKey": "srp.salt.request",
                    "data": [
                        {"name": "status", "type": "STRING", "value": "KO"},
                        {"name": "errorCode", "type": "INTEGER", "value": "12"},
                        {"name": "srpLoginB", "type": "STRING", "value": ""},
                        {"name": "srpLoginS", "type": "STRING", "value": ""},
                    ],
                }
            }
        },
    )

    with pytest.raises(ValueError, match="errorCode=12"):
        vehicle._poll_srp_challenge("some-action-id", timeout=5, interval=0.01)

    status_requests = [r for r in requests_mock.request_history if r.url.startswith(status_url)]
    assert len(status_requests) == 1


def test_vehicle_request_does_not_retry_auth_failures(requests_mock):
    """A bad password must surface at once, not drive repeated logins."""
    user_url = (
        "https://alliance-platform-usersadapter-prod.apps.eu2.kamereon.io/"
        "user-adapter/v1/users/current"
    )
    vehicles_url = f"{BFF_BASE_URL}v5/users/test-user/cars"
    requests_mock.get(user_url, json={"userId": "test-user"})
    requests_mock.get(vehicles_url, json={"data": [{"vin": "test-vin"}]})
    session = NCISession(region="EU")
    session._install_kamereon_token({
        "access_token": "kamereon-access-token",
        "token_type": "Bearer",
        "expires_in": 1800,
    })
    vehicle = session.fetch_vehicles()[0]

    with patch.object(
        session, "request", side_effect=NissanAuthError("Invalid credentials")
    ) as mock_request:
        with pytest.raises(NissanAuthError):
            vehicle._get("https://example.invalid/anything")

    assert mock_request.call_count == 1
