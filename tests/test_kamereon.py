import base64
import hashlib
from urllib.parse import parse_qs, urlparse
from unittest.mock import patch

import pytest
import requests

from custom_components.nissan_connect.kamereon import NCISession, NissanAuthError


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
