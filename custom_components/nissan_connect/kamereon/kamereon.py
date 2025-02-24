# Based on work by @mitchellrj and @Tobiaswk
# Portions re-licensed from Apache License, Version 2.0 with permission

import collections
import datetime
import json
import os
import logging
from typing import List
import requests
import time
from oauthlib.common import generate_nonce
from oauthlib.oauth2 import TokenExpiredError
from requests_oauthlib import OAuth2Session
from .kamereon_const import *

_LOGGER = logging.getLogger(__name__)

_registry = {
    USERS: {},
    VEHICLES: {},
    CATEGORIES: {},
    NOTIFICATION_RULES: {},
    NOTIFICATION_TYPES: {},
    NOTIFICATION_CATEGORIES: {},
}

NotificationType = collections.namedtuple('NotificationType', ['key', 'title', 'message', 'category'])
NotificationCategory = collections.namedtuple('Category', ['key', 'title'])

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
    unique_id = None

    def __init__(self, region, unique_id=None):
        self.settings = SETTINGS_MAP[self.tenant][region]
        session = requests.session()
        self.session = session
        self._oauth = None
        self._user_id = None
        self.unique_id = unique_id
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
            _LOGGER.error("Invalid credentials provided: %s", resp.text)
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
        return self.vin

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
                    _LOGGER.debug(f"Unknown feature {str(u['id'])}")
                    pass
        
        _LOGGER.debug("Active features: %s", self.features)

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
        self.battery_supported = True
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
            ChargingSpeed.ADAPTIVE: None
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

    def _request(self, method, url, headers=None, params=None, data=None, max_retries=3):
        for attempt in range(max_retries):
            try:
                if method == 'GET':
                    resp = self.session.oauth.get(url, headers=headers, params=params)
                elif method == 'POST':
                    resp = self.session.oauth.post(url, data=data, headers=headers)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                # Check for token expiration
                if resp.status_code == 401:
                    raise TokenExpiredError()
                
                # Successful request
                return resp

            except TokenExpiredError:
                _LOGGER.debug("Token expired. Refreshing session and retrying.")
                self.session.login()
            except Exception as e:
                _LOGGER.debug(f"Request failed on attempt {attempt + 1} of {max_retries}: {e}")
                if attempt == max_retries - 1:  # Exhausted retries
                    raise
                time.sleep(2 ** attempt)  # Exponential backoff on retry

        raise RuntimeError("Max retries reached, but the request could not be completed.")

    def _get(self, url, headers=None, params=None):
        return self._request('GET', url, headers=headers, params=params)

    def _post(self, url, data=None, headers=None):
        return self._request('POST', url, headers=headers, data=data)

    def refresh(self):
        self.refresh_location()
        self.refresh_battery_status()

    def fetch_all(self):
        self.fetch_cockpit()
        self.fetch_location()
        self.fetch_battery_status()
        self.fetch_hvac_status()
        self.fetch_lock_status()

    def refresh_location(self):
        if Feature.MY_CAR_FINDER not in self.features:
            return
        
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
        if Feature.MY_CAR_FINDER not in self.features:
            return
        
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
        self.next_target_temperature = hvac_data.get('nextTargetTemperature')
        if 'hvacStatus' in hvac_data:
            self.hvac_status = hvac_data['hvacStatus'] == "on"
        if 'nextHvacStartDate' in hvac_data:
            self.next_hvac_start_date = datetime.datetime.fromisoformat(hvac_data['nextHvacStartDate'].replace('Z','+00:00'))
        if 'lastUpdateTime' in hvac_data:
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
        self.fetch_battery_status_leaf()
        if self.model_name == "Ariya":
            self.fetch_battery_status_ariya()

    def fetch_battery_status_leaf(self):
        """The battery-status endpoint isn't just for EV's. ICE Nissans publish the range under this!
           There is no obvious feature to qualify this, so we just suck it and see."""
        resp = self._get(
            '{}v1/cars/{}/battery-status'.format(self.session.settings['car_adapter_base_url'], self.vin),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        body = resp.json()
        if 'errors' in body and Feature.BATTERY_STATUS in self.features:
            raise ValueError(body['errors'])

        if not 'data' in body or not 'attributes' in body['data']:
            self.battery_supported = False

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
            ChargingSpeed.ADAPTIVE: None
        }
        self.range_hvac_off = battery_data.get('rangeHvacOff')
        self.range_hvac_on = battery_data.get('rangeHvacOn')
        
        # For ICE vehicles, we should get the range at least. If not, dont bother again
        if self.range_hvac_on is None and Feature.BATTERY_STATUS not in self.features:
            self.battery_supported = False
            return

        self.charging = ChargingStatus(battery_data.get('chargeStatus', 0))
        self.plugged_in = PluggedStatus(battery_data.get('plugStatus', 0))
        if 'vehiclePlugTimestamp' in battery_data:
            self.plugged_in_time = datetime.datetime.fromisoformat(battery_data['vehiclePlugTimestamp'].replace('Z','+00:00'))
        if 'vehicleUnplugTimestamp' in battery_data:
            self.unplugged_time = datetime.datetime.fromisoformat(battery_data['vehicleUnplugTimestamp'].replace('Z','+00:00'))
        if 'lastUpdateTime' in battery_data:
            self.battery_status_last_updated = datetime.datetime.fromisoformat(battery_data['lastUpdateTime'].replace('Z','+00:00'))

    def fetch_battery_status_ariya(self):
        resp = self._get(
            '{}v3/cars/{}/battery-status?canGen={}'.format(self.session.settings['user_base_url'], self.vin, self.can_generation),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        body = resp.json()
        if 'errors' in body and Feature.BATTERY_STATUS in self.features:
            raise ValueError(body['errors'])

        if not 'data' in body or not 'attributes' in body['data']:
            self.battery_supported = False

        battery_data = body['data']['attributes']
        
        self.range_hvac_off = None
        self.range_hvac_on = battery_data.get('batteryAutonomy') or self.range_hvac_on

        self.charging_speed = ChargingSpeed(None)
        self.charge_time_required_to_full = {
            ChargingSpeed.FAST: None,
            ChargingSpeed.NORMAL: None,
            ChargingSpeed.SLOW: None,
            ChargingSpeed.ADAPTIVE: battery_data.get('chargingRemainingTime') or self.charge_time_required_to_full[ChargingSpeed.NORMAL]
        }

        self.plugged_in = PluggedStatus(battery_data.get('plugStatus', 0))
                
        if 'vehiclePlugTimestamp' in battery_data:
            self.plugged_in_time = datetime.datetime.fromisoformat(battery_data['vehiclePlugTimestamp'].replace('Z','+00:00'))
        if 'vehicleUnplugTimestamp' in battery_data:
            self.unplugged_time = datetime.datetime.fromisoformat(battery_data['vehicleUnplugTimestamp'].replace('Z','+00:00'))
        if 'lastUpdateTime' in battery_data:
            self.battery_status_last_updated = datetime.datetime.fromisoformat(battery_data['lastUpdateTime'].replace('Z','+00:00'))

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
            end = datetime.datetime.utcnow().date()
            start = end.replace(day=1)
        elif start is None:
            start = datetime.datetime.utcnow().date()
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
