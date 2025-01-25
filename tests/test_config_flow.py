"""Tests for the config flow."""
from unittest import mock
import pytest

from custom_components.nissan_connect import config_flow
from custom_components.nissan_connect.const import DOMAIN
from homeassistant import data_entry_flow
from custom_components.nissan_connect.const import DOMAIN, DEFAULT_REGION

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

    assert result["type"] == data_entry_flow.RESULT_TYPE_CREATE_ENTRY
    assert result["title"] == "test@example.com"
    assert result["data"] == {
        "email": "test@example.com",
        "password": "password123",
        "region": DEFAULT_REGION,
        "imperial_distance": False
    }

async def test_step_user_invalid_auth(hass, mock_kamereon_session):
    """Test the user step with invalid credentials."""
    mock_kamereon_session.return_value.login.side_effect = Exception("Invalid credentials")

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

    assert result["type"] == data_entry_flow.RESULT_TYPE_FORM
    assert result["errors"] == {"base": "auth_error"}
