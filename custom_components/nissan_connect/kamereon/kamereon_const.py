import enum

API_VERSION = 'protocol=1.0,resource=2.1'
SRP_KEY = 'D5AF0E14718E662D12DBB4FE42304DF5A8E48359E22261138B40AA16CC85C76A11B43200A1EECB3C9546A262D1FBD51ACE6FCDE558C00665BBF93FF86B9F8F76AA7A53CA74F5B4DFF9A4B847295E7D82450A2078B5A28814A7A07F8BBDD34F8EEB42B0E70499087A242AA2C5BA9513C8F9D35A81B33A121EEF0A71F3F9071CCD'

SETTINGS_MAP = {
    'nissan': {
        'EU': {
            'client_id': 'a-ncb-nc-android-prod',
            'client_secret': '6GKIax7fGT5yPHuNmWNVOc4q5POBw1WRSW39ubRA8WPBmQ7MOxhm75EsmKMKENem',
            'scope': 'openid profile vehicles',
            'auth_base_url': 'https://prod.eu2.auth.kamereon.org/kauth/',
            'realm': 'a-ncb-prod',
            'redirect_uri': 'org.kamereon.service.nci:/oauth2redirect',
            'car_adapter_base_url': 'https://alliance-platform-caradapter-prod.apps.eu2.kamereon.io/car-adapter/',
            'notifications_base_url': 'https://alliance-platform-notifications-prod.apps.eu2.kamereon.io/notifications/',
            'user_adapter_base_url': 'https://alliance-platform-usersadapter-prod.apps.eu2.kamereon.io/user-adapter/',
            'user_base_url': 'https://nci-bff-web-prod.apps.eu2.kamereon.io/bff-web/'
        }
    }
}


USERS = 'users'
VEHICLES = 'vehicles'
CATEGORIES = 'categories'
NOTIFICATION_RULES = 'notification_rules'
NOTIFICATION_TYPES = 'notification_types'
NOTIFICATION_CATEGORIES = 'notification_categories'

class HVACAction(enum.Enum):
    # Start or schedule start
    START = 'start'
    # Stop active HVAC
    STOP = 'stop'
    # Cancel scheduled HVAC
    CANCEL = 'cancel'


class LockStatus(enum.Enum):
    CLOSED = 'closed'
    LOCKED = 'locked'
    OPEN = 'open'
    UNLOCKED = 'unlocked'


class Door(enum.Enum):
    HATCH = 'hatch'
    FRONT_LEFT = 'front_left'
    FRONT_RIGHT = 'front_right'
    REAR_LEFT = 'rear_left'
    REAR_RIGHT = 'rear_right'


class LockableDoorGroup(enum.Enum):
    DOORS_AND_HATCH = 'doors_hatch'
    DRIVERS_DOOR = 'driver_s_door'
    HATCH = 'hatch'


class ChargingSpeed(enum.Enum):
    NONE = None
    SLOW = 1
    NORMAL = 2
    FAST = 3
    FASTEST = 4
    ADAPTIVE = 5


class ChargingStatus(enum.Enum):
    ERROR = -1
    NOT_CHARGING = 0
    CHARGING = 1


class PluggedStatus(enum.Enum):
    ERROR = -1
    NOT_PLUGGED = 0
    PLUGGED = 1


class Period(enum.Enum):
    DAILY = 0
    MONTHLY = 1
    YEARLY = 2


class Feature(enum.Enum):
    BREAKDOWN_ASSISTANCE_CALL = '1'
    SVT_WITH_VEHICLE_BLOCKAGE = '10'
    MAINTENANCE_ALERT = '101'
    VEHICLE_SOFTWARE_UPDATES = '107'
    MY_CAR_FINDER = '12'
    MIL_ON_NOTIFICATION = '15'
    VEHICLE_HEALTH_REPORT = '18'
    ADVANCED_CAN = '201'
    VEHICLE_STATUS_CHECK = '202'
    LOCK_STATUS_CHECK = '2021'
    NAVIGATION_FACTORY_RESET = '208'
    MESSAGES_TO_THE_VEHICLE = '21'
    VEHICLE_DATA = '2121'
    VEHICLE_DATA_2 = '2122'
    VEHICLE_WIFI = '213'
    ADVANCED_VEHICLE_DIAGNOSTICS = '215'
    NAVIGATION_MAP_UPDATES = '217'
    VEHICLE_SETTINGS_TRANSFER = '221'
    LAST_MILE_NAVIGATION = '227'
    GOOGLE_STREET_VIEW = '229'
    GOOGLE_SATELITE_VIEW = '230'
    DYNAMIC_EV_ICE_RANGE = '232'
    ECO_ROUTE_CALCULATION = '233'
    CO_PILOT = '234'
    DRIVING_JOURNEY_HISTORY = '235'
    NISSAN_RENAULT_BROADCASTS = '241'
    ONLINE_PARKING_INFO = '243'
    ONLINE_RESTAURANT_INFO = '244'
    ONLINE_SPEED_RESTRICTION_INFO = '245'
    WEATHER_INFO = '246'
    VEHICLE_ACCESS_TO_EMAIL = '248'
    VEHICLE_ACCESS_TO_MUSIC = '249'
    VEHICLE_ACCESS_TO_CONTACTS = '262'
    APP_DOOR_LOCKING = '27'
    GLONASS = '276'
    ZONE_ALERT = '281'
    SPEEDING_ALERT = '282'
    SERVICE_SUBSCRIPTION = '284'
    PAY_HOW_YOU_DRIVE = '286'
    CHARGING_SPOT_INFO = '288'
    FLEET_ASSET_INFORMATION = '29'
    CHARGING_SPOT_INFO_COLLECTION = '292'
    CHARGING_START = '299'
    CHARGING_STOP = '303'
    INTERIOR_TEMP_SETTINGS = '307'
    CLIMATE_ON_OFF_NOTIFICATION = '311'
    CHARGING_SPOT_SEARCH = '312'
    PLUG_IN_REMINDER = '314'
    CHARGING_STOP_NOTIFICATION = '317'
    BATTERY_STATUS = '319'
    BATTERY_HEATING_NOTIFICATION = '320'
    VEHICLE_STATE_OF_CHARGE_PERCENT = '322'
    BATTERY_STATE_OF_HEALTH_PERCENT = '323'
    PAY_AS_YOU_DRIVE = '34'
    DRIVING_ANALYSIS = '340'
    CO2_GAS_SAVINGS = '341'
    ELECTRICITY_FEE_CALCULATION = '342'
    CHARGING_CONSUMPTION_HISTORY = '344'
    BATTERY_MONITORING = '345'
    BATTERY_DATA = '347'
    APP_BASED_NAVIGATION = '35'
    CHARGING_SPOT_UPDATES = '354'
    RECHARGEABLE_AREA = '358'
    NO_CHARGING_SPOT_INFO = '359'
    EV_RANGE = '360'
    CLIMATE_ON_OFF = '366'
    ONLINE_FUEL_STATION_INFO = '367'
    DESTINATION_SEND_TO_CAR = '37'
    ECALL = '4'
    GOOGLE_PLACES_SEARCH = '40'
    PREMIUM_TRAFFIC = '43'
    AUTO_COLLISION_NOTIFICATION_ACN = '6'
    THEFT_BURGLAR_NOTIFICATION_VEHICLE = '7'
    ECO_CHALLENGE = '721'
    ECO_CHALLENGE_FLEET = '722'
    MOBILE_INFORMATION = '74'
    URL_PRESET_ON_VEHICLE = '77'
    ASSISTED_DESTINATION_SETTING = '78'
    CONCIERGE = '79'
    PERSONAL_DATA_SYNC = '80'
    THEFT_BURGLAR_NOTIFICATION_APP = '87'
    STOLEN_VEHICLE_TRACKING_SVT = '9'
    REMOTE_ENGINE_START = '96'
    HORN_AND_LIGHTS = '97'
    CURFEW_ALERT = '98'
    TEMPERATURE = '2042'
    VALET_PARKING_CALL = '401'
    PANIC_CALL = '406'
    VIRTUAL_PERSONAL_ASSISTANT = '734'
    ALEXA_ONBOARD_ASSISTANT = '736'
    SCHEDULED_ROUTE_CLIMATE_CONTROL = '747'
    SCHEDULED_ROUTE_CALENDAR_INTERGRATION = '819'
    OWNER_MANUAL = '827'


class Language(enum.Enum):
    """The service requires ISO 639-1 language codes to be mapped back
    to ISO 3166-1 country codes. Of course.
    """

    # Bulgarian = Bulgaria
    BG = 'BG'
    # Czech = Czech Republic
    CS = 'CZ'
    # Danish = Denmark
    DA = 'DK'
    # German = Germany
    DE = 'DE'
    # Greek = Greece
    EL = 'GR'
    # Spanish = Spain
    ES = 'ES'
    # Finnish = Finland
    FI = 'FI'
    # French = France
    FR = 'FR'
    # Hebrew = Israel
    HE = 'IL'
    # Croatian = Croatia
    HR = 'HR'
    # Hungarian = Hungary
    HU = 'HU'
    # Italian = Italy
    IT = 'IT'
    # Formal Norwegian = Norway
    NB = 'NO'
    # Dutch = Netherlands
    NL = 'NL'
    # Polish = Poland
    PL = 'PL'
    # Portuguese = Portugal
    PT = 'PT'
    # Romanian = Romania
    RO = 'RO'
    # Russian = Russia
    RU = 'RU'
    # Slovakian = Slovakia
    SK = 'SK'
    # Slovenian = Slovenia
    SI = 'SL'
    # Serbian = Serbia
    SR = 'RS'
    # Swedish = Sweden
    SV = 'SE'
    # Ukranian = Ukraine
    UK = 'UA'
    # Default
    EN = 'EN'


class Order(enum.Enum):
    DESC = 'DESC'
    ASC = 'ASC'


class NotificationCategoryKey(enum.Enum):
    ASSISTANCE = 'assistance'
    CHARGE_EV = 'chargeev'
    CUSTOM = 'custom'
    EV_BATTERY = 'EVBattery'
    FOTA = 'fota'
    GEO_FENCING = 'geofencing'
    MAINTENANCE = 'maintenance'
    NAVIGATION = 'navigation'
    PRIVACY_MODE = 'privacymode'
    REMOTE_CONTROL = 'remotecontrol'
    RESET = 'RESET'
    RGDC = 'rgdcmyze'
    SAFETY_AND_SECURITY = 'Safety&Security'
    SVT = 'SVT'


class NotificationStatus(enum.Enum):
    READ = 'READ'
    UNREAD = 'UNREAD'


class NotificationChannelType(enum.Enum):
    PUSH_APP = 'PUSH_APP'
    MAIL = 'MAIL'
    OFF = ''
    SMS = 'SMS'

class NotificationTypeKey(enum.Enum):
    ABS_ALERT = 'abs.alert'
    AVAILABLE_CHARGING = 'available.charging'
    BADGE_BATTERY_ALERT = 'badge.battery.alert'
    BATTERY_BLOWING_REQUEST = 'battery.blowing.request'
    BATTERY_CHARGE_AVAILABLE = 'battery.charge.available'
    BATTERY_CHARGE_IN_PROGRESS = 'battery.charge.in.progress'
    BATTERY_CHARGE_UNAVAILABLE = 'battery.charge.unavailable'
    BATTERY_COOLING_CONDITIONNING_REQUEST = 'battery.cooling.conditionning.request'
    BATTERY_ENDED_CHARGE = 'battery.ended.charge'
    BATTERY_FLAP_OPENED = 'battery.flap.opened'
    BATTERY_FULL_EXCEPTION = 'battery.full.exception'
    BATTERY_HEATING_CONDITIONNING_REQUEST = 'battery.heating.conditionning.request'
    BATTERY_HEATING_START = 'battery.heating.start'
    BATTERY_HEATING_STOP = 'battery.heating.stop'
    BATTERY_PREHEATING_START = 'battery.preheating.start'
    BATTERY_PREHEATING_STOP = 'battery.preheating.stop'
    BATTERY_SCHEDULE_ISSUE = 'battery.schedule.issue'
    BATTERY_TEMPERATURE_ALERT = 'battery.temperature.alert'
    BATTERY_WAITING_CURRENT_CHARGE = 'battery.waiting.current.charge'
    BATTERY_WAITING_PLANNED_CHARGE = 'battery.waiting.planned.charge'
    BRAKE_ALERT = 'brake.alert'
    BRAKE_SYSTEM_MALFUNCTION = 'brake.system.malfunction'
    BURGLAR_ALARM_LOST = 'burglar.alarm.lost'
    BURGLAR_CAR_STOLEN = 'burglar.car.stolen'
    BURGLAR_TOW_INFO = 'burglar.tow.info'
    CHARGE_FAILURE = 'charge.failure'
    CHARGE_NOT_PROHIBITED = 'charge.not.prohibited'
    CHARGE_PROHIBITED = 'charge.prohibited'
    CHARGING_STOP_GEN3 = 'charging.stop.gen3'
    COOLANT_ALERT = 'coolant.alert'
    CRASH_DETECTION_ALERT = 'crash.detection.alert'
    CURFEW_INFRINGEMENT = 'curfew.infringement'
    CURFEW_RECOVERY = 'curfew.recovery'
    CUSTOM = 'custom'
    DURING_INHIBITED_CHARGING = 'during.inhibited.charging'
    ENGINE_WATER_TEMP_ALERT = 'engine.water.temp.alert'
    EPS_ALERT = 'eps.alert'
    FOTA_CAMPAIGN_AVAILABLE = 'fota.campaign.available'
    FOTA_CAMPAIGN_STATUS_ACTIVATION_COMPLETED = 'fota.campaign.status.activation.completed'
    FOTA_CAMPAIGN_STATUS_ACTIVATION_FAILED = 'fota.campaign.status.activation.failed'
    FOTA_CAMPAIGN_STATUS_ACTIVATION_POSTPONED = 'fota.campaign.status.activation.postponed'
    FOTA_CAMPAIGN_STATUS_ACTIVATION_PROGRESS = 'fota.campaign.status.activation.progress'
    FOTA_CAMPAIGN_STATUS_ACTIVATION_SCHEDULED = 'fota.campaign.status.activation.scheduled'
    FOTA_CAMPAIGN_STATUS_CANCELLED = 'fota.campaign.status.cancelled'
    FOTA_CAMPAIGN_STATUS_CANCELLING = 'fota.campaign.status.cancelling'
    FOTA_CAMPAIGN_STATUS_DOWNLOAD_COMPLETED = 'fota.campaign.status.download.completed'
    FOTA_CAMPAIGN_STATUS_DOWNLOAD_PAUSED = 'fota.campaign.status.download.paused'
    FOTA_CAMPAIGN_STATUS_DOWNLOAD_PROGRESS = 'fota.campaign.status.download.progress'
    FOTA_CAMPAIGN_STATUS_INSTALLATION_COMPLETED = 'fota.campaign.status.installation.completed'
    FOTA_CAMPAIGN_STATUS_INSTALLATION_PROGRESS = 'fota.campaign.status.installation.progress'
    FUEL_ALERT = 'fuel.alert'
    HVAC_AUTOSTART = 'hvac.autostart'
    HVAC_AUTOSTOP = 'hvac.autostop'
    HVAC_TECHNICAL_ISSUE = 'hvac.technical.issue'
    HVAC_TRACTION_BATTERY_LOW = 'hvac.traction.battery.low'
    HVAC_VEHICLE_IN_USE = 'hvac.vehicle.in.use'
    HVAC_VEHICLE_NOT_CONNECTED_POWER = 'hvac.vehicle.not.connected.power'
    LAST_MILE_DESTINATION_ADDRESS = 'last.mile.destination.address'
    LOCK_STATUS_REMINDER = 'lock.status.reminder'
    MAINTENANCE_DISTANCE_PREALERT = 'maintenance.distance.prealert'
    MAINTENANCE_TIME_PREALERT = 'maintenance.time.prealert'
    MIL_LAMP_AUTO_TEST = 'mil.lamp.auto.test'
    MIL_LAMP_FLASH_REQUEST = 'mil.lamp.flash.request'
    MIL_LAMP_OFF_REQUEST = 'mil.lamp.off.request'
    MIL_LAMP_ON_REQUEST = 'mil.lamp.on.request'
    NEXT_CHARGING_INHIBITED = 'next.charging.inhibited'
    OIL_LEVEL_ALERT = 'oil.level.alert'
    OIL_PRESSURE_ALERT = 'oil.pressure.alert'
    OUT_OF_PARK_POSITION_CHARGE_INTERRUPTION = 'out.of.park.position.charge.interruption'
    PLUG_CONNECTION_ISSUE = 'plug.connection.issue'
    PLUG_CONNECTION_SUCCESS = 'plug.connection.success'
    PLUG_UNLOCKING = 'plug.unlocking'
    PREREMINDER_ALERT_DEFAULT = 'prereminder.alert.default'
    PRIVACY_MODE_OFF = 'privacy.mode.off'
    PRIVACY_MODE_ON = 'privacy.mode.on'
    PROGRAMMED_CHARGE_INTERRUPTION = 'programmed.charge.interruption'
    PROHIBITION_BATTERY_RENTAL = 'prohibition.battery.rental'
    PWT_START_IMPOSSIBLE = 'pwt.start.impossible'
    REMOTE_LEFT_TIME_CYCLE = 'remote.left.time.cycle'
    REMOTE_START_CUSTOMER = 'remote.start.customer'
    REMOTE_START_ENGINE = 'remote.start.engine'
    REMOTE_START_NORMAL_ONLY = 'remote.start.normal.only'
    REMOTE_START_PHONE_ERROR = 'remote.start.phone.error'
    REMOTE_START_UNAVAILABLE = 'remote.start.unavailable'
    REMOTE_START_WAIT_PRESOAK = 'remote.start.wait.presoak'
    SERV_WARNING_ALERT = 'serv.warning.alert'
    SPEED_INFRINGEMENT = 'speed.infringement'
    SPEED_RECOVERY = 'speed.recovery'
    START_DRIVING_CHARGE_INTERRUPTION = 'start.driving.charge.interruption'
    START_IN_PROGRESS = 'start.in.progress'
    STATUS_OIL_PRESSURE_SWITCH_CLOSED = 'status.oil.pressure.switch.closed'
    STATUS_OIL_PRESSURE_SWITCH_OPEN = 'status.oil.pressure.switch.open'
    STOP_WARNING_ALERT = 'stop.warning.alert'
    UNPLUG_CHARGE = 'unplug.charge'
    WAITING_PLANNED_CHARGE = 'waiting.planned.charge'
    WHEEL_ALERT = 'wheel.alert'
    ZONE_INFRINGEMENT = 'zone.infringement'
    ZONE_RECOVERY = 'zone.recovery'


class NotificationRuleKey(enum.Enum):
    ABS_ALERT = 'abs.alert'
    AVAILABLE_CHARGING = 'available.charging'
    BADGE_BATTERY_ALERT = 'badge.battery.alert'
    BATTERY_BLOWING_REQUEST = 'battery.blowing.request'
    BATTERY_CHARGE_AVAILABLE = 'battery.charge.available'
    BATTERY_CHARGE_IN_PROGRESS = 'battery.charge.in.progress'
    BATTERY_CHARGE_UNAVAILABLE = 'battery.charge.unavailable'
    BATTERY_COOLING_CONDITIONNING_REQUEST = 'battery.cooling.conditionning.request'
    BATTERY_ENDED_CHARGE = 'battery.ended.charge'
    BATTERY_FLAP_OPENED = 'battery.flap.opened'
    BATTERY_FULL_EXCEPTION = 'battery.full.exception'
    BATTERY_HEATING_CONDITIONNING_REQUEST = 'battery.heating.conditionning.request'
    BATTERY_HEATING_START = 'battery.heating.start'
    BATTERY_HEATING_STOP = 'battery.heating.stop'
    BATTERY_PREHEATING_START = 'battery.preheating.start'
    BATTERY_PREHEATING_STOP = 'battery.preheating.stop'
    BATTERY_SCHEDULE_ISSUE = 'battery.schedule.issue'
    BATTERY_TEMPERATURE_ALERT = 'battery.temperature.alert'
    BATTERY_WAITING_CURRENT_CHARGE = 'battery.waiting.current.charge'
    BATTERY_WAITING_PLANNED_CHARGE = 'battery.waiting.planned.charge'
    BRAKE_ALERT = 'brake.alert'
    BRAKE_SYSTEM_MALFUNCTION = 'brake.system.malfunction'
    BURGLAR_ALARM_LOST = 'burglar.alarm.lost'
    BURGLAR_CAR_STOLEN = 'burglar.car.stolen'
    BURGLAR_TOW_INFO = 'burglar.tow.info'
    BURGLAR_TOW_SYSTEM_FAILURE = 'burglar.tow.system.failure'
    CHARGE_FAILURE = 'charge.failure'
    CHARGE_NOT_PROHIBITED = 'charge.not.prohibited'
    CHARGE_PROHIBITED = 'charge.prohibited'
    CHARGING_STOP_GEN3 = 'charging.stop.gen3'
    COOLANT_ALERT = 'coolant.alert'
    CRASH_DETECTION_ALERT = 'crash.detection.alert'
    CURFEW_INFRINGEMENT = 'curfew.infringement'
    CURFEW_RECOVERY = 'curfew.recovery'
    CUSTOM = 'custom'
    DURING_INHIBITED_CHARGING = 'during.inhibited.charging'
    ENGINE_WATER_TEMP_ALERT = 'engine.water.temp.alert'
    EPS_ALERT = 'eps.alert'
    FOTA_CAMPAIGN_AVAILABLE = 'fota.campaign.available'
    FOTA_CAMPAIGN_STATUS_ACTIVATION_COMPLETED = 'fota.campaign.status.activation.completed'
    FOTA_CAMPAIGN_STATUS_ACTIVATION_FAILED = 'fota.campaign.status.activation.failed'
    FOTA_CAMPAIGN_STATUS_ACTIVATION_POSTPONED = 'fota.campaign.status.activation.postponed'
    FOTA_CAMPAIGN_STATUS_ACTIVATION_PROGRESS = 'fota.campaign.status.activation.progress'
    FOTA_CAMPAIGN_STATUS_ACTIVATION_SCHEDULED = 'fota.campaign.status.activation.scheduled'
    FOTA_CAMPAIGN_STATUS_CANCELLED = 'fota.campaign.status.cancelled'
    FOTA_CAMPAIGN_STATUS_CANCELLING = 'fota.campaign.status.cancelling'
    FOTA_CAMPAIGN_STATUS_DOWNLOAD_COMPLETED = 'fota.campaign.status.download.completed'
    FOTA_CAMPAIGN_STATUS_DOWNLOAD_PAUSED = 'fota.campaign.status.download.paused'
    FOTA_CAMPAIGN_STATUS_DOWNLOAD_PROGRESS = 'fota.campaign.status.download.progress'
    FOTA_CAMPAIGN_STATUS_INSTALLATION_COMPLETED = 'fota.campaign.status.installation.completed'
    FOTA_CAMPAIGN_STATUS_INSTALLATION_PROGRESS = 'fota.campaign.status.installation.progress'
    FUEL_ALERT = 'fuel.alert'
    HVAC_AUTOSTART = 'hvac.autostart'
    HVAC_AUTOSTOP = 'hvac.autostop'
    HVAC_TECHNICAL_ISSUE = 'hvac.technical.issue'
    HVAC_TRACTION_BATTERY_LOW = 'hvac.traction.battery.low'
    HVAC_VEHICLE_IN_USE = 'hvac.vehicle.in.use'
    HVAC_VEHICLE_NOT_CONNECTED_POWER = 'hvac.vehicle.not.connected.power'
    LAST_MILE_DESTINATION_ADDRESS = 'last.mile.destination.address'
    LOCK_STATUS_REMINDER = 'lock.status.reminder'
    MAINTENANCE_DISTANCE_PREALERT = 'maintenance.distance.prealert'
    MAINTENANCE_TIME_PREALERT = 'maintenance.time.prealert'
    MIL_LAMP_AUTO_TEST = 'mil.lamp.auto.test'
    MIL_LAMP_FLASH_REQUEST = 'mil.lamp.flash.request'
    MIL_LAMP_OFF_REQUEST = 'mil.lamp.off.request'
    MIL_LAMP_ON_REQUEST = 'mil.lamp.on.request'
    NEXT_CHARGING_INHIBITED = 'next.charging.inhibited'
    OIL_LEVEL_ALERT = 'oil.level.alert'
    OIL_PRESSURE_ALERT = 'oil.pressure.alert'
    OUT_OF_PARK_POSITION_CHARGE_INTERRUPTION = 'out.of.park.position.charge.interruption'
    PLUG_CONNECTION_ISSUE = 'plug.connection.issue'
    PLUG_CONNECTION_SUCCESS = 'plug.connection.success'
    PLUG_UNLOCKING = 'plug.unlocking'
    PREREMINDER_ALERT_DEFAULT = 'prereminder.alert.default'
    PRIVACY_MODE_OFF = 'privacy.mode.off'
    PRIVACY_MODE_ON = 'privacy.mode.on'
    PROGRAMMED_CHARGE_INTERRUPTION = 'programmed.charge.interruption'
    PROHIBITION_BATTERY_RENTAL = 'prohibition.battery.rental'
    PWT_START_IMPOSSIBLE = 'pwt.start.impossible'
    REMOTE_LEFT_TIME_CYCLE = 'remote.left.time.cycle'
    REMOTE_START_CUSTOMER = 'remote.start.customer'
    REMOTE_START_ENGINE = 'remote.start.engine'
    REMOTE_START_NORMAL_ONLY = 'remote.start.normal.only'
    REMOTE_START_PHONE_ERROR = 'remote.start.phone.error'
    REMOTE_START_UNAVAILABLE = 'remote.start.unavailable'
    REMOTE_START_WAIT_PRESOAK = 'remote.start.wait.presoak'
    RENAULT_RESET_FACTORY = 'renault.reset.factory'
    RGDC_CHARGE_COMPLETE = 'rgdc.charge.complete'
    RGDC_CHARGE_ERROR = 'rgdc.charge.error'
    RGDC_CHARGE_ON = 'rgdc.charge.on'
    RGDC_CHARGE_STATUS = 'rgdc.charge.status'
    RGDC_LOW_BATTERY_ALERT = 'rgdc.low.battery.alert'
    RGDC_LOW_BATTERY_REMINDER = 'rgdc.low.battery.reminder'
    SERV_WARNING_ALERT = 'serv.warning.alert'
    SPEED_INFRINGEMENT = 'speed.infringement'
    SPEED_RECOVERY = 'speed.recovery'
    SRP_PINCODE_ACKNOWLEDGEMENT = 'srp.pincode.acknowledgement'
    SRP_PINCODE_DELETION = 'srp.pincode.deletion'
    SRP_PINCODE_STATUS = 'srp.pincode.status'
    SRP_SALT_REQUEST = 'srp.salt.request'
    START_DRIVING_CHARGE_INTERRUPTION = 'start.driving.charge.interruption'
    START_IN_PROGRESS = 'start.in.progress'
    STATUS_OIL_PRESSURE_SWITCH_CLOSED = 'status.oil.pressure.switch.closed'
    STATUS_OIL_PRESSURE_SWITCH_OPEN = 'status.oil.pressure.switch.open'
    STOLEN_VEHICLE_TRACKING = 'stolen.vehicle.tracking'
    STOLEN_VEHICLE_TRACKING_BLOCKING = 'stolen.vehicle.tracking.blocking'
    STOP_WARNING_ALERT = 'stop.warning.alert'
    SVT_SERVICE_ACTIVATION = 'svt.service.activation'
    UNPLUG_CHARGE = 'unplug.charge'
    WAITING_PLANNED_CHARGE = 'waiting.planned.charge'
    WHEEL_ALERT = 'wheel.alert'
    ZONE_INFRINGEMENT = 'zone.infringement'
    ZONE_RECOVERY = 'zone.recovery'


class NotificationPriority(enum.Enum):

    NONE = None
    P0 = 0
    P1 = 1
    P2 = 2
    P3 = 3


class NotificationRuleStatus(enum.Enum):
    ACTIVATED = 'ACTIVATED'
    ACTIVATION_IN_PROGRESS = 'STATUS_ACTIVATION_IN_PROGRESS'
    DELETION_IN_PROGRESS = 'STATUS_DELETION_IN_PROGRESS'
