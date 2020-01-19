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

import datetime
import enum
import json
import os
from urllib.parse import urljoin, urlparse, parse_qs

from oauthlib.common import generate_nonce
import requests
from requests_oauthlib import OAuth2Session


API_VERSION = 'protocol=1.0,resource=2.1'


settings_map = {
    'nissan': {
        'EU': {
            'client_id': 'a-ncb-prod-android',
            'client_secret': '3LBs0yOx2XO-3m4mMRW27rKeJzskhfWF0A8KUtnim8i/qYQPl8ZItp3IaqJXaYj_',
            'scope': 'openid profile vehicles',
            'auth_base_url': 'https://prod.eu.auth.kamereon.org/kauth/',
            'realm': 'a-ncb-prod',
            'redirect_uri': 'org.kamereon.service.nci:/oauth2redirect',
            'car_adapter_base_url': 'https://alliance-platform-caradapter-prod.apps.eu.kamereon.io/car-adapter/',
            'user_adapter_base_url': 'https://alliance-platform-usersadapter-prod.apps.eu.kamereon.io/user-adapter/',
            'user_base_url': 'https://nci-bff-web-prod.apps.eu.kamereon.io/bff-web/',
        },
        'JP': {},
        'RU': {},
    },
    'mitsubishi': {},
    'renault': {},
}


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
    FRONT_LEFT = 'front-left'
    FRONT_RIGHT = 'front-right'
    REAR_LEFT = 'rear-left'
    REAR_RIGHT = 'rear-right'


class ChargingSpeed(enum.Enum):
    NONE = None
    SLOW = 1
    NORMAL = 2
    FAST = 3


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


class Kamereon:

    def __init__(self, territory):
        self.settings = settings_map[self.tenant][territory]
        self._oauth = None
        # ugly hack
        os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'

    def login(self, username, password):
        # grab an auth ID to use as part of the username/password login request,
        # then move to the regular OAuth2 process
        session = requests.session()
        auth_url = '{}json/realms/root/realms/{}/authenticate'.format(
            self.settings['auth_base_url'],
            self.settings['realm'],
        )
        resp = session.post(
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

        resp = session.post(
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
        #self._access_token = oauth_data['tokenId']
        
        oauth_authorize_url = '{}oauth2{}/authorize'.format(
            self.settings['auth_base_url'],
            oauth_data['realm']
            )
        nonce = generate_nonce()
        resp = session.get(
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

    def get_user_id(self):
        resp = self.oauth.get(
            '{}v1/users/current'.format(self.settings['user_adapter_base_url'])
        )
        return resp.json()['userId']

    def get_cars(self, user_id):
        resp = self.oauth.get(
            '{}v2/users/{}/cars'.format(self.settings['user_base_url'], user_id)
        )
        return [
            Vehicle(v, self) for v in resp.json()['data']
        ]


class NCI(Kamereon):

    tenant = 'nissan'


class Vehicle:

    def __repr__(self):
        return '<{} {}>'.format(self.__class__.__name__, self.vin)

    def __str__(self):
        return self.nickname or self.vin

    def __init__(self, data, connection):
        self.connection = connection
        self.vin = data.get('vin')
        self.features = [
            Feature(u['name'])
            for u in data.get('uids', [])
            if u['enabled']]
        self.can_generation = data.get('canGeneration')
        self.color = data.get('color')
        self.energy = data.get('energy')
        self.vehicle_gateway = data.get('carGateway')
        self.battery_code = data.get('batteryCode')
        self.engine_type = data.get('engineType')
        self.first_registration_date = data.get('firstRegistrationDate')
        self.ice_or_ev = data.get('iceEvFlag')
        self.model_name = data.get('modelName')
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

    def refresh(self):
        self.refresh_location()
        self.refresh_battery_status()

    def fetch_all(self):
        self.fetch_location()
        self.fetch_battery_status()
        self.fetch_energy_unit_cost()
        self.fetch_hvac_status()
        self.fetch_lock_status()

    def refresh_location(self):
        resp = self.connection.oauth.post(
            '{}v1/cars/{}/actions/refresh-location'.format(self.connection.settings['car_adapter_base_url'], self.vin),
            data=json.dumps({
                'data': {'type': 'RefreshLocation'}
            }),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        return resp.json()

    def fetch_location(self):
        resp = self.connection.oauth.get(
            '{}v1/cars/{}/location'.format(self.connection.settings['car_adapter_base_url'], self.vin),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        location_data = resp.json()['data']['attributes']
        self.location = (location_data['gpsLatitude'], location_data['gpsLongitude'])
        self.location_last_updated = datetime.datetime.fromisoformat(location_data['lastUpdateTime'].replace('Z','+00:00'))

    def refresh_lock_status(self):
        resp = self.connection.oauth.post(
            '{}v1/cars/{}/actions/refresh-lock-status'.format(self.connection.settings['car_adapter_base_url'], self.vin),
            data=json.dumps({
                'data': {'type': 'RefreshLockStatus'}
            }),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        return resp.json()

    def fetch_lock_status(self):
        if Feature.LOCK_STATUS_CHECK not in self.features:
            return
        resp = self.connection.oauth.get(
            '{}v1/cars/{}/lock-status'.format(self.connection.settings['car_adapter_base_url'], self.vin),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        lock_data = resp.json()['data']['attributes']
        self.door_status[Door.FRONT_LEFT] = LockStatus(lock_data['doorStatusFrontLeft'])
        self.door_status[Door.FRONT_RIGHT] = LockStatus(lock_data['doorStatusFrontRight'])
        self.door_status[Door.REAR_LEFT] = LockStatus(lock_data['doorStatusRearLeft'])
        self.door_status[Door.REAR_RIGHT] = LockStatus(lock_data['doorStatusRearRight'])
        self.door_status[Door.HATCH] = LockStatus(lock_data['hatchStatus'])
        self.lock_status = LockStatus(lock_data['lockStatus'])
        self.lock_status_last_updated = datetime.datetime.fromisoformat(location_data['lastUpdateTime'].replace('Z','+00:00'))

    def refresh_hvac_status(self):
        resp = self.connection.oauth.post(
            '{}v1/cars/{}/actions/refresh-hvac-status'.format(self.connection.settings['car_adapter_base_url'], self.vin),
            data=json.dumps({
                'data': {'type': 'RefreshHvacStatus'}
            }),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        return resp.json()

    def fetch_hvac_status(self):
        resp = self.connection.oauth.get(
            '{}v1/cars/{}/hvac-status'.format(self.connection.settings['car_adapter_base_url'], self.vin),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        hvac_data = resp.json()['data']['attributes']
        self.external_temperature = hvac_data.get('externalTemperature')
        self.internal_temperature = hvac_data.get('internalTemperature')
        if 'hvacStatus' in hvac_data:
            self.hvac_status = HVACStatus(hvac_data['hvacStatus'])
        if 'nextHvacStartDate' in hvac_data:
            self.next_hvac_start_date = datetime.datetime.fromisoformat(hvac_data['nextHvacStartDate'].replace('Z','+00:00'))
        self.next_target_temperature = hvac_data.get('nextTargetTemperature')
        self.hvac_status_last_updated = datetime.datetime.fromisoformat(hvac_data['lastUpdateTime'].replace('Z','+00:00'))

    def refresh_battery_status(self):
        resp = self.connection.oauth.post(
            '{}v1/cars/{}/actions/refresh-battery-status'.format(self.connection.settings['car_adapter_base_url'], self.vin),
            data=json.dumps({
                'data': {'type': 'RefreshBatteryStatus'}
            }),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        return resp.json()

    def fetch_battery_status(self):
        if Feature.BATTERY_STATUS not in self.features:
            return
        resp = self.connection.oauth.get(
            '{}v1/cars/{}/battery-status'.format(self.connection.settings['car_adapter_base_url'], self.vin),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        battery_data = resp.json()['data']['attributes']
        self.battery_capacity = battery_data['batteryCapacity']  # kWh
        self.battery_level = battery_data['batteryLevel']  # %
        self.battery_temperature = battery_data.get('batteryTemperature')  # Fahrenheit?
        # same meaning as battery level, different scale. 240 = 100%
        self.battery_bar_level = battery_data['batteryBarLevel']
        self.instantaneous_power = battery_data.get('instantaneousPower')  # kW
        self.charging_speed = ChargingSpeed(battery_data.get('chargePower'))
        self.charge_time_required_to_full = {
            ChargingSpeed.FAST: battery_data['timeRequiredToFullFast'],
            ChargingSpeed.NORMAL: battery_data['timeRequiredToFullNormal'],
            ChargingSpeed.SLOW: battery_data['timeRequiredToFullSlow'],
        }
        self.range_hvac_off = battery_data['rangeHvacOff']
        self.range_hvac_on = battery_data['rangeHvacOn']
        self.charging = ChargingStatus(battery_data['chargeStatus'])
        self.plugged_in = PluggedStatus(battery_data['plugStatus'])
        if 'vehiclePlugTimestamp' in battery_data:
            self.plugged_in_time = datetime.datetime.fromisoformat(battery_data['vehiclePlugTimestamp'].replace('Z','+00:00'))
        if 'vehicleUnplugTimestamp' in battery_data:
            self.unplugged_time = datetime.datetime.fromisoformat(battery_data['vehicleUnplugTimestamp'].replace('Z','+00:00'))
        self.battery_status_last_updated = datetime.datetime.fromisoformat(battery_data['lastUpdateTime'].replace('Z','+00:00'))

    def fetch_trip_histories(self, period, start, end):
        resp = self.connection.oauth.get(
            '{}v1/cars/{}/trip-history'.format(self.connection.settings['car_adapter_base_url'], self.vin),
            params={
                'type': period.value,
                'start': start.isoformat(),
                'end': end.isoformat()
            }
        )
        return map(TripSummary, resp.json()['data']['attributes']['summaries'])

    def fetch_energy_unit_cost(self):
        resp = self.connection.oauth.get(
            '{}v1/cars/{}/energy-unit-cost'.format(self.connection.settings['car_adapter_base_url'], self.vin)
        )
        energy_cost_data = resp.json()['data']['attributes']
        self.electricity_unit_cost = energy_cost_data.get('electricityUnitCost')
        self.combustion_fuel_unit_cost = energy_cost_data.get('fuelUnitCost')
        return resp.json()

    def set_energy_unit_cost(self, cost):
        resp = self.connection.oauth.post(
            '{}v1/cars/{}/energy-unit-cost'.format(self.connection.settings['car_adapter_base_url'], self.vin),
            data=json.dumps({
                'data': {
                    'type': {}
                }
            })
        )


class TripSummary:

    def __init__(self, data):
        self.trip_count = data['tripsNumber']
        self.total_distance_km = data['distance']  # km
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
            self.end = datetime.date(end_year, end_month) - datetime.timedelta(days=1)
        elif 'year' in data:
            self.start = datetime.date(int(data['year']), 1, 1)
            self.end = datetime.date(int(data['year']) + 1, 1, 1) - datetime.timedelta(days=1)



if __name__ == '__main__':
    import pprint
    import sys

    nci = NCI(sys.argv[1])
    nci.login(sys.argv[2], sys.argv[3])
    user_id = nci.get_user_id()
    cars = nci.get_cars(user_id)
    for car in cars:
        car.fetch_all()
        car.fetch_trip_histories(Period.DAILY, datetime.date(2020, 1, 1), datetime.date(2020, 1, 7))
        pprint.pprint(vars(car))
    
