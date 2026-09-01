DOMAIN = "nissan_connect"
CONFIG_VERSION = 2
ENTITY_TYPES = [
    "binary_sensor",
    "sensor",
    "button",
    "climate",
    "device_tracker",
    "lock",
]

CONF_REMOTE_LOCK = "remote_lock"
CONF_REMOTE_LOCK_DEVICE_ID = "device_id"
CONF_REMOTE_LOCK_STATUS = "status"

REMOTE_LOCK_STATUS_REGISTERED = "registered"
REMOTE_LOCK_STATUS_CONFIGURED = "configured"
REMOTE_LOCK_STATUS_ENABLED = "enabled"
REMOTE_LOCK_STATUS_UNREGISTERED = "unregistered"

DATA_VEHICLES = "vehicles"
DATA_REMOTE_LOCK_CONFIG = "remote_lock_config"
DATA_COORDINATOR_FETCH = "coordinator_fetch"
DATA_COORDINATOR_POLL = "coordinator_poll"
DATA_COORDINATOR_STATISTICS = "coordinator_statistics"

DEFAULT_INTERVAL_POLL = 0
DEFAULT_INTERVAL_CHARGING = 15
DEFAULT_INTERVAL_STATISTICS = 60

DEFAULT_INTERVAL_FETCH = 10

DEFAULT_REGION = "EU"
REGIONS = ["EU"]
