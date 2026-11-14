import base64
import hashlib
import http.client
import socket
from urllib.parse import parse_qs, urlparse
from oauthlib.oauth2 import TokenExpiredError
from unittest.mock import patch
from urllib3.exceptions import MaxRetryError, ProtocolError

import pytest
import requests

from custom_components.nissan_connect.kamereon import (
    Feature,
    HVACAction,
    NCISession,
    NissanAuthError,
)
from custom_components.nissan_connect.kamereon.kamereon import (
    REQUEST_TIMEOUT,
    TCP_KEEPALIVE_IDLE,
    _is_pre_response_disconnect,
)


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


def _vehicle(requests_mock, model="TOWNSTAR"):
    """A vehicle whose session is already authenticated."""
    user_url = (
        "https://alliance-platform-usersadapter-prod.apps.eu2.kamereon.io/"
        "user-adapter/v1/users/current"
    )
    requests_mock.get(user_url, json={"userId": "test-user"})
    requests_mock.get(f"{BFF_BASE_URL}v5/users/test-user/cars", json={"data": [
        {"vin": "test-vin", "modelName": model}]})
    session = NCISession(region="EU")
    session._install_kamereon_token({
        "access_token": "kamereon-access-token",
        "token_type": "Bearer",
        "expires_in": 1800,
    })
    return session.fetch_vehicles()[0]


CAR_BASE_URL = (
    "https://alliance-platform-caradapter-prod.apps.eu2.kamereon.io/car-adapter/"
)
# Verbatim from a Townstar (dan-r/HomeAssistant-NissanConnect#109)
GATEWAY_NOT_IMPLEMENTED = {"errors": [{
    "status": "Not Implemented", "code": "501", "title": "Not supported Feature",
    "detail": "This feature is not technically supported by this gateway"}]}


def _cockpit_requests(requests_mock):
    return [r.path for r in requests_mock.request_history if "cockpit" in r.path]


def test_cockpit_still_uses_v1_when_it_works(requests_mock):
    """Cars that work today must not gain an extra request."""
    vehicle = _vehicle(requests_mock, model="LEAF")
    requests_mock.get(f"{CAR_BASE_URL}v1/cars/TEST-VIN/cockpit", json={"data": {
        "attributes": {"totalMileage": 1000.0, "fuelLevel": 50}}})

    vehicle.fetch_cockpit()

    assert vehicle.total_mileage == 1000.0
    assert _cockpit_requests(requests_mock) == ["/car-adapter/v1/cars/test-vin/cockpit"]


def test_cockpit_falls_back_to_v2_when_gateway_does_not_implement_v1(requests_mock):
    """The Townstar's RVG gateway answers v1 with 501 but serves v2."""
    vehicle = _vehicle(requests_mock)
    requests_mock.get(f"{CAR_BASE_URL}v1/cars/TEST-VIN/cockpit",
                      json=GATEWAY_NOT_IMPLEMENTED, status_code=501)
    requests_mock.get(f"{CAR_BASE_URL}v2/cars/TEST-VIN/cockpit", json={"data": {
        "attributes": {"fuelAutonomy": 671.0, "fuelQuantity": 52.0,
                       "totalMileage": 2580.0}}})

    vehicle.fetch_cockpit()

    assert vehicle.total_mileage == 2580.0
    assert vehicle.fuel_autonomy == 671.0
    assert vehicle.fuel_quantity == 52.0
    assert _cockpit_requests(requests_mock) == [
        "/car-adapter/v1/cars/test-vin/cockpit",
        "/car-adapter/v2/cars/test-vin/cockpit",
    ]


def test_cockpit_version_is_resolved_only_once(requests_mock):
    """After the first fetch we must stop calling the unsupported version."""
    vehicle = _vehicle(requests_mock)
    requests_mock.get(f"{CAR_BASE_URL}v1/cars/TEST-VIN/cockpit",
                      json=GATEWAY_NOT_IMPLEMENTED, status_code=501)
    requests_mock.get(f"{CAR_BASE_URL}v2/cars/TEST-VIN/cockpit", json={"data": {
        "attributes": {"totalMileage": 2580.0}}})

    vehicle.fetch_cockpit()
    vehicle.fetch_cockpit()
    vehicle.fetch_cockpit()

    assert _cockpit_requests(requests_mock) == [
        "/car-adapter/v1/cars/test-vin/cockpit",
        "/car-adapter/v2/cars/test-vin/cockpit",
        "/car-adapter/v2/cars/test-vin/cockpit",
        "/car-adapter/v2/cars/test-vin/cockpit",
    ]


def test_cockpit_does_not_probe_other_versions_on_a_real_error(requests_mock):
    """A 403 is a real failure, not 'try another version'."""
    vehicle = _vehicle(requests_mock)
    requests_mock.get(f"{CAR_BASE_URL}v1/cars/TEST-VIN/cockpit", status_code=403, json={
        "errors": [{"status": "Forbidden", "code": "403", "title": "security.access"}]})

    with pytest.raises(ValueError):
        vehicle.fetch_cockpit()

    assert _cockpit_requests(requests_mock) == ["/car-adapter/v1/cars/test-vin/cockpit"]


def test_cockpit_raises_when_no_version_is_served(requests_mock):
    vehicle = _vehicle(requests_mock)
    for version in ("v1", "v2"):
        requests_mock.get(f"{CAR_BASE_URL}{version}/cars/TEST-VIN/cockpit",
                          json=GATEWAY_NOT_IMPLEMENTED, status_code=501)

    with pytest.raises(ValueError):
        vehicle.fetch_cockpit()


def test_api_requests_time_out(requests_mock):
    """A stalled connection must not block the executor thread forever."""
    vehicle = _vehicle(requests_mock, model="LEAF")
    requests_mock.get(f"{CAR_BASE_URL}v1/cars/TEST-VIN/cockpit", json={"data": {
        "attributes": {"totalMileage": 1000.0}}})

    vehicle.fetch_cockpit()

    assert requests_mock.request_history
    assert all(r.timeout == REQUEST_TIMEOUT for r in requests_mock.request_history)


def test_get_is_retried_after_a_transport_error(requests_mock):
    vehicle = _vehicle(requests_mock, model="LEAF")
    url = f"{CAR_BASE_URL}v1/cars/TEST-VIN/cockpit"
    requests_mock.get(url, [
        {"exc": requests.ConnectionError("reset")},
        {"json": {"data": {"attributes": {"totalMileage": 1000.0}}}},
    ])

    with patch("custom_components.nissan_connect.kamereon.kamereon.time.sleep") as sleep:
        vehicle.fetch_cockpit()

    sleep.assert_called_once_with(1)
    assert vehicle.total_mileage == 1000.0
    assert _cockpit_requests(requests_mock) == [
        "/car-adapter/v1/cars/test-vin/cockpit",
        "/car-adapter/v1/cars/test-vin/cockpit",
    ]


def test_car_command_is_not_resent_after_a_timeout(requests_mock):
    """The horn may already be sounding; a retry would sound it again."""
    vehicle = _vehicle(requests_mock, model="LEAF")
    vehicle.features.append(Feature.HORN_AND_LIGHTS)
    requests_mock.post(f"{CAR_BASE_URL}v1/cars/TEST-VIN/actions/horn-lights",
                       exc=requests.Timeout("read timed out"))

    with patch("custom_components.nissan_connect.kamereon.kamereon.time.sleep"):
        with pytest.raises(requests.Timeout):
            vehicle.control_horn_lights("start", "horn_lights")

    assert [r.path for r in requests_mock.request_history if "horn-lights" in r.path] == [
        "/car-adapter/v1/cars/test-vin/actions/horn-lights",
    ]


def test_persistent_401_is_not_retried(requests_mock):
    """Each retry would cost another full login, so give up after one."""
    vehicle = _vehicle(requests_mock, model="LEAF")

    with patch.object(
        vehicle.session, "request", side_effect=TokenExpiredError()
    ) as mock_request:
        with pytest.raises(TokenExpiredError):
            vehicle._get("https://example.invalid/anything")

    assert mock_request.call_count == 1


# Verbatim from a petrol Townstar (dan-r/HomeAssistant-NissanConnect#109)
BATTERY_ADAPTER_500 = {"errors": [{
    "code": "500", "status": "Internal Server Error",
    "title": "BatteryAdapter.getBatteryStatus()"}]}


def _ice_vehicle(requests_mock):
    """A vehicle that does not advertise BATTERY_STATUS."""
    user_url = (
        "https://alliance-platform-usersadapter-prod.apps.eu2.kamereon.io/"
        "user-adapter/v1/users/current"
    )
    requests_mock.get(user_url, json={"userId": "test-user"})
    requests_mock.get(f"{BFF_BASE_URL}v5/users/test-user/cars", json={"data": [{
        "vin": "test-vin", "modelName": "TOWNSTAR",
        "services": [{"id": "12", "activationState": "ACTIVATED"}]}]})
    session = NCISession(region="EU")
    session._install_kamereon_token({
        "access_token": "kamereon-access-token",
        "token_type": "Bearer", "expires_in": 1800})
    return session.fetch_vehicles()[0]


def _battery_requests(requests_mock):
    return [r.path for r in requests_mock.request_history if "battery-status" in r.path]


def test_battery_status_is_probed_then_abandoned(requests_mock):
    """A car whose gateway 500s here must not be asked forever."""
    vehicle = _ice_vehicle(requests_mock)
    requests_mock.get(f"{CAR_BASE_URL}v2/cars/TEST-VIN/battery-status",
                      json=BATTERY_ADAPTER_500, status_code=500)

    for _ in range(10):
        vehicle.fetch_battery_status()

    assert len(_battery_requests(requests_mock)) == 3
    assert vehicle._battery_status_supported is False


def test_a_transient_error_does_not_abandon_the_endpoint(requests_mock):
    """An ICE vehicle that does publish its range here must keep it."""
    vehicle = _ice_vehicle(requests_mock)
    # Townstar battery-status is the v2 endpoint and reports batteryAutonomy.
    requests_mock.get(f"{CAR_BASE_URL}v2/cars/TEST-VIN/battery-status", [
        {"json": BATTERY_ADAPTER_500, "status_code": 500},
        {"json": BATTERY_ADAPTER_500, "status_code": 500},
        {"json": {"data": {"attributes": {"batteryAutonomy": 480}}}, "status_code": 200},
        {"json": BATTERY_ADAPTER_500, "status_code": 500},
    ])

    for _ in range(4):
        vehicle.fetch_battery_status()

    assert vehicle.range_hvac_on == 480
    assert vehicle._battery_status_supported is True
    assert len(_battery_requests(requests_mock)) == 4


def test_an_ev_still_raises_immediately(requests_mock):
    """With BATTERY_STATUS active an error is a real failure, not a probe."""
    user_url = (
        "https://alliance-platform-usersadapter-prod.apps.eu2.kamereon.io/"
        "user-adapter/v1/users/current"
    )
    requests_mock.get(user_url, json={"userId": "test-user"})
    requests_mock.get(f"{BFF_BASE_URL}v5/users/test-user/cars", json={"data": [{
        "vin": "test-vin", "modelName": "LEAF",
        "services": [{"id": "319", "activationState": "ACTIVATED"}]}]})
    session = NCISession(region="EU")
    session._install_kamereon_token({
        "access_token": "kamereon-access-token",
        "token_type": "Bearer", "expires_in": 1800})
    vehicle = session.fetch_vehicles()[0]
    requests_mock.get(f"{CAR_BASE_URL}v1/cars/TEST-VIN/battery-status",
                      json=BATTERY_ADAPTER_500, status_code=500)

    with pytest.raises(ValueError):
        vehicle.fetch_battery_status()
    assert vehicle._battery_status_supported is True


def _connection_reset():
    """The exception requests raises when a keep-alive read dies at the status line."""
    reset = ConnectionResetError(104, "Connection reset by peer")
    return requests.ConnectionError(ProtocolError("Connection aborted.", reset))


def _remote_disconnected():
    remote = http.client.RemoteDisconnected(
        "Remote end closed connection without response")
    return requests.ConnectionError(ProtocolError("Connection aborted.", remote))


def _action_paths(requests_mock, action):
    return [request.path for request in requests_mock.request_history if action in request.path]


class _IdleConnection:
    def __init__(self):
        self.closed = False

    def close(self):
        self.closed = True


def _plant_idle_connection(vehicle):
    adapter = vehicle.session.oauth.get_adapter(CAR_BASE_URL)
    pool = adapter.poolmanager.connection_from_url(CAR_BASE_URL)
    pool.pool.get_nowait()
    conn = _IdleConnection()
    pool.pool.put(conn)
    return conn


def test_stale_reset_is_recognised_through_urllib3_wrappers():
    assert _is_pre_response_disconnect(_connection_reset())
    assert _is_pre_response_disconnect(_remote_disconnected())

    reset = ConnectionResetError(104, "Connection reset by peer")
    protocol = ProtocolError("Connection aborted.", reset)
    try:
        raise MaxRetryError(None, "/cmd", protocol) from protocol
    except MaxRetryError as err:
        wrapped = requests.ConnectionError(err)
    assert _is_pre_response_disconnect(wrapped)

    answered = _connection_reset()
    answered.response = requests.Response()
    assert not _is_pre_response_disconnect(answered)
    assert not _is_pre_response_disconnect(requests.Timeout("read timed out"))
    assert not _is_pre_response_disconnect(requests.ConnectionError("reset"))
    assert not _is_pre_response_disconnect(
        requests.exceptions.ChunkedEncodingError(protocol))


def _command_vehicle(requests_mock, feature=None):
    vehicle = _vehicle(requests_mock)
    if feature is not None:
        vehicle.features.append(feature)
    return vehicle


@pytest.mark.parametrize("failure", [_connection_reset, _remote_disconnected])
def test_charging_is_retried_once_when_the_connection_closes_first(requests_mock, failure):
    vehicle = _command_vehicle(requests_mock, Feature.CHARGING_START)
    url = f"{CAR_BASE_URL}v1/cars/TEST-VIN/actions/charging-start"
    requests_mock.post(url, [
        {"exc": failure()},
        {"json": {"data": {"type": "ChargingStart"}}},
    ])

    with patch("custom_components.nissan_connect.kamereon.kamereon.time.sleep") as sleep:
        body = vehicle.control_charging("start")

    assert body == {"data": {"type": "ChargingStart"}}
    assert _action_paths(requests_mock, "charging-start") == [
        "/car-adapter/v1/cars/test-vin/actions/charging-start",
        "/car-adapter/v1/cars/test-vin/actions/charging-start",
    ]
    sleep.assert_not_called()


def test_charging_is_not_sent_a_third_time(requests_mock):
    vehicle = _command_vehicle(requests_mock, Feature.CHARGING_START)
    url = f"{CAR_BASE_URL}v1/cars/TEST-VIN/actions/charging-start"
    requests_mock.post(url, [
        {"exc": _connection_reset()},
        {"exc": _connection_reset()},
    ])

    with patch("custom_components.nissan_connect.kamereon.kamereon.time.sleep"):
        with pytest.raises(requests.ConnectionError):
            vehicle.control_charging("start")

    assert len(_action_paths(requests_mock, "charging-start")) == 2


@pytest.mark.parametrize("failure", [
    lambda: requests.Timeout("read timed out"),
    lambda: requests.ConnectionError("reset"),
    lambda: requests.exceptions.ChunkedEncodingError(
        ProtocolError("Connection aborted.", ConnectionResetError(104, "Connection reset by peer"))),
])
def test_charging_is_not_resent_once_a_response_or_timeout_happened(requests_mock, failure):
    vehicle = _command_vehicle(requests_mock, Feature.CHARGING_START)
    exc = failure()
    requests_mock.post(
        f"{CAR_BASE_URL}v1/cars/TEST-VIN/actions/charging-start", exc=exc)

    with patch("custom_components.nissan_connect.kamereon.kamereon.time.sleep") as sleep:
        with pytest.raises(type(exc)):
            vehicle.control_charging("start")

    assert len(_action_paths(requests_mock, "charging-start")) == 1
    sleep.assert_not_called()


def test_charging_is_not_resent_when_the_reset_carries_a_response(requests_mock):
    vehicle = _command_vehicle(requests_mock, Feature.CHARGING_START)
    err = _connection_reset()
    err.response = requests.Response()
    requests_mock.post(
        f"{CAR_BASE_URL}v1/cars/TEST-VIN/actions/charging-start", exc=err)

    with pytest.raises(requests.ConnectionError):
        vehicle.control_charging("start")

    assert len(_action_paths(requests_mock, "charging-start")) == 1


@pytest.mark.parametrize("action", ["start", "stop"])
def test_hvac_is_retried_once_after_a_connection_reset(requests_mock, action):
    vehicle = _command_vehicle(requests_mock, Feature.CLIMATE_ON_OFF)
    url = f"{CAR_BASE_URL}v1/cars/TEST-VIN/actions/hvac-start"
    requests_mock.post(url, [
        {"exc": _connection_reset()},
        {"json": {"data": {"type": "HvacStart"}}},
    ])
    hvac_action = HVACAction.START if action == "start" else HVACAction.STOP

    with patch("custom_components.nissan_connect.kamereon.kamereon.time.sleep") as sleep:
        vehicle.set_hvac_status(hvac_action)

    assert len(_action_paths(requests_mock, "hvac-start")) == 2
    sleep.assert_not_called()


@pytest.mark.parametrize("method,action,feature", [
    ("refresh_battery_status", "refresh-battery-status", None),
    ("refresh_hvac_status", "refresh-hvac-status", None),
    ("refresh_lock_status", "refresh-lock-status", None),
    ("refresh_location", "refresh-location", Feature.MY_CAR_FINDER),
])
def test_refresh_commands_are_retried_once_after_a_connection_reset(
        requests_mock, method, action, feature):
    vehicle = _command_vehicle(requests_mock, feature)
    requests_mock.post(f"{CAR_BASE_URL}v1/cars/TEST-VIN/actions/{action}", [
        {"exc": _connection_reset()},
        {"json": {"data": {"type": "Refresh"}}},
    ])

    with patch("custom_components.nissan_connect.kamereon.kamereon.time.sleep"):
        getattr(vehicle, method)()

    assert len(_action_paths(requests_mock, action)) == 2


def test_horn_is_not_resent_after_a_connection_reset(requests_mock):
    vehicle = _command_vehicle(requests_mock, Feature.HORN_AND_LIGHTS)
    requests_mock.post(
        f"{CAR_BASE_URL}v1/cars/TEST-VIN/actions/horn-lights",
        exc=_connection_reset(),
    )

    with pytest.raises(requests.ConnectionError):
        vehicle.control_horn_lights("start", "horn_lights")

    assert len(_action_paths(requests_mock, "horn-lights")) == 1


def test_lock_is_not_resent_after_a_connection_reset(requests_mock):
    vehicle = _command_vehicle(requests_mock, Feature.APP_DOOR_LOCKING)
    # The lock URL is built with a trailing quote. Match that request as sent.
    requests_mock.post(
        f'{CAR_BASE_URL}v1/cars/TEST-VIN/actions/lock-unlock"',
        exc=_connection_reset(),
    )

    with pytest.raises(requests.ConnectionError):
        vehicle.lock_unlock("srp", "lock")

    assert len(_action_paths(requests_mock, "lock-unlock")) == 1


def test_commands_drop_idle_pooled_connections(requests_mock):
    vehicle = _command_vehicle(requests_mock, Feature.CHARGING_START)
    idle = _plant_idle_connection(vehicle)
    requests_mock.post(
        f"{CAR_BASE_URL}v1/cars/TEST-VIN/actions/charging-start",
        json={"data": {"type": "ChargingStart"}},
    )

    vehicle.control_charging("start")

    assert idle.closed
    assert len(_action_paths(requests_mock, "charging-start")) == 1


def test_reads_keep_idle_pooled_connections(requests_mock):
    vehicle = _vehicle(requests_mock, model="LEAF")
    idle = _plant_idle_connection(vehicle)
    requests_mock.get(
        f"{CAR_BASE_URL}v1/cars/TEST-VIN/cockpit",
        json={"data": {"attributes": {"totalMileage": 10}}},
    )

    vehicle.fetch_cockpit()

    assert idle.closed is False


def test_api_session_enables_tcp_keepalive():
    session = NCISession(region="EU")
    session._install_kamereon_token({
        "access_token": "kamereon-access-token",
        "token_type": "Bearer",
        "expires_in": 1800,
    })
    adapter = session.oauth.get_adapter("https://example.com/")
    options = adapter.poolmanager.connection_pool_kw["socket_options"]
    assert (socket.IPPROTO_TCP, socket.TCP_NODELAY, 1) in options
    assert (socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1) in options
    assert (socket.IPPROTO_TCP, socket.TCP_KEEPIDLE, TCP_KEEPALIVE_IDLE) in options
