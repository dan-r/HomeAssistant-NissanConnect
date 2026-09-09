# Based on work by @mitchellrj and @Tobiaswk
# Portions re-licensed from Apache License, Version 2.0 with permission

import base64
import collections
import datetime
import hashlib
from html.parser import HTMLParser
import json
import logging
import secrets
import threading
from typing import List
from urllib.parse import parse_qs, urljoin, urlparse
import requests
import time
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


class _LoginFormParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.forms = []
        self._form = None

    def handle_starttag(self, tag, attrs):
        attributes = dict(attrs)
        if tag == 'form':
            self._form = {
                'action': attributes.get('action'),
                'method': attributes.get('method', 'get').lower(),
                'inputs': {}
            }
        elif tag == 'input' and self._form is not None:
            name = attributes.get('name')
            if name:
                self._form['inputs'][name] = attributes.get('value', '')

    def handle_endtag(self, tag):
        if tag == 'form' and self._form is not None:
            self.forms.append(self._form)
            self._form = None

    @property
    def login_form(self):
        for form in self.forms:
            inputs = form['inputs']
            if 'sessionDataKey' in inputs and 'password' in inputs:
                return form
        return None

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


class NissanAuthError(RuntimeError):
    """Raised when Nissan rejects the credentials themselves."""


class RefreshInProgressError(RuntimeError):
    """Raised when a vehicle refresh is already in progress."""


class KamereonSession:

    tenant = None
    copy_realm = None
    unique_id = None

    def __init__(self, region, unique_id=None):
        self.settings = SETTINGS_MAP[self.tenant][region]
        self.session = requests.session()
        self._oauth = None
        self._user_id = None
        self._kamereon_refresh_token = None
        self.unique_id = unique_id

    @staticmethod
    def _generate_pkce_pair():
        verifier = secrets.token_urlsafe(64)
        digest = hashlib.sha256(verifier.encode('ascii')).digest()
        challenge = base64.urlsafe_b64encode(digest).rstrip(b'=').decode('ascii')
        return verifier, challenge

    def _is_auth_url(self, url):
        try:
            expected = urlparse(self.settings['auth_base_url'])
            parsed = urlparse(url)
            return (
                parsed.scheme == 'https'
                and parsed.hostname == expected.hostname
                and (parsed.port or 443) == (expected.port or 443)
            )
        except ValueError:
            return False

    @staticmethod
    def _parse_token_response(response, token_name, require_id_token=False):
        try:
            data = response.json()
        except ValueError as error:
            raise RuntimeError(f"Invalid {token_name} response") from error

        if not response.ok or data.get('error') or not data.get('access_token'):
            raise RuntimeError(f"Unable to obtain {token_name}")
        if require_id_token and not data.get('id_token'):
            raise RuntimeError(f"Missing ID token in {token_name} response")
        return data

    def _authorization_code(self, username, password):
        verifier, challenge = self._generate_pkce_pair()
        state = secrets.token_urlsafe(32)
        try:
            response = self.session.get(
                urljoin(self.settings['auth_base_url'], 'oauth2/authorize'),
                params={
                    'response_type': 'code',
                    'redirect_uri': self.settings['redirect_uri'],
                    'client_id': self.settings['client_id'],
                    'state': state,
                    'scope': self.settings['scope'],
                    'code_challenge': challenge,
                    'code_challenge_method': 'S256',
                    'locale': self.settings['auth_locale'],
                    'brand': self.settings['auth_brand'],
                    'client': self.settings['auth_client'],
                },
                allow_redirects=False,
                timeout=30,
            )
        except requests.RequestException:
            raise RuntimeError("Unable to contact Nissan login") from None
        response = self._follow_login_redirects(response)

        parser = _LoginFormParser()
        parser.feed(response.text)
        form = parser.login_form
        if form is None or not form['action']:
            raise RuntimeError("Nissan login form is unavailable")

        login_data = dict(form['inputs'])
        login_region = login_data.get('regionCode', '')
        login_data.update({
            'userName': username,
            'username': (
                f"{login_region}/{username}" if login_region else username
            ),
            'password': password,
        })
        form_url = urljoin(response.url, form['action'])
        if not self._is_auth_url(form_url):
            raise RuntimeError("Unexpected Nissan login form target")
        form_origin = urlparse(form_url)
        try:
            response = self.session.post(
                form_url,
                data=login_data,
                headers={
                    'Origin': f"{form_origin.scheme}://{form_origin.netloc}",
                    'Referer': response.url,
                },
                allow_redirects=False,
                timeout=30,
            )
        except requests.RequestException:
            raise RuntimeError("Unable to submit Nissan login") from None

        callback_url = self._follow_authorization_redirects(response)
        callback = urlparse(callback_url)
        expected_callback = urlparse(self.settings['redirect_uri'])
        if (callback.scheme, callback.netloc) != (
                expected_callback.scheme, expected_callback.netloc):
            raise RuntimeError("Unexpected Nissan login callback")

        callback_data = parse_qs(callback.query)
        if callback_data.get('state', [None])[0] != state:
            raise RuntimeError("Invalid Nissan login state")
        code = callback_data.get('code', [None])[0]
        if not code:
            raise NissanAuthError("Invalid credentials")
        return code, verifier

    def _follow_login_redirects(self, response):
        for _ in range(10):
            if response.is_redirect or response.is_permanent_redirect:
                location = response.headers.get('Location')
                if not location:
                    break
                target = urljoin(response.url, location)
                if not self._is_auth_url(target):
                    raise RuntimeError("Unexpected Nissan login redirect")
                try:
                    response = self.session.get(
                        target, allow_redirects=False, timeout=30)
                except requests.RequestException:
                    raise RuntimeError("Unable to load Nissan login") from None
                continue
            if response.ok and self._is_auth_url(response.url):
                return response
            break
        raise RuntimeError("Unable to load Nissan login")

    def _follow_authorization_redirects(self, response):
        expected_callback = urlparse(self.settings['redirect_uri'])
        for _ in range(10):
            if response.is_redirect or response.is_permanent_redirect:
                location = response.headers.get('Location')
                if not location:
                    break
                target = urljoin(response.url, location)
                parsed_target = urlparse(target)
                if (parsed_target.scheme, parsed_target.netloc) == (
                        expected_callback.scheme, expected_callback.netloc):
                    return target
                if not self._is_auth_url(target):
                    raise RuntimeError("Unexpected Nissan authorization redirect")
                try:
                    response = self.session.get(
                        target, allow_redirects=False, timeout=30)
                except requests.RequestException:
                    raise RuntimeError(
                        "Unable to complete Nissan login") from None
                continue

            if response.ok:
                parser = _LoginFormParser()
                parser.feed(response.text)
                if parser.login_form is not None:
                    raise NissanAuthError("Invalid credentials")
            break

        raise RuntimeError("Nissan login did not return an authorization code")

    def _exchange_wso2_token(self, code, verifier):
        response = self.session.post(
            urljoin(self.settings['auth_base_url'], 'oauth2/token'),
            data={
                'redirect_uri': self.settings['redirect_uri'],
                'grant_type': 'authorization_code',
                'client_id': self.settings['client_id'],
                'code': code,
                'code_verifier': verifier,
                'scope': self.settings['scope'],
            },
            allow_redirects=False,
            timeout=30,
        )
        return self._parse_token_response(
            response, 'Nissan OneID token', require_id_token=True)

    def _exchange_kamereon_token(self, wso2_id_token):
        response = self.session.post(
            urljoin(self.settings['user_base_url'], 'v1/oauth2/access_token'),
            params={'platform': self.settings['auth_platform']},
            headers={
                'Authorization': wso2_id_token,
                'Content-Type': 'application/vnd.api+json',
            },
            allow_redirects=False,
            timeout=30,
        )
        return self._parse_token_response(response, 'Kamereon token')

    def _install_kamereon_token(self, token):
        expires_in = int(token.get('expires_in', 3600))
        refresh_token = token.get('refresh_token') or self._kamereon_refresh_token
        oauth_token = {
            'access_token': token['access_token'],
            'token_type': token.get('token_type', 'Bearer'),
            'expires_in': expires_in,
            'expires_at': time.time() + expires_in,
        }
        if refresh_token:
            oauth_token['refresh_token'] = refresh_token
        self._kamereon_refresh_token = refresh_token
        self._oauth = OAuth2Session(
            client_id=self.settings['client_id'],
            token=oauth_token,
        )

    def _refresh_kamereon_token(self):
        if not self._kamereon_refresh_token:
            raise RuntimeError("No Kamereon refresh token available")
        response = self.session.post(
            urljoin(self.settings['user_base_url'], 'v1/oauth2/refresh-token'),
            params={'platform': self.settings['auth_platform']},
            headers={
                'Authorization': self._kamereon_refresh_token,
                'Content-Type': 'application/vnd.api+json',
            },
            data=json.dumps({'scope': self.settings['kamereon_scope']}),
            allow_redirects=False,
            timeout=30,
        )
        self._install_kamereon_token(
            self._parse_token_response(response, 'Kamereon refresh token'))

    def _refresh_authentication(self):
        try:
            self._refresh_kamereon_token()
        except Exception as error:
            _LOGGER.debug("Kamereon token refresh failed, logging in again: %s", error)
            self.login()

    def login(self, username=None, password=None):
        if username is not None and password is not None:
            self._username = username
            self._password = password

        try:
            username = self._username
            password = self._password
        except AttributeError as error:
            raise RuntimeError("Credentials are required") from error

        self.session = requests.session()
        code, verifier = self._authorization_code(username, password)
        wso2_token = self._exchange_wso2_token(code, verifier)
        self._install_kamereon_token(
            self._exchange_kamereon_token(wso2_token['id_token']))

    def request(self, method, url, **kwargs):
        for attempt in range(2):
            try:
                response = self.oauth.request(method, url, **kwargs)
            except TokenExpiredError:
                if attempt == 1:
                    raise
                self._refresh_authentication()
                continue
            if response.status_code != 401:
                return response
            if attempt == 0:
                self._refresh_authentication()
        raise TokenExpiredError()

    @property
    def oauth(self):
        if self._oauth is None:
            raise RuntimeError('No access token set, you need to log in first.')
        return self._oauth

    @property
    def user_id(self):
        if not self._user_id:
            resp = self.request(
                'GET',
                '{}v1/users/current'.format(self.settings['user_adapter_base_url'])
            )
            self._user_id = resp.json()['userId']
            _registry[USERS][self._user_id] = self
        return self._user_id

    def fetch_vehicles(self):
        resp = self.request(
            'GET',
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
        self._refresh_fetch_lock = threading.Lock()
        
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
        if self.model_name in ("TOWNSTAR"):
            self.features.append(Feature.INTERIOR_TEMP_SETTINGS)
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
                return self.session.request(
                    method, url, headers=headers, params=params, data=data)
            except NissanAuthError:
                raise
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

    @property
    def last_updated(self):
        timestamps = [
            self.battery_status_last_updated,
            self.location_last_updated,
            self.hvac_status_last_updated,
            self.lock_status_last_updated,
        ]
        return max(
            (
                t if t.tzinfo is not None
                else t.replace(tzinfo=datetime.timezone.utc)
                for t in timestamps if t is not None
            ),
            default=None,
        )

    def fetch_all(self):
        try:
            self.fetch_battery_status()
        except Exception as e:
            _LOGGER.warning("fetch_battery_status() failed: %s", e)

        if (self.model_name or "").upper() == "MICRA":
            return

        try:
            self.fetch_cockpit()
        except Exception as e:
            _LOGGER.debug("fetch_cockpit() not supported on this vehicle: %s", e)
        self.fetch_location()
        self.fetch_hvac_status()
        self.fetch_lock_status()

    def refresh_fetch(self, check_interval=10, max_attempts=5):
        """Wake the vehicle and update data repeatedly until new data is fetched or timeout is reached."""
        if check_interval < 0:
            raise ValueError('check_interval must not be negative')
        if max_attempts < 1:
            raise ValueError('max_attempts must be at least 1')

        if not self._refresh_fetch_lock.acquire(blocking=False):
            raise RefreshInProgressError(
                f"An update is already in progress for this vehicle"
            )

        try:
            self.fetch_all()
            previous_last_updated = self.last_updated
            self.refresh()

            for _ in range(max_attempts):
                time.sleep(check_interval)
                self.fetch_all()
                if self.last_updated != previous_last_updated:
                    return True
            return False
        finally:
            self._refresh_fetch_lock.release()

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
        model = (self.model_name or "").upper()
        if model == "MICRA" or model == "ARIYA":
            self.fetch_battery_status_ariya()
        elif model == "TOWNSTAR":
            self.fetch_battery_status_townstar()
        else:
            self.fetch_battery_status_leaf()

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
            return

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

        if 'lastUpdateTime' in battery_data:
            self.battery_status_last_updated = datetime.datetime.fromisoformat(battery_data['lastUpdateTime'].replace('Z','+00:00'))

        # Everything below is EV-only
        if self.range_hvac_on is None and Feature.BATTERY_STATUS not in self.features:
            return

        self.charging = ChargingStatus(battery_data.get('chargeStatus', 0))
        self.plugged_in = PluggedStatus(battery_data.get('plugStatus', 0))
        if 'vehiclePlugTimestamp' in battery_data:
            self.plugged_in_time = datetime.datetime.fromisoformat(battery_data['vehiclePlugTimestamp'].replace('Z','+00:00'))
        if 'vehicleUnplugTimestamp' in battery_data:
            self.unplugged_time = datetime.datetime.fromisoformat(battery_data['vehicleUnplugTimestamp'].replace('Z','+00:00'))

    def fetch_battery_status_townstar(self):
        resp = self._get(
            '{}v2/cars/{}/battery-status'.format(self.session.settings['car_adapter_base_url'], self.vin),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        body = resp.json()
        _LOGGER.debug("Townstar battery-status response received for vin=%s: keys=%s", self.vin, list(body.keys()))
        if 'errors' in body and Feature.BATTERY_STATUS in self.features:
            raise ValueError(body['errors'])

        if not 'data' in body or not 'attributes' in body['data']:
            _LOGGER.debug("Townstar battery-status missing data/attributes for vin=%s: %s", self.vin, body)
            self.battery_supported = False
            return

        battery_data = body['data']['attributes']
        _LOGGER.debug("Townstar battery attributes for vin=%s: %s", self.vin, battery_data)
        
        self.range_hvac_off = None
        if 'batteryAutonomy' in battery_data:
            self.range_hvac_on = battery_data.get('batteryAutonomy')
        if 'stateOfCharge' in battery_data or 'batteryLevel' in battery_data:
            battery_level = battery_data.get('batteryLevel')
            if battery_level is None:
                battery_level = battery_data.get('stateOfCharge')
            if battery_level is not None:
                self.battery_level = battery_level
        if 'totalMileage' in battery_data or 'mileage' in battery_data:
            total_mileage = battery_data.get('totalMileage')
            if total_mileage is None:
                total_mileage = battery_data.get('mileage')
            if total_mileage is not None:
                self.total_mileage = total_mileage
        self.mileage = self.total_mileage

        self.charging_speed = ChargingSpeed(None)
        if 'chargingRemainingTime' in battery_data:
            self.charge_time_required_to_full = {
                ChargingSpeed.FAST: None,
                ChargingSpeed.NORMAL: None,
                ChargingSpeed.SLOW: None,
                ChargingSpeed.ADAPTIVE: battery_data.get('chargingRemainingTime')
            }

        if 'chargingStatus' in battery_data:
            charging_status = battery_data.get('chargingStatus')
            if isinstance(charging_status, (int, float)):
                # Townstar can return fractional charging progress/status (e.g. 0.4)
                self.charging = ChargingStatus.CHARGING if charging_status > 0 else ChargingStatus.NOT_CHARGING
            else:
                self.charging = ChargingStatus(charging_status)

        if 'plugStatus' in battery_data:
            self.plugged_in = PluggedStatus(battery_data.get('plugStatus', 0))
            if self.plugged_in == PluggedStatus.NOT_PLUGGED:
                self.charging = ChargingStatus.NOT_CHARGING
                
        if 'timestamp' in battery_data:
            self.battery_status_last_updated = datetime.datetime.fromisoformat(battery_data['timestamp'].replace('Z','+00:00'))

        _LOGGER.debug(
            "Townstar battery parsed for vin=%s: level=%s autonomy=%s plugged_in=%s charging=%s remaining=%s timestamp=%s",
            self.vin,
            self.battery_level,
            self.range_hvac_on,
            self.plugged_in,
            self.charging,
            self.charge_time_required_to_full.get(ChargingSpeed.ADAPTIVE),
            self.battery_status_last_updated
        )

    def fetch_battery_status_ariya(self):
        """Fetch battery data from Nissan's newer v3 battery-status API.

        Originally added for the Ariya, this endpoint is also used by the
        new Micra EV.
        """
        resp = self._get(
            '{}v3/cars/{}/battery-status?canGen={}'.format(
                self.session.settings['user_base_url'],
                self.vin,
                self.can_generation
            ),
            headers={'Content-Type': 'application/vnd.api+json'}
        )

        body = resp.json()
        if 'errors' in body and Feature.BATTERY_STATUS in self.features:
            raise ValueError(body['errors'])

        if not 'data' in body or not 'attributes' in body['data']:
            return

        battery_data = body['data']['attributes']

        # Newer Nissan/Renault-derived vehicles may expose state of charge
        # using different field names. Use the first populated value.
        self.battery_level = battery_data.get('batteryLevel')
        self.battery_capacity = battery_data.get('batteryCapacity')
        self.battery_temperature = battery_data.get('batteryTemperature')
        self.instantaneous_power = battery_data.get('instantaneousPower')

        self.range_hvac_off = None
        self.range_hvac_on = (
            battery_data.get('batteryAutonomy')
            or battery_data.get('rangeHvacOn')
            or self.range_hvac_on
        )
        self.battery_level = battery_data.get('batteryLevel') or battery_data.get('stateOfCharge') or self.battery_level
        self.total_mileage = battery_data.get('totalMileage') or battery_data.get('mileage') or self.total_mileage
        self.mileage = self.total_mileage

        self.charging_speed = ChargingSpeed(None)
        self.charge_time_required_to_full = {
            ChargingSpeed.FAST: None,
            ChargingSpeed.NORMAL: None,
            ChargingSpeed.SLOW: None,
            ChargingSpeed.ADAPTIVE: (
                battery_data.get('chargingRemainingTime')
                or self.charge_time_required_to_full[ChargingSpeed.NORMAL]
            )
        }

        try:
            self.plugged_in = PluggedStatus(battery_data.get('plugStatus', 0))
        except (TypeError, ValueError):
            _LOGGER.debug(
                "Unknown plugStatus from v3 battery API: %s",
                battery_data.get('plugStatus')
            )
        charging_status = battery_data.get('chargingStatus')

        if charging_status is None:
            charging_status = battery_data.get('chargeStatus')

        if charging_status is not None:
            try:
                self.charging = ChargingStatus(charging_status)
            except (TypeError, ValueError):
                _LOGGER.debug(
                    "Unknown charging status from v3 battery API: %s",
                    charging_status
                )

        if 'vehiclePlugTimestamp' in battery_data:
            try:
                self.plugged_in_time = datetime.datetime.fromisoformat(
                    battery_data['vehiclePlugTimestamp'].replace('Z', '+00:00')
                )
            except (TypeError, ValueError):
                pass

        if 'vehicleUnplugTimestamp' in battery_data:
            try:
                self.unplugged_time = datetime.datetime.fromisoformat(
                    battery_data['vehicleUnplugTimestamp'].replace('Z', '+00:00')
                )
            except (TypeError, ValueError):
                pass

        if 'lastUpdateTime' in battery_data:
            try:
                self.battery_status_last_updated = datetime.datetime.fromisoformat(
                    battery_data['lastUpdateTime'].replace('Z', '+00:00')
                )
            except (TypeError, ValueError):
                pass

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

    def fetch_cockpit(self):
        if self.model_name in ("TOWNSTAR"):
            resp = self._get(
                "{}v2/cars/{}/cockpit".format(self.session.settings['car_adapter_base_url'], self.vin)
            )
        else:
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
        self.fuel_quantity = cockpit_data.get('fuelQuantity')
        self.mileage = cockpit_data.get('mileage')
        self.total_mileage = cockpit_data.get('totalMileage')

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
