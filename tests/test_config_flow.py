"""Tests for the config flow."""
from unittest import mock
import pytest

from custom_components.nissan_connect import config_flow
from pytest_homeassistant_custom_component.common import MockConfigEntry
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant import data_entry_flow
from custom_components.nissan_connect.const import (
    CONF_REMOTE_LOCK,
    CONF_REMOTE_LOCK_DEVICE_ID,
    CONF_REMOTE_LOCK_STATUS,
    DEFAULT_INTERVAL_CHARGING,
    DEFAULT_INTERVAL_FETCH,
    DEFAULT_INTERVAL_POLL,
    DEFAULT_INTERVAL_STATISTICS,
    DEFAULT_REGION,
    DOMAIN,
    REMOTE_LOCK_STATUS_ENABLED,
    REMOTE_LOCK_STATUS_REGISTERED,
    REMOTE_LOCK_STATUS_UNREGISTERED,
)
from custom_components.nissan_connect.kamereon import NissanAuthError

@pytest.fixture
def mock_kamereon_session():
    with mock.patch("custom_components.nissan_connect.config_flow.NCISession") as mock_session:
        yield mock_session

async def test_step_account(hass):
    """Test the initialization of the form in the first step of the config flow."""
    result = await hass.config_entries.flow.async_init(
        config_flow.DOMAIN, context={"source": "user"}
    )
    
    expected = {
        'type': 'form',
        'flow_id': mock.ANY,
        'handler': DOMAIN,
        'step_id': 'user',
        'data_schema': config_flow.USER_SCHEMA,
        'errors': {},
        'description_placeholders': None,
        'last_step': None,
        'preview': None
    }

    assert expected == result

async def test_step_user_init(hass):
    """Test the initialization of the form in the first step of the config flow."""
    result = await hass.config_entries.flow.async_init(
        config_flow.DOMAIN, context={"source": "user"}
    )
    
    expected = {
        'type': 'form',
        'flow_id': mock.ANY,
        'handler': DOMAIN,
        'step_id': 'user',
        'data_schema': config_flow.USER_SCHEMA,
        'errors': {},
        'description_placeholders': None,
        'last_step': None,
        'preview': None
    }

    assert expected == result

async def test_step_user_submit(hass, mock_kamereon_session):
    """Test the user step with valid credentials."""
    mock_kamereon_session.return_value.login.return_value = True

    result = await hass.config_entries.flow.async_init(
        config_flow.DOMAIN, context={"source": "user"}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "email": "test@example.com",
            "password": "password123",
            "region": DEFAULT_REGION.lower(),
            "imperial_distance": False
        }
    )

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert result["title"] == "test@example.com"
    assert result["data"] == {
        "email": "test@example.com",
        "password": "password123",
        "region": DEFAULT_REGION,
        "imperial_distance": False
    }
    mock_kamereon_session.assert_called_once_with(region=DEFAULT_REGION)
    mock_kamereon_session.return_value.login.assert_called_once_with(
        "test@example.com",
        "password123",
    )

async def test_step_user_invalid_auth(hass, mock_kamereon_session):
    """Test the user step with invalid credentials."""
    mock_kamereon_session.return_value.login.side_effect = NissanAuthError(
        "Invalid credentials"
    )

    result = await hass.config_entries.flow.async_init(
        config_flow.DOMAIN, context={"source": "user"}
    )

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "email": "test@example.com",
            "password": "wrongpassword",
            "region": DEFAULT_REGION.lower(),
            "imperial_distance": False
        }
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "auth_error"}


async def test_reauth_updates_password(hass, mock_kamereon_session):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="test@example.com",
        data={
            "email": "test@example.com",
            "password": "old-password",
            "region": DEFAULT_REGION,
            "imperial_distance": False,
        },
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    with mock.patch.object(
        hass.config_entries,
        "async_reload",
        new=mock.AsyncMock(return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"password": "new-password"},
        )
        await hass.async_block_till_done()

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["password"] == "new-password"
    mock_kamereon_session.return_value.login.assert_called_once_with(
        "test@example.com",
        "new-password",
    )


async def test_reauth_reports_connection_error_separately(
        hass, mock_kamereon_session):
    """A network blip must not tell the user their password is wrong."""
    mock_kamereon_session.return_value.login.side_effect = RuntimeError(
        "Unable to contact Nissan login"
    )
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="test@example.com",
        data={
            "email": "test@example.com",
            "password": "old-password",
            "region": DEFAULT_REGION,
        },
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"password": "new-password"},
    )

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}
    assert entry.data["password"] == "old-password"


def _options_input(**values):
    return {
        "interval": DEFAULT_INTERVAL_POLL,
        "interval_charging": DEFAULT_INTERVAL_CHARGING,
        "interval_fetch": DEFAULT_INTERVAL_FETCH,
        "interval_statistics": DEFAULT_INTERVAL_STATISTICS,
        "configure_remote_lock": True,
        **values,
    }


async def test_remote_lock_setup_is_per_vehicle_and_does_not_store_pin(
        hass, mock_kamereon_session):
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="test@example.com",
        data={
            "email": "test@example.com",
            "password": "test-password",
            "region": DEFAULT_REGION,
        },
    )
    entry.add_to_hass(hass)
    first_vehicle = mock.MagicMock(
        vin="FIRST-VIN",
        nickname="First",
        model_name="Leaf",
        supports_remote_lock_setup=True,
    )
    second_vehicle = mock.MagicMock(
        vin="SECOND-VIN",
        nickname="Second",
        model_name="Ariya",
        supports_remote_lock_setup=True,
    )
    mock_kamereon_session.return_value.fetch_vehicles.return_value = [
        first_vehicle,
        second_vehicle,
    ]

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _options_input())

    assert result["type"] == data_entry_flow.FlowResultType.FORM
    assert result["step_id"] == "remote_lock_vehicle"

    with mock.patch(
        "custom_components.nissan_connect.config_flow.secrets.token_hex",
        return_value="0123456789abcdef0123456789abcdef",
    ):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"vehicle": "SECOND-VIN"})

    assert result["step_id"] == "remote_lock_otp"
    second_vehicle.request_remote_lock_otp.assert_called_once_with(
        "0123456789abcdef0123456789abcdef")
    first_vehicle.request_remote_lock_otp.assert_not_called()

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"otp": "123456"})

    assert result["step_id"] == "remote_lock_pin"
    second_vehicle.register_remote_lock_device.assert_called_once_with(
        "0123456789abcdef0123456789abcdef", "123456")
    assert entry.data[CONF_REMOTE_LOCK]["SECOND-VIN"] == {
        CONF_REMOTE_LOCK_DEVICE_ID:
            "0123456789abcdef0123456789abcdef",
        CONF_REMOTE_LOCK_STATUS: REMOTE_LOCK_STATUS_REGISTERED,
    }

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"pin": "1234", "pin_confirm": "1234"})

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    second_vehicle.enroll_remote_lock_pin.assert_called_once_with("1234")
    assert entry.data[CONF_REMOTE_LOCK]["SECOND-VIN"] == {
        CONF_REMOTE_LOCK_DEVICE_ID:
            "0123456789abcdef0123456789abcdef",
        CONF_REMOTE_LOCK_STATUS: REMOTE_LOCK_STATUS_ENABLED,
    }
    assert "pin" not in str(entry.data.keys()).lower()
    assert "pin" not in str(
        entry.data[CONF_REMOTE_LOCK]["SECOND-VIN"].keys()).lower()


async def test_remote_lock_setup_validates_otp_and_pin(
        hass, mock_kamereon_session):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "email": "test@example.com",
            "password": "test-password",
            "region": DEFAULT_REGION,
        },
    )
    entry.add_to_hass(hass)
    vehicle = mock.MagicMock(
        vin="TEST-VIN",
        nickname="Leaf",
        model_name="Leaf",
        supports_remote_lock_setup=True,
    )
    mock_kamereon_session.return_value.fetch_vehicles.return_value = [vehicle]

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _options_input())
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"vehicle": "TEST-VIN"})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"otp": "12345x"})

    assert result["step_id"] == "remote_lock_otp"
    assert result["errors"] == {"otp": "otp_invalid"}
    vehicle.register_remote_lock_device.assert_not_called()

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"otp": "123456"})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"pin": "1234", "pin_confirm": "4321"})

    assert result["step_id"] == "remote_lock_pin"
    assert result["errors"] == {"pin_confirm": "pin_mismatch"}
    vehicle.enroll_remote_lock_pin.assert_not_called()


async def test_remote_lock_setup_resumes_after_device_registration(
        hass, mock_kamereon_session):
    device_id = "0123456789abcdef0123456789abcdef"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "email": "test@example.com",
            "password": "test-password",
            "region": DEFAULT_REGION,
            CONF_REMOTE_LOCK: {
                "TEST-VIN": {
                    CONF_REMOTE_LOCK_DEVICE_ID: device_id,
                    CONF_REMOTE_LOCK_STATUS:
                        REMOTE_LOCK_STATUS_REGISTERED,
                }
            },
        },
    )
    entry.add_to_hass(hass)
    vehicle = mock.MagicMock(
        vin="TEST-VIN",
        nickname="Leaf",
        model_name="Leaf",
        supports_remote_lock_setup=True,
    )
    vehicle.remote_lock_device_is_registered.return_value = True
    mock_kamereon_session.return_value.fetch_vehicles.return_value = [vehicle]

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _options_input())
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"vehicle": "TEST-VIN"})

    assert result["step_id"] == "remote_lock_pin"
    vehicle.remote_lock_device_is_registered.assert_called_once_with(device_id)
    vehicle.request_remote_lock_otp.assert_not_called()


async def test_remote_lock_setup_aborts_without_supported_vehicle(
        hass, mock_kamereon_session):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "email": "test@example.com",
            "password": "test-password",
            "region": DEFAULT_REGION,
        },
    )
    entry.add_to_hass(hass)
    mock_kamereon_session.return_value.fetch_vehicles.return_value = [
        mock.MagicMock(supports_remote_lock_setup=False)
    ]

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _options_input())

    assert result["type"] == data_entry_flow.FlowResultType.ABORT
    assert result["reason"] == "no_remote_lock_vehicle"


@pytest.mark.parametrize(
    "initial_status, action, final_status",
    [
        (REMOTE_LOCK_STATUS_ENABLED, "disable", "configured"),
        ("configured", "enable", REMOTE_LOCK_STATUS_ENABLED),
    ],
)
async def test_remote_lock_can_be_enabled_or_disabled(
        hass, mock_kamereon_session, initial_status, action, final_status):
    device_id = "0123456789abcdef0123456789abcdef"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "email": "test@example.com",
            "password": "test-password",
            "region": DEFAULT_REGION,
            CONF_REMOTE_LOCK: {
                "TEST-VIN": {
                    CONF_REMOTE_LOCK_DEVICE_ID: device_id,
                    CONF_REMOTE_LOCK_STATUS: initial_status,
                }
            },
        },
    )
    entry.add_to_hass(hass)
    vehicle = mock.MagicMock(
        vin="TEST-VIN",
        nickname="Leaf",
        model_name="Leaf",
        supports_remote_lock_setup=True,
    )
    mock_kamereon_session.return_value.fetch_vehicles.return_value = [vehicle]

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _options_input())
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"vehicle": "TEST-VIN"})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"action": action})

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    assert entry.data[CONF_REMOTE_LOCK]["TEST-VIN"] == {
        CONF_REMOTE_LOCK_DEVICE_ID: device_id,
        CONF_REMOTE_LOCK_STATUS: final_status,
    }


async def test_remote_lock_pin_can_be_updated_without_being_stored(
        hass, mock_kamereon_session):
    device_id = "0123456789abcdef0123456789abcdef"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "email": "test@example.com",
            "password": "test-password",
            "region": DEFAULT_REGION,
            CONF_REMOTE_LOCK: {
                "TEST-VIN": {
                    CONF_REMOTE_LOCK_DEVICE_ID: device_id,
                    CONF_REMOTE_LOCK_STATUS: REMOTE_LOCK_STATUS_ENABLED,
                }
            },
        },
    )
    entry.add_to_hass(hass)
    vehicle = mock.MagicMock(
        vin="TEST-VIN",
        nickname="Leaf",
        model_name="Leaf",
        supports_remote_lock_setup=True,
    )
    mock_kamereon_session.return_value.fetch_vehicles.return_value = [vehicle]

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _options_input())
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"vehicle": "TEST-VIN"})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"action": "update_pin"})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"pin": "5678", "pin_confirm": "5678"})

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    vehicle.enroll_remote_lock_pin.assert_called_once_with("5678")
    assert entry.data[CONF_REMOTE_LOCK]["TEST-VIN"] == {
        CONF_REMOTE_LOCK_DEVICE_ID: device_id,
        CONF_REMOTE_LOCK_STATUS: REMOTE_LOCK_STATUS_ENABLED,
    }


async def test_remote_lock_device_can_be_removed_and_id_is_preserved(
        hass, mock_kamereon_session):
    device_id = "0123456789abcdef0123456789abcdef"
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            "email": "test@example.com",
            "password": "test-password",
            "region": DEFAULT_REGION,
            CONF_REMOTE_LOCK: {
                "TEST-VIN": {
                    CONF_REMOTE_LOCK_DEVICE_ID: device_id,
                    CONF_REMOTE_LOCK_STATUS: REMOTE_LOCK_STATUS_ENABLED,
                }
            },
        },
    )
    entry.add_to_hass(hass)
    vehicle = mock.MagicMock(
        vin="TEST-VIN",
        nickname="Leaf",
        model_name="Leaf",
        supports_remote_lock_setup=True,
    )
    mock_kamereon_session.return_value.fetch_vehicles.return_value = [vehicle]

    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _options_input())
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"vehicle": "TEST-VIN"})
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"action": "remove_device"})

    assert result["type"] == data_entry_flow.FlowResultType.CREATE_ENTRY
    vehicle.unregister_remote_lock_device.assert_called_once_with(device_id)
    assert entry.data[CONF_REMOTE_LOCK]["TEST-VIN"] == {
        CONF_REMOTE_LOCK_DEVICE_ID: device_id,
        CONF_REMOTE_LOCK_STATUS: REMOTE_LOCK_STATUS_UNREGISTERED,
    }
