# Copyright 2020 Richard Mitchell

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import collections
import datetime
import enum
import json
import os
import requests
import logging
from typing import List
from oauthlib.common import generate_nonce
from oauthlib.oauth2 import TokenExpiredError
from requests_oauthlib import OAuth2Session

_LOGGER = logging.getLogger(__name__)

API_VERSION = 'protocol=1.0,resource=2.1'
SRP_KEY = 'D5AF0E14718E662D12DBB4FE42304DF5A8E48359E22261138B40AA16CC85C76A11B43200A1EECB3C9546A262D1FBD51ACE6FCDE558C00665BBF93FF86B9F8F76AA7A53CA74F5B4DFF9A4B847295E7D82450A2078B5A28814A7A07F8BBDD34F8EEB42B0E70499087A242AA2C5BA9513C8F9D35A81B33A121EEF0A71F3F9071CCD'


settings_map = {
    'nissan': {
        'EU': {
            'client_id': 'a-ncb-prod-android',
            'client_secret': '0sAcrtwvwEXXZp5nzQhPexSRhxUVKa0d76F4uqDvxvvKFHXpo4myoJwUuV4vuNqC',
            'scope': 'openid profile vehicles',
            'auth_base_url': 'https://prod.eu2.auth.kamereon.org/kauth/',
            'realm': 'a-ncb-prod',
            'redirect_uri': 'org.kamereon.service.nci:/oauth2redirect',
            'car_adapter_base_url': 'https://alliance-platform-caradapter-prod.apps.eu2.kamereon.io/car-adapter/',
            'notifications_base_url': 'https://alliance-platform-notifications-prod.apps.eu2.kamereon.io/notifications/',
            'user_adapter_base_url': 'https://alliance-platform-usersadapter-prod.apps.eu2.kamereon.io/user-adapter/',
            'user_base_url': 'https://nci-bff-web-prod.apps.eu2.kamereon.io/bff-web/',
        },
        'US': {
            'client_id': 'a-ncb-prod-android',
            'client_secret': '0sAcrtwvwEXXZp5nzQhPexSRhxUVKa0d76F4uqDvxvvKFHXpo4myoJwUuV4vuNqC',
            'scope': 'openid profile vehicles',
            'auth_base_url': 'https://prod.eu2.auth.kamereon.org/kauth/',
            'realm': 'a-ncb-prod',
            'redirect_uri': 'org.kamereon.service.nci:/oauth2redirect',
            'car_adapter_base_url': 'https://alliance-platform-caradapter-prod.apps.eu2.kamereon.io/car-adapter/',
            'notifications_base_url': 'https://alliance-platform-notifications-prod.apps.eu2.kamereon.io/notifications/',
            'user_adapter_base_url': 'https://alliance-platform-usersadapter-prod.apps.eu2.kamereon.io/user-adapter/',
            'user_base_url': 'https://nci-bff-web-prod.apps.eu2.kamereon.io/bff-web/',
        }
    },
    'mitsubishi': {},
    'renault': {},
}


USERS = 'users'
VEHICLES = 'vehicles'
CATEGORIES = 'categories'
NOTIFICATION_RULES = 'notification_rules'
NOTIFICATION_TYPES = 'notification_types'
NOTIFICATION_CATEGORIES = 'notification_categories'
_registry = {
    USERS: {},
    VEHICLES: {},
    CATEGORIES: {},
    NOTIFICATION_RULES: {},
    NOTIFICATION_TYPES: {},
    NOTIFICATION_CATEGORIES: {},
}


class HVACAction(enum.Enum):
    # Start or schedule start
    START = 'start'
    # Stop active HVAC
    STOP = 'stop'
    # Cancel scheduled HVAC
    CANCEL = 'cancel'


class HVACStatus(enum.Enum):
    OFF = 'off'
    ON = 'on'


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


NotificationType = collections.namedtuple('NotificationType', ['key', 'title', 'message', 'category'])
NotificationCategory = collections.namedtuple('Category', ['key', 'title'])


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


class Notification:

    @property
    def vehicle(self):
        return _registry[VEHICLES][self.vin]

    @property
    def user_id(self):
        return self.vehicle.user_id

    @property
    def session(self):
        return self.vehicle.session

    def __init__(self, data, language, vin):
        self.language = language
        self.vin = vin
        self.id = data['notificationId']
        self.title = data['messageTitle']
        self.subtitle = data['messageSubtitle']
        self.description = data['messageDescription']
        self.category = NotificationCategoryKey(data['categoryKey'])
        self.rule_key = NotificationRuleKey(data['ruleKey'])
        self.notification_key = NotificationTypeKey(data['notificationKey'])
        self.priority = NotificationPriority(data['priority'])
        self.state = NotificationStatus(data['status'])
        t = datetime.datetime.strptime(data['timestamp'].split('.')[0], '%Y-%m-%dT%H:%M:%S')
        if '.' in data['timestamp']:
            fraction = data['timestamp'][20:-1]
            t = t.replace(microsecond=int(fraction) * 10**(6-len(fraction)))
        self.time = t
        # List of {'name': 'N', 'type': 'T', 'value': 'V'}
        self.data = data['data']
        # future use maybe? empty dict
        self.metadata = data['metadata']

    def __str__(self):
        # title is kinda useless, subtitle has better content
        return '{}: {}'.format(self.time, self.subtitle)

    def fetch_details(self, language: Language=None):
        if language is None:
            language = self.language
        resp = self._get(
            '{}v2/notifications/users/{}/vehicles/{}/notifications/{}'.format(
                self.session.settings['notifications_base_url'],
                self.user_id, self.vin, self.id
            ),
            params={'langCode': language.value}
        )
        return resp


class KamereonSession:

    tenant = None
    copy_realm = None

    def __init__(self, region):
        self.settings = settings_map[self.tenant][region]
        session = requests.session()
        self.session = session
        self._oauth = None
        self._user_id = None
        # ugly hack
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

    def login(self, username=None, password=None):
        if username is not None and password is not None:
            # Cache credentials
            self._username = username
            self._password = password
        else:
            # Use cached credentials
            username = self._username
            password = self._password
        
        # Reset session
        self.session = requests.session()

        # grab an auth ID to use as part of the username/password login request,
        # then move to the regular OAuth2 process
        auth_url = '{}json/realms/root/realms/{}/authenticate'.format(
            self.settings['auth_base_url'],
            self.settings['realm'],
        )
        resp = self.session.post(
            auth_url,
            headers={
                'Accept-Api-Version': API_VERSION,
                'X-Username': 'anonymous',
                'X-Password': 'anonymous',
                'Accept': 'application/json',
            })
        next_body = resp.json()

        # insert the username, and password
        for c in next_body['callbacks']:
            input_type = c['type']
            if input_type == 'NameCallback':
                c['input'][0]['value'] = username
            elif input_type == 'PasswordCallback':
                c['input'][0]['value'] = password

        resp = self.session.post(
            auth_url,
            headers={
                'Accept-Api-Version': API_VERSION,
                'X-Username': 'anonymous',
                'X-Password': 'anonymous',
                'Accept': 'application/json',
                'Content-Type': 'application/json',
            },
            data=json.dumps(next_body))

        oauth_data = resp.json()

        if 'realm' not in oauth_data:
            raise RuntimeError("Invalid credentials")
        
        oauth_authorize_url = '{}oauth2{}/authorize'.format(
            self.settings['auth_base_url'],
            oauth_data['realm']
            )
        nonce = generate_nonce()
        resp = self.session.get(
            oauth_authorize_url,
            params={
                'client_id': self.settings['client_id'],
                'redirect_uri': self.settings['redirect_uri'],
                'response_type': 'code',
                'scope': self.settings['scope'],
                'nonce': nonce,
            },
            allow_redirects=False)
        oauth_authorize_url = resp.headers['location']

        oauth_token_url = '{}oauth2{}/access_token'.format(
            self.settings['auth_base_url'],
            oauth_data['realm']
            )
        self._oauth = OAuth2Session(
            client_id=self.settings['client_id'],
            redirect_uri=self.settings['redirect_uri'],
            scope=self.settings['scope'])
        self._oauth._client.nonce = nonce
        self._oauth.fetch_token(
            oauth_token_url,
            authorization_response=oauth_authorize_url,
            client_secret=self.settings['client_secret'],
            include_client_id=True)

    @property
    def oauth(self):
        if self._oauth is None:
            raise RuntimeError('No access token set, you need to log in first.')
        return self._oauth

    @property
    def user_id(self):
        if not self._user_id:
            resp = self.oauth.get(
                '{}v1/users/current'.format(self.settings['user_adapter_base_url'])
            )
            self._user_id = resp.json()['userId']
            _registry[USERS][self._user_id] = self
        return self._user_id

    def fetch_vehicles(self):
        resp = self.oauth.get(
            '{}v5/users/{}/cars'.format(self.settings['user_base_url'], self.user_id)
        )
        vehicles = []
        for vehicle_data in resp.json()['data']:
            vehicle = Vehicle(vehicle_data, self.user_id)
            vehicles.append(vehicle)
            _registry[VEHICLES][vehicle.vin] = vehicle
        return vehicles


class NCISession(KamereonSession):

    tenant = 'nissan'
    copy_realm = 'P_NCB'


class Vehicle:

    def __repr__(self):
        return '<{} {}>'.format(self.__class__.__name__, self.vin)

    def __str__(self):
        return self.nickname or self.vin

    @property
    def session(self):
        return _registry[USERS][self.user_id]

    def __init__(self, data, user_id):
        self.user_id = user_id
        self.vin = data['vin'].upper()
        self.features = []

        # Try to parse every feature, but dont fail if we dont recognise one
        for u in data.get('services', []):
            if u['activationState'] == "ACTIVATED":
                try:
                    self.features.append(Feature(str(u['id'])))
                except ValueError:
                    pass
        
        _LOGGER.debug(f"Active features: {self.features}")

        self.can_generation = data.get('canGeneration')
        self.color = data.get('color')
        self.energy = data.get('energy')
        self.vehicle_gateway = data.get('carGateway')
        self.battery_code = data.get('batteryCode')
        self.engine_type = data.get('engineType')
        self.first_registration_date = data.get('firstRegistrationDate')
        self.ice_or_ev = data.get('iceEvFlag')
        self.model_name = data.get('modelName')
        self.model_code = data.get('modelCode')
        self.model_year = data.get('modelYear')
        self.nickname = data.get('nickname')
        self.phase = data.get('phase')
        self.picture_url = data.get('pictureURL')
        self.privacy_mode = data.get('privacyMode')
        self.registration_number = data.get('registrationNumber')
        self.battery_capacity = None
        self.battery_level = None
        self.battery_temperature = None
        self.battery_bar_level = None
        self.instantaneous_power = None
        self.charging_speed = None
        self.charge_time_required_to_full = {
            ChargingSpeed.FAST: None,
            ChargingSpeed.NORMAL: None,
            ChargingSpeed.SLOW: None,
        }
        self.range_hvac_off = None
        self.range_hvac_on = None
        self.charging = ChargingStatus.NOT_CHARGING
        self.plugged_in = PluggedStatus.NOT_PLUGGED
        self.plugged_in_time = None
        self.unplugged_time = None
        self.battery_status_last_updated = None
        self.location = None
        self.location_last_updated = None
        self.combustion_fuel_unit_cost = None
        self.electricity_unit_cost = None
        self.external_temperature = None
        self.internal_temperature = None
        self.hvac_status = None
        self.next_hvac_start_date = None
        self.next_target_temperature = None
        self.hvac_status_last_updated = None
        self.door_status = {
            Door.FRONT_LEFT: None,
            Door.FRONT_RIGHT: None,
            Door.REAR_LEFT: None,
            Door.REAR_RIGHT: None,
            Door.HATCH: None
        }
        self.lock_status = None
        self.lock_status_last_updated = None
        self.eco_score = None
        self.fuel_autonomy = None
        self.fuel_consumption = None
        self.fuel_economy = None
        self.fuel_level = None
        self.fuel_low_warning = None
        self.fuel_quantity = None
        self.mileage = None
        self.total_mileage = None

    def _get(self, url, headers=None, params=None):
        """Try logging in again before returning a failure."""
        expired = False
        try:
            resp = self.session.oauth.get(url, headers=headers, params=params)
        except TokenExpiredError:
            expired = True

        if expired or resp.status_code == 401:
            _LOGGER.debug("Refreshing session and retrying request as token expired")
            self.session.login()
            return self.session.oauth.get(url, headers=headers, params=params)
        
        return resp

    def _post(self, url, data=None, headers=None):
        """Try logging in again before returning a failure."""
        expired = False
        try:
            resp = self.session.oauth.post(url, data=data, headers=headers)
        except TokenExpiredError:
            expired = True

        if expired or resp.status_code == 401:
            _LOGGER.debug("Refreshing session and retrying request as token expired")
            self.session.login()
            return self.session.oauth.post(url, data=data, headers=headers)
        
        return resp

    def refresh(self):
        self.refresh_location()
        self.refresh_battery_status()
        self.fetch_all()

    def fetch_all(self):
        self.fetch_cockpit()
        self.fetch_location()
        self.fetch_battery_status()
        self.fetch_energy_unit_cost()
        self.fetch_hvac_status()
        self.fetch_lock_status()

    def refresh_location(self):
        resp = self._post(
            '{}v1/cars/{}/actions/refresh-location'.format(self.session.settings['car_adapter_base_url'], self.vin),
            data=json.dumps({
                'data': {'type': 'RefreshLocation'}
            }),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        body = resp.json()
        if 'errors' in body:
            raise ValueError(body['errors'])
        return body

    def fetch_location(self):
        resp = self._get(
            '{}v1/cars/{}/location'.format(self.session.settings['car_adapter_base_url'], self.vin),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        body = resp.json()
        if 'errors' in body:
            raise ValueError(body['errors'])
        location_data = body['data']['attributes']
        self.location = (location_data['gpsLatitude'], location_data['gpsLongitude'])
        self.location_last_updated = datetime.datetime.fromisoformat(location_data['lastUpdateTime'].replace('Z','+00:00'))

    def refresh_lock_status(self):
        resp = self._post(
            '{}v1/cars/{}/actions/refresh-lock-status'.format(self.session.settings['car_adapter_base_url'], self.vin),
            data=json.dumps({
                'data': {'type': 'RefreshLockStatus'}
            }),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        body = resp.json()
        if 'errors' in body:
            raise ValueError(body['errors'])
        return body

    def fetch_lock_status(self):
        if Feature.LOCK_STATUS_CHECK not in self.features:
            return
        resp = self._get(
            '{}v1/cars/{}/lock-status'.format(self.session.settings['car_adapter_base_url'], self.vin),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        body = resp.json()
        if 'errors' in body:
            raise ValueError(body['errors'])
        lock_data = body['data']['attributes']
        self.door_status[Door.FRONT_LEFT] = LockStatus(lock_data.get('doorStatusFrontLeft', LockStatus.CLOSED))
        self.door_status[Door.FRONT_RIGHT] = LockStatus(lock_data.get('doorStatusFrontRight', LockStatus.CLOSED))
        self.door_status[Door.REAR_LEFT] = LockStatus(lock_data.get('doorStatusRearLeft', LockStatus.CLOSED))
        self.door_status[Door.REAR_RIGHT] = LockStatus(lock_data.get('doorStatusRearRight', LockStatus.CLOSED))
        self.door_status[Door.HATCH] = LockStatus(lock_data.get('hatchStatus', LockStatus.CLOSED))
        self.lock_status = LockStatus(lock_data.get('lockStatus', LockStatus.LOCKED))
        self.lock_status_last_updated = datetime.datetime.fromisoformat(lock_data['lastUpdateTime'].replace('Z','+00:00'))

    def refresh_hvac_status(self):
        resp = self._post(
            '{}v1/cars/{}/actions/refresh-hvac-status'.format(self.session.settings['car_adapter_base_url'], self.vin),
            data=json.dumps({
                'data': {'type': 'RefreshHvacStatus'}
            }),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        body = resp.json()
        if 'errors' in body:
            raise ValueError(body['errors'])
        return body

    def initiate_srp(self):
        (salt, verifier) = SRP.enroll(self.user_id, self.vin)
        resp = self._post(
            '{}v1/cars/{}/actions/srp-initiates'.format(self.session.settings['car_adapter_base_url'], self.vin),
            data=json.dumps({
                "data": {
                    "type": "SrpInitiates",
                    "attributes": {
                        "s": salt,
                        "i": self.user_id,
                        "v": verifier
                    }
                }
            }),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        body = resp.json()
        if 'errors' in body:
            raise ValueError(body['errors'])
        return body

    def validate_srp(self):
        a = SRP.generate_a()
        resp = self._post(
            '{}v1/cars/{}/actions/srp-sets'.format(self.session.settings['car_adapter_base_url'], self.vin),
            data=json.dumps({
                "data": {
                    "type": "SrpSets",
                    "attributes": {
                        "i": self.user_id,
                        "a": a
                    }
                }
            }),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        body = resp.json()
        if 'errors' in body:
            raise ValueError(body['errors'])
        return body

    """
    Other vehicle controls to implement / investigate:
        DataReset
        DeleteCurfewRestrictions
        CreateCurfewRestrictions
        CreateSpeedRestrictions
        SrpInitiates
        DeleteAreaRestrictions
        SrpDelete
        SrpSets
        OpenClose
        EngineStart
        LockUnlock
        CreateAreaRestrictions
        DeleteSpeedRestrictions
    """

    def control_charging(self, action: str, srp: str=None):
        assert action in ('stop', 'start')
        if action == 'start' and Feature.CHARGING_START not in self.features:
            return
        if action == 'stop' and Feature.CHARGING_STOP not in self.features:
            return
        attributes = {
            'action': action,
        }
        if srp is not None:
            attributes['srp'] = srp
        resp = self._post(
            '{}v1/cars/{}/actions/charging-start'.format(self.session.settings['car_adapter_base_url'], self.vin),
            data=json.dumps({
                'data': {
                    'type': 'ChargingStart',
                    'attributes': attributes
                }
            }),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        body = resp.json()
        if 'errors' in body:
            raise ValueError(body['errors'])
        return body

    def control_horn_lights(self, action: str, target: str, duration: int=5, srp: str=None):
        if Feature.HORN_AND_LIGHTS not in self.features:
            return
        assert target in ('horn_lights', 'lights', 'horn')
        assert action in ('stop', 'start', 'double_start')
        attributes = {
            'action': action,
            'duration': duration,
            'target': target,
        }
        if srp is not None:
            attributes['srp'] = srp
        resp = self._post(
            '{}v1/cars/{}/actions/horn-lights'.format(self.session.settings['car_adapter_base_url'], self.vin),
            data=json.dumps({
                'data': {
                    'type': 'HornLights',
                    'attributes': attributes
                }
            }),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        body = resp.json()
        if 'errors' in body:
            raise ValueError(body['errors'])
        return body

    def set_hvac_status(self, action: HVACAction, target_temperature: int=21, start: datetime.datetime=None, srp: str=None):
        if Feature.CLIMATE_ON_OFF not in self.features:
            return

        if target_temperature < 16 or target_temperature > 26:
            raise ValueError('Temperature must be between 16 & 26 degrees')

        attributes = {
            'action': action.value
        }
        if action == HVACAction.START:
            attributes['targetTemperature'] = target_temperature
        if start is not None:
            attributes['startDateTime'] = start.isoformat(timespec='seconds')
        if srp is not None:
            attributes['srp'] = srp

        resp = self._post(
            '{}v1/cars/{}/actions/hvac-start'.format(self.session.settings['car_adapter_base_url'], self.vin),
            data=json.dumps({
                'data': {
                    'type': 'HvacStart',
                    'attributes': attributes
                }
            }),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        body = resp.json()
        if 'errors' in body:
            raise ValueError(body['errors'])
        return body

    def lock_unlock(self, srp: str, action: str, group: LockableDoorGroup=None):
        if Feature.APP_DOOR_LOCKING not in self.features:
            return
        assert action in ('lock', 'unlock')
        if group is None:
            group = LockableDoorGroup.DOORS_AND_HATCH
        resp = self._post(
            '{}v1/cars/{}/actions/lock-unlock"'.format(self.session.settings['car_adapter_base_url'], self.vin),
            data=json.dumps({
                'data': {
                    'type': 'LockUnlock',
                    'attributes': {
                        'lock': action,
                        'doorType': group.value,
                        'srp': srp
                    }
                }
            }),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        body = resp.json()
        if 'errors' in body:
            raise ValueError(body['errors'])
        return body

    def lock(self, srp: str, group: LockableDoorGroup=None):
        return self.lock_unlock(srp, 'lock', group)

    def unlock(self, srp: str, group: LockableDoorGroup=None):
        return self.lock_unlock(srp, 'unlock', group)

    def fetch_hvac_status(self):
        if Feature.INTERIOR_TEMP_SETTINGS not in self.features and Feature.TEMPERATURE not in self.features:
            return
        
        resp = self._get(
            '{}v1/cars/{}/hvac-status'.format(self.session.settings['car_adapter_base_url'], self.vin),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        body = resp.json()
        if 'errors' in body:
            raise ValueError(body['errors'])
        hvac_data = body['data']['attributes']
        self.external_temperature = hvac_data.get('externalTemperature')
        self.internal_temperature = hvac_data.get('internalTemperature')
        if 'hvacStatus' in hvac_data:
            self.hvac_status = HVACStatus(hvac_data['hvacStatus'])
        if 'nextHvacStartDate' in hvac_data:
            self.next_hvac_start_date = datetime.datetime.fromisoformat(hvac_data['nextHvacStartDate'].replace('Z','+00:00'))
        self.next_target_temperature = hvac_data.get('nextTargetTemperature')
        self.hvac_status_last_updated = datetime.datetime.fromisoformat(hvac_data['lastUpdateTime'].replace('Z','+00:00'))

    def refresh_battery_status(self):
        resp = self._post(
            '{}v1/cars/{}/actions/refresh-battery-status'.format(self.session.settings['car_adapter_base_url'], self.vin),
            data=json.dumps({
                'data': {'type': 'RefreshBatteryStatus'}
            }),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        body = resp.json()
        if 'errors' in body:
            raise ValueError(body['errors'])
        return body

    def fetch_battery_status(self):
        if Feature.DRIVING_JOURNEY_HISTORY not in self.features:
            return
        resp = self._get(
            '{}v1/cars/{}/battery-status'.format(self.session.settings['car_adapter_base_url'], self.vin),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        body = resp.json()
        if 'errors' in body:
            raise ValueError(body['errors'])
        battery_data = body['data']['attributes']
        self.battery_capacity = battery_data.get('batteryCapacity')  # kWh
        self.battery_level = battery_data.get('batteryLevel')  # %
        self.battery_temperature = battery_data.get('batteryTemperature')  # Fahrenheit?
        # same meaning as battery level, different scale. 240 = 100%
        self.battery_bar_level = battery_data.get('batteryBarLevel')
        self.instantaneous_power = battery_data.get('instantaneousPower')  # kW
        self.charging_speed = ChargingSpeed(battery_data.get('chargePower'))
        self.charge_time_required_to_full = {
            ChargingSpeed.FAST: battery_data.get('timeRequiredToFullFast'),
            ChargingSpeed.NORMAL: battery_data.get('timeRequiredToFullNormal'),
            ChargingSpeed.SLOW: battery_data.get('timeRequiredToFullSlow'),
        }
        self.range_hvac_off = battery_data.get('rangeHvacOff')
        self.range_hvac_on = battery_data.get('rangeHvacOn')
        self.charging = ChargingStatus(battery_data.get('chargeStatus', 0))
        self.plugged_in = PluggedStatus(battery_data.get('plugStatus', 0))
        if 'vehiclePlugTimestamp' in battery_data:
            self.plugged_in_time = datetime.datetime.fromisoformat(battery_data['vehiclePlugTimestamp'].replace('Z','+00:00'))
        if 'vehicleUnplugTimestamp' in battery_data:
            self.unplugged_time = datetime.datetime.fromisoformat(battery_data['vehicleUnplugTimestamp'].replace('Z','+00:00'))
        if 'lastUpdateTime' in battery_data:
            self.battery_status_last_updated = datetime.datetime.fromisoformat(battery_data['lastUpdateTime'].replace('Z','+00:00'))

    def fetch_energy_unit_cost(self):
        resp = self._get(
            '{}v1/cars/{}/energy-unit-cost'.format(self.session.settings['car_adapter_base_url'], self.vin)
        )
        body = resp.json()
        if 'errors' in body:
            raise ValueError(body['errors'])
        energy_cost_data = body['data']['attributes']
        self.electricity_unit_cost = energy_cost_data.get('electricityUnitCost')
        self.combustion_fuel_unit_cost = energy_cost_data.get('fuelUnitCost')
        return body

    def set_energy_unit_cost(self, cost):
        resp = self._post(
            '{}v1/cars/{}/energy-unit-cost'.format(self.session.settings['car_adapter_base_url'], self.vin),
            data=json.dumps({
                'data': {
                    'type': {}
                }
            })
        )
        body = resp.json()
        if 'errors' in body:
            raise ValueError(body['errors'])

    def fetch_trip_histories(self, period: Period=None, start: datetime.date=None, end: datetime.date=None):
        if period is None:
            period = Period.DAILY
        if start is None and end is None and period == Period.MONTHLY:
            end = datetime.date.today()
            start = end.replace(day=1)
        elif start is None:
            start = datetime.date.today()
        if end is None:
            end = start
        resp = self._get(
            '{}v1/cars/{}/trip-history'.format(self.session.settings['car_adapter_base_url'], self.vin),
            params={
                'type': period.value,
                'start': start.isoformat(),
                'end': end.isoformat()
            }
        )
        body = resp.json()
        if 'errors' in body:
            raise ValueError(body['errors'])
        return [TripSummary(s, self.vin) for s in body['data']['attributes']['summaries']]

    def fetch_notifications(
            self,
            language: Language=None,
            category_key: NotificationCategoryKey=None,
            status: NotificationStatus=None,
            start: datetime.datetime=None,
            end: datetime.datetime=None,
            # offset
            from_: int=1,
            # limit
            to: int=20,
            order: Order=None
            ):

        if language is None:
            language = Language.EN
        params = {
            'realm': self.session.copy_realm,
            'langCode': language.value,
        }
        if category_key is not None:
            params['categoryKey'] = category_key.value
        if status is not None:
            params['status'] = status.value
        if start is not None:
            params['start'] = start.isoformat(timespec='seconds')
            if start.tzinfo is None:
                # Assume UTC
                params['start'] += 'Z'
        if end is not None:
            params['end'] = start.isoformat(timespec='seconds')
            if end.tzinfo is None:
                # Assume UTC
                params['end'] += 'Z'
        resp = self._get(
            '{}v2/notifications/users/{}/vehicles/{}'.format(self.session.settings['notifications_base_url'], self.user_id, self.vin),
            params=params
        )
        body = resp.json()
        if 'errors' in body:
            raise ValueError(body['errors'])
        return [Notification(m, language, self.vin) for m in body['data']['attributes']['messages']]

    def mark_notifications(self, messages: List[Notification]):
        """Take a list of notifications and set their status remotely
        to the one held locally (read / unread)."""

        resp = self._post(
            '{}v2/notifications/users/{}/vehicles/{}'.format(self.session.settings['notifications_base_url'], self.user_id, self.vin),
            data=json.dumps([
                {'notificationId': m.id, 'status': m.status.value}
                for m in messages
            ])
        )
        body = resp.json()
        if 'errors' in body:
            raise ValueError(body['errors'])
        return body

    def fetch_notification_settings(self, language: Language=None):
        if language is None:
            language = Language.EN
        params = {
            'langCode': language.value,
        }
        resp = self._get(
            '{}v1/rules/settings/users/{}/vehicles/{}'.format(self.session.settings['notifications_base_url'], self.user_id, self.vin),
            params=params
        )
        body = resp.json()
        if 'errors' in body:
            raise ValueError(body['errors'])
        return [
            NotificationRule(r, language, self.vin)
            for r in body['settings']
        ]

    def update_notification_settings(self):
        # TODO
        pass

    def fetch_cockpit(self):
        resp = self._get(
            "{}v1/cars/{}/cockpit".format(self.session.settings['car_adapter_base_url'], self.vin)
        )
        body = resp.json()
        if 'errors' in body:
            raise ValueError(body['errors'])

        cockpit_data = body['data']['attributes']
        self.eco_score = cockpit_data.get('ecoScore')
        self.fuel_autonomy = cockpit_data.get('fuelAutonomy')
        self.fuel_consumption = cockpit_data.get('fuelConsumption')
        self.fuel_economy = cockpit_data.get('fuelEconomy')
        self.fuel_level = cockpit_data.get('fuelLevel')
        if 'fuelLowWarning' in cockpit_data:
            self.fuel_low_warning = bool(cockpit_data.get('fuelLowWarning', False))
        self.fuel_quantity = cockpit_data.get('fuelQuantity')  # litres
        self.mileage = cockpit_data.get('mileage')
        self.total_mileage = cockpit_data.get('totalMileage')


class TripSummary:

    def __init__(self, data, vin):
        self.vin = vin
        self.trip_count = data['tripsNumber']
        self.total_distance = data['distance']  # km
        self.total_duration = data['duration']  # minutes
        self.first_trip_start = datetime.datetime.fromisoformat(data['firstTripStart'].replace('Z','+00:00'))
        self.last_trip_end = datetime.datetime.fromisoformat(data['lastTripEnd'].replace('Z','+00:00'))
        self.consumed_fuel = data['consumedFuel']  # litres
        self.consumed_electricity = data['consumedElectricity']  # W
        self.saved_electricity = data['savedElectricity']  # W
        if 'day' in data:
            self.start = self.end = datetime.date(int(data['day'][:4]), int(data['day'][4:6]), int(data['day'][6:]))
        elif 'month' in data:
            start_year = int(data['month'][:4])
            start_month = int(data['month'][4:])
            end_month = start_month + 1
            end_year = start_year
            if end_month > 12:
                end_month = 1
                end_year = end_year + 1
            self.start = datetime.date(start_year, start_month, 1)
            self.end = datetime.date(end_year, end_month, 1) - datetime.timedelta(days=1)
        elif 'year' in data:
            self.start = datetime.date(int(data['year']), 1, 1)
            self.end = datetime.date(int(data['year']) + 1, 1, 1) - datetime.timedelta(days=1)

    def __str__(self):
        return '{} trips covering {} kilometres over {} minutes using {} litres fuel and {} kilowatt-hours electricity'.format(
            self.trip_count, self.total_distance, self.total_duration, self.consumed_fuel, self.consumed_electricity
        )


class NotificationRule:

    def __init__(self, data, language, vin):
        self.vin = vin
        self.language = language
        self.key = NotificationRuleKey(data['ruleKey'])
        self.title = data['ruleTitle']
        self.description = data['ruleDescription']
        self.priority = NotificationPriority(data['priority'])
        self.status = NotificationRuleStatus(data['status'])
        self.channels = [
            NotificationChannelType(c['channelType'])
            for c in data['channels']
        ]
        self.category = NotificationCategory(NotificationCategoryKey(data['categoryKey']), data['categoryTitle'])
        self.notification_type = None
        if 'notificationKey' in data:
            self.notification_type = NotificationType(
                NotificationTypeKey(data['notificationKey']),
                data['notificationTitle'],
                data['notificationMessage'],
                self.category,
                )
    
    def __str__(self):
        return '{}: {} ({})'.format(
            self.title or self.key,
            self.status.value,
            ', '.join(c.value for c in self.channels)
        )


class SRP:

    @classmethod
    def enroll(cls, user_id, vin):
        salt, verifier = '0'*20, 'ABCDEFGH'*64
        # salt = 20 hex chars, verifier = 512 hex chars
        return (salt, verifier)

    @classmethod
    def generate_a(cls):
        # 512 hex chars
        return ''

    @classmethod
    def generate_proof(cls, salt, b, user_id, confirm_code, order):
        """Required for remote lock / unlock."""
        # order = '<VIN>/<PERMISSIONS>'
        # where PERMISSIONS is one of:
        # * "BCI/Block"
        # * "BCI/Unblock"
        # * "RC/Delayed"
        # * "RC/Start"
        # * "RC/Stop"
        # * "RES/DoubleStart"
        # * "RES/Start"
        # * "RES/Stop"
        # * "RHL/Start/HornOnly"
        # * "RHL/Start/HornLight"
        # * "RHL/Start/LightOnly"
        # * "RHL/Stop"
        # * "RLU/Lock"
        # * "RLU/Unlock"
        # * "RPC_ICE/Start"
        # * "RPC_ICE/Stop"
        # * "RPU_CCS/Disable"
        # * "RPU_CCS/Enable"
        # * "RPU_SVTB/Disable"
        # * "RPU_SVTB/Enable"
        pass



if __name__ == '__main__':
    import pprint
    import sys

    region = sys.argv[1]
    username = sys.argv[2]
    password = sys.argv[3]
    if len(sys.argv) > 4:
        srp = sys.argv[4]

    nci = NCISession(region)
    nci.login(username, password)
    user_id = nci.get_user_id()
    vehicles = nci.fetch_vehicles()
    for vehicle in vehicles:
        vehicle.fetch_cockpit()
        vehicle.fetch_all()
        pprint.pprint(vars(vehicle))
        print('today trip summary')
        trip_summaries = vehicle.fetch_trip_histories()
        print('\n'.join(map(str, trip_summaries)))
        print('last notifications')
        notifications = vehicle.fetch_notifications()
        print('\n'.join(map(str, notifications)))
        notifications[0].fetch_details()
    
