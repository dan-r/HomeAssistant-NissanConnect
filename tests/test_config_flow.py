"""Tests for the config flow."""
from unittest import mock
import pytest

from custom_components.nissan_connect import config_flow
from pytest_homeassistant_custom_component.common import MockConfigEntry
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant import data_entry_flow
from custom_components.nissan_connect.const import DOMAIN, DEFAULT_REGION
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
