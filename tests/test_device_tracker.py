import pytest
from unittest.mock import AsyncMock, MagicMock
from homeassistant.components.device_tracker.const import SourceType

from custom_components.nissan_connect.device_tracker import (
    async_setup_entry,
    KamereonDeviceTracker,
)

@pytest.fixture
def mock_hass():
    hass = MagicMock()
    hass.data = {
        'nissan_connect': {
            'test@example.com': {
                'vehicles': {
                    'vehicle_1': MagicMock(features=['MY_CAR_FINDER'], location=(12.34, 56.78)),
                },
                'coordinator_fetch': MagicMock(),
            }
        }
    }
    return hass

@pytest.fixture
def mock_entry():
    return MagicMock(data={'email': 'test@example.com'})

@pytest.fixture
def mock_vehicle():
    return MagicMock(location=(12.34, 56.78))

@pytest.fixture
def mock_coordinator():
    return MagicMock()

def test_kamereon_device_tracker_properties(mock_vehicle, mock_coordinator):
    tracker = KamereonDeviceTracker(mock_coordinator, mock_vehicle)
    
    assert tracker.latitude == 12.34
    assert tracker.longitude == 56.78
    assert tracker.source_type == SourceType.GPS
