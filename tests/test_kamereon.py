import base64
import hashlib
from urllib.parse import parse_qs, urlparse
from unittest.mock import MagicMock, patch

import pytest
import requests

from custom_components.nissan_connect.kamereon import (
    NCISession,
    NissanAuthError,
    RemoteLockError,
    RemoteLockRejected,
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


@pytest.mark.parametrize("service_id", ["2021", "886"])
def test_fetch_lock_status_supports_both_service_catalogs(requests_mock, service_id):
    user_url = (
        "https://alliance-platform-usersadapter-prod.apps.eu2.kamereon.io/"
        "user-adapter/v1/users/current"
    )
    vehicles_url = f"{BFF_BASE_URL}v5/users/test-user/cars"
    lock_url = (
        "https://alliance-platform-caradapter-prod.apps.eu2.kamereon.io/"
        "car-adapter/v1/cars/TEST-VIN/lock-status"
    )
    requests_mock.get(user_url, json={"userId": "test-user"})
    requests_mock.get(
        vehicles_url,
        json={"data": [{
            "vin": "test-vin",
            "services": [{"id": service_id, "activationState": "ACTIVATED"}],
        }]},
    )
    requests_mock.get(
        lock_url,
        json={"data": {"attributes": {
            "lockStatus": "locked",
            "lastUpdateTime": "2026-09-01T12:00:00Z",
        }}},
    )
    session = NCISession(region="EU")
    session._install_kamereon_token({
        "access_token": "kamereon-access-token",
        "token_type": "Bearer",
        "expires_in": 1800,
    })

    vehicle = session.fetch_vehicles()[0]
    vehicle.fetch_lock_status()

    assert vehicle.supports_lock_status is True
    assert vehicle.lock_status.value == "locked"
    assert requests_mock.last_request.url == lock_url


@pytest.mark.parametrize("service_id", ["27", "878"])
def test_command_service_does_not_enable_lock_status(requests_mock, service_id):
    user_url = (
        "https://alliance-platform-usersadapter-prod.apps.eu2.kamereon.io/"
        "user-adapter/v1/users/current"
    )
    vehicles_url = f"{BFF_BASE_URL}v5/users/test-user/cars"
    requests_mock.get(user_url, json={"userId": "test-user"})
    requests_mock.get(
        vehicles_url,
        json={"data": [{
            "vin": "test-vin",
            "services": [{"id": service_id, "activationState": "ACTIVATED"}],
        }]},
    )
    session = NCISession(region="EU")
    session._install_kamereon_token({
        "access_token": "kamereon-access-token",
        "token_type": "Bearer",
        "expires_in": 1800,
    })

    vehicle = session.fetch_vehicles()[0]
    request_count = len(requests_mock.request_history)
    vehicle.fetch_lock_status()

    assert vehicle.supports_lock_status is False
    assert len(requests_mock.request_history) == request_count


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


def _fetch_remote_lock_vehicle(
        requests_mock, service_ids=None, ccs_generation="1",
        is_cross_badged=False, role="OWNER"):
    if service_ids is None:
        service_ids = ["886", "878", "909"]
    user_url = (
        "https://alliance-platform-usersadapter-prod.apps.eu2.kamereon.io/"
        "user-adapter/v1/users/current"
    )
    vehicles_url = f"{BFF_BASE_URL}v5/users/test-user/cars"
    requests_mock.get(user_url, json={"userId": "test-user"})
    requests_mock.get(
        vehicles_url,
        json={"data": [{
            "vin": "test-vin",
            "ccsGen": ccs_generation,
            "isCrossBadged": is_cross_badged,
            "role": role,
            "services": [
                {"id": service_id, "activationState": "ACTIVATED"}
                for service_id in service_ids
            ],
        }]},
    )
    session = NCISession(region="EU")
    session._install_kamereon_token({
        "access_token": "kamereon-access-token",
        "token_type": "Bearer",
        "expires_in": 1800,
    })
    return session.fetch_vehicles()[0]


@pytest.mark.parametrize(
    "service_ids, ccs_generation, is_cross_badged, "
    "expected_command, expected_setup",
    [
        (["2021", "27"], "0", False, True, False),
        (["2021", "27", "747"], "2", False, True, True),
        (["886", "878", "909"], "1", False, True, True),
        (["886", "878"], "1", False, True, False),
        (["886", "878", "909"], "1", True, True, False),
        (["886", "878", "747"], "2", False, True, True),
        (["886", "878"], "2", False, True, False),
        (["878", "909"], "1", False, False, False),
    ],
)
def test_remote_lock_capability_gate(
        requests_mock, service_ids, ccs_generation,
        is_cross_badged, expected_command, expected_setup):
    vehicle = _fetch_remote_lock_vehicle(
        requests_mock,
        service_ids=service_ids,
        ccs_generation=ccs_generation,
        is_cross_badged=is_cross_badged,
    )

    assert vehicle.supports_remote_lock is expected_command
    assert vehicle.supports_remote_lock_setup is expected_setup


def test_secondary_user_cannot_set_up_remote_lock(requests_mock):
    vehicle = _fetch_remote_lock_vehicle(requests_mock, role="STANDARD")

    assert vehicle.supports_remote_lock is True
    assert vehicle.supports_remote_lock_setup is False


def test_remote_lock_device_registration_contract(requests_mock):
    vehicle = _fetch_remote_lock_vehicle(requests_mock)
    otp_url = (
        f"{BFF_BASE_URL}v1/users/test-user/vehicles/TEST-VIN/"
        "generate-device-otp"
    )
    register_url = (
        f"{BFF_BASE_URL}v1/users/test-user/vehicles/TEST-VIN/"
        "register-device"
    )
    requests_mock.post(otp_url, json={})
    requests_mock.post(register_url, json={})

    vehicle.request_remote_lock_otp("0123456789abcdef")
    vehicle.register_remote_lock_device(
        "0123456789abcdef", "123456")

    otp_request, register_request = requests_mock.request_history[-2:]
    assert otp_request.json() == {
        "data": {
            "type": "GenerateDeviceOtp",
            "attributes": {"deviceId": "0123456789abcdef"},
        }
    }
    assert register_request.json() == {
        "data": {
            "type": "RegisterDevice",
            "attributes": {
                "deviceId": "0123456789abcdef",
                "otp": "123456",
                "modelName": "Home Assistant",
            },
        }
    }
    assert otp_request.headers["Content-Type"] == "application/json"
    assert register_request.headers["Content-Type"] == "application/json"


def test_remote_lock_device_status_and_removal(requests_mock):
    vehicle = _fetch_remote_lock_vehicle(requests_mock)
    status_url = (
        f"{BFF_BASE_URL}v1/users/test-user/vehicles/TEST-VIN/"
        "devices/0123456789abcdef/registration-status"
    )
    delete_url = (
        f"{BFF_BASE_URL}v1/vehicles/TEST-VIN/devices/0123456789abcdef"
    )
    requests_mock.get(status_url, json={})
    requests_mock.delete(delete_url, status_code=204)

    assert vehicle.remote_lock_device_is_registered(
        "0123456789abcdef") is True
    vehicle.unregister_remote_lock_device("0123456789abcdef")

    assert requests_mock.request_history[-1].method == "DELETE"


def test_enroll_remote_lock_pin_waits_for_completion(requests_mock):
    vehicle = _fetch_remote_lock_vehicle(requests_mock)
    enroll_url = (
        "https://alliance-platform-caradapter-prod.apps.eu2.kamereon.io/"
        "car-adapter/v1/cars/TEST-VIN/actions/srp-initiates"
    )
    status_url = (
        "https://alliance-platform-action-status-polling-prod.apps.eu2.kamereon.io/"
        "v1/cars/TEST-VIN/actions/status"
    )
    requests_mock.post(
        enroll_url,
        json={"data": {"type": "SrpInitiates", "id": "enroll-action"}},
    )
    requests_mock.get(
        status_url,
        json={"data": {"attributes": {"status": "COMPLETED"}}},
    )

    with (
        patch(
            "custom_components.nissan_connect.kamereon.kamereon."
            "NissanSRPClient.enroll",
            return_value=("00" * 10, "11" * 256),
        ),
        patch("custom_components.nissan_connect.kamereon.kamereon.time.sleep"),
    ):
        vehicle.enroll_remote_lock_pin("1234")

    enroll_request = next(
        request for request in requests_mock.request_history
        if request.url == enroll_url
    )
    assert enroll_request.json() == {
        "data": {
            "type": "SrpInitiates",
            "attributes": {
                "s": "00" * 10,
                "i": "test-user",
                "v": "11" * 256,
            },
        }
    }
    assert requests_mock.last_request.qs == {"actionid": ["enroll-action"]}


def test_remote_lock_proof_uses_completed_challenge(requests_mock):
    vehicle = _fetch_remote_lock_vehicle(requests_mock)
    challenge_url = (
        "https://alliance-platform-caradapter-prod.apps.eu2.kamereon.io/"
        "car-adapter/v1/cars/TEST-VIN/actions/srp-sets"
    )
    status_url = (
        "https://alliance-platform-action-status-polling-prod.apps.eu2.kamereon.io/"
        "v1/cars/TEST-VIN/actions/status"
    )
    requests_mock.post(
        challenge_url,
        json={"data": {"type": "SrpSets", "id": "challenge-action"}},
    )
    requests_mock.get(
        status_url,
        json={"data": {"attributes": {
            "status": "COMPLETED",
            "data": [
                {"name": "srpLoginS", "value": "00" * 10},
                {"name": "srpLoginB", "value": "22" * 256},
            ],
        }}},
    )
    client = MagicMock()
    client.public_ephemeral.return_value = "11" * 256
    client.proof.return_value = "test-proof"

    with (
        patch(
            "custom_components.nissan_connect.kamereon.kamereon."
            "NissanSRPClient",
            return_value=client,
        ),
        patch("custom_components.nissan_connect.kamereon.kamereon.time.sleep"),
    ):
        proof = vehicle._remote_lock_proof("1234", "lock")

    assert proof == "test-proof"
    client.proof.assert_called_once_with(
        "00" * 10,
        "22" * 256,
        "test-user",
        "1234",
        "TEST-VIN/RLU/Lock",
    )
    client.clear.assert_called_once_with()


def test_remote_lock_rejects_invalid_srp_challenge(requests_mock):
    vehicle = _fetch_remote_lock_vehicle(requests_mock)
    challenge_url = (
        "https://alliance-platform-caradapter-prod.apps.eu2.kamereon.io/"
        "car-adapter/v1/cars/TEST-VIN/actions/srp-sets"
    )
    status_url = (
        "https://alliance-platform-action-status-polling-prod.apps.eu2.kamereon.io/"
        "v1/cars/TEST-VIN/actions/status"
    )
    requests_mock.post(
        challenge_url,
        json={"data": {"type": "SrpSets", "id": "challenge-action"}},
    )
    requests_mock.get(
        status_url,
        json={"data": {"attributes": {
            "status": "COMPLETED",
            "data": [
                {"name": "srpLoginS", "value": "invalid"},
                {"name": "srpLoginB", "value": "22" * 256},
            ],
        }}},
    )

    with (
        patch("custom_components.nissan_connect.kamereon.kamereon.time.sleep"),
        pytest.raises(
            RemoteLockRejected,
            match="SRP challenge is invalid",
        ) as error_info,
    ):
        vehicle._remote_lock_proof("1234", "lock")

    assert error_info.value.__suppress_context__ is True


def test_lock_unlock_sends_device_and_confirms_completion(requests_mock):
    vehicle = _fetch_remote_lock_vehicle(requests_mock)
    command_url = (
        "https://alliance-platform-caradapter-prod.apps.eu2.kamereon.io/"
        "car-adapter/v1/cars/TEST-VIN/actions/lock-unlock"
    )
    status_url = (
        "https://alliance-platform-action-status-polling-prod.apps.eu2.kamereon.io/"
        "v1/cars/TEST-VIN/actions/status"
    )
    requests_mock.post(
        command_url,
        json={"data": {"type": "LockUnlock", "id": "lock-action"}},
    )
    requests_mock.get(
        status_url,
        json={"data": {"attributes": {"status": "COMPLETED"}}},
    )

    with (
        patch.object(vehicle, "_remote_lock_proof", return_value="test-proof"),
        patch("custom_components.nissan_connect.kamereon.kamereon.time.sleep"),
    ):
        vehicle.unlock("1234", "0123456789abcdef")

    command_request = next(
        request for request in requests_mock.request_history
        if request.url == command_url
    )
    assert command_request.json() == {
        "data": {
            "type": "LockUnlock",
            "attributes": {
                "action": "unlock",
                "deviceId": "0123456789abcdef",
                "duration": 0,
                "target": "doors_hatch",
                "srp": "test-proof",
            },
        }
    }
    assert not any(
        "wake-up-vehicle" in request.url
        for request in requests_mock.request_history
    )


def test_lock_unlock_requires_action_id(requests_mock):
    vehicle = _fetch_remote_lock_vehicle(requests_mock)
    command_url = (
        "https://alliance-platform-caradapter-prod.apps.eu2.kamereon.io/"
        "car-adapter/v1/cars/TEST-VIN/actions/lock-unlock"
    )
    requests_mock.post(command_url, json={"data": {"type": "LockUnlock"}})

    with (
        patch.object(vehicle, "_remote_lock_proof", return_value="test-proof"),
        pytest.raises(RemoteLockError, match="no action ID"),
    ):
        vehicle.lock("1234", "0123456789abcdef")


def test_lock_unlock_surfaces_final_rejection(requests_mock):
    vehicle = _fetch_remote_lock_vehicle(requests_mock)
    command_url = (
        "https://alliance-platform-caradapter-prod.apps.eu2.kamereon.io/"
        "car-adapter/v1/cars/TEST-VIN/actions/lock-unlock"
    )
    status_url = (
        "https://alliance-platform-action-status-polling-prod.apps.eu2.kamereon.io/"
        "v1/cars/TEST-VIN/actions/status"
    )
    requests_mock.post(
        command_url,
        json={"data": {"type": "LockUnlock", "id": "lock-action"}},
    )
    requests_mock.get(
        status_url,
        json={"data": {"attributes": {
            "status": "REJECTED",
            "errorCode": "12",
        }}},
    )

    with (
        patch.object(vehicle, "_remote_lock_proof", return_value="test-proof"),
        patch("custom_components.nissan_connect.kamereon.kamereon.time.sleep"),
        pytest.raises(RemoteLockRejected, match=r"REJECTED \(12\)"),
    ):
        vehicle.lock("1234", "0123456789abcdef")


def test_sensitive_remote_lock_post_does_not_follow_redirect(requests_mock):
    vehicle = _fetch_remote_lock_vehicle(requests_mock)
    otp_url = (
        f"{BFF_BASE_URL}v1/users/test-user/vehicles/TEST-VIN/"
        "generate-device-otp"
    )
    external_url = "https://example.invalid/collect"
    requests_mock.post(
        otp_url,
        status_code=307,
        headers={"Location": external_url},
    )

    with pytest.raises(RemoteLockError, match="Unexpected redirect"):
        vehicle.request_remote_lock_otp("0123456789abcdef")

    assert len([request for request in requests_mock.request_history
                if request.url == otp_url]) == 1
    assert all(request.url != external_url
               for request in requests_mock.request_history)


def test_action_polling_tolerates_initial_not_found(requests_mock):
    vehicle = _fetch_remote_lock_vehicle(requests_mock)
    status_url = (
        "https://alliance-platform-action-status-polling-prod.apps.eu2.kamereon.io/"
        "v1/cars/TEST-VIN/actions/status"
    )
    requests_mock.get(status_url, [
        {"status_code": 404},
        {"json": {"data": {"attributes": {"status": "COMPLETED"}}}},
    ])

    with patch("custom_components.nissan_connect.kamereon.kamereon.time.sleep"):
        result = vehicle._wait_for_action(
            "test-action", "test operation", initial_delay=0)

    assert result["status"] == "COMPLETED"
    status_requests = [
        request for request in requests_mock.request_history
        if request.url.startswith(status_url)
    ]
    assert len(status_requests) == 2


@pytest.mark.parametrize("status", ["CANCELLED", "REJECTED", "TIMEOUT"])
def test_action_polling_rejects_unsuccessful_final_states(
        requests_mock, status):
    vehicle = _fetch_remote_lock_vehicle(requests_mock)
    status_url = (
        "https://alliance-platform-action-status-polling-prod.apps.eu2.kamereon.io/"
        "v1/cars/TEST-VIN/actions/status"
    )
    requests_mock.get(
        status_url,
        json={"data": {"attributes": {"status": status}}},
    )

    with pytest.raises(RemoteLockRejected, match=status):
        vehicle._wait_for_action(
            "test-action", "test operation", initial_delay=0)


def test_action_polling_times_out_without_final_state(requests_mock):
    vehicle = _fetch_remote_lock_vehicle(requests_mock)
    status_url = (
        "https://alliance-platform-action-status-polling-prod.apps.eu2.kamereon.io/"
        "v1/cars/TEST-VIN/actions/status"
    )
    requests_mock.get(
        status_url,
        json={"data": {"attributes": {"status": "CREATED"}}},
    )

    with pytest.raises(RemoteLockRejected, match="timed out"):
        vehicle._wait_for_action(
            "test-action",
            "test operation",
            timeout=0,
            interval=0,
            initial_delay=0,
        )


def test_remote_lock_network_failure_is_single_shot_and_redacted(
        requests_mock, caplog):
    vehicle = _fetch_remote_lock_vehicle(requests_mock)
    device_id = "sensitive-device-1234"
    sensitive_error = requests.ConnectionError(
        f"failed for {vehicle.vin}/{device_id}")
    caplog.set_level(
        "DEBUG",
        logger="custom_components.nissan_connect.kamereon.kamereon",
    )

    with (
        patch.object(
            vehicle.session,
            "request",
            side_effect=sensitive_error,
        ) as request,
        pytest.raises(RemoteLockError) as error_info,
    ):
        vehicle.request_remote_lock_otp(device_id)

    request.assert_called_once()
    assert error_info.value.__suppress_context__ is True
    assert vehicle.vin not in str(error_info.value)
    assert device_id not in str(error_info.value)
    assert vehicle.vin not in caplog.text
    assert device_id not in caplog.text
