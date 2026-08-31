# Based on work by @mitchellrj and @Tobiaswk
# Portions re-licensed from Apache License, Version 2.0 with permission

import base64
import collections
import datetime
import hashlib
from html.parser import HTMLParser
import hmac
import json
import logging
import os
import secrets
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

    def initiate_srp(self, pincode: str):
        """Register a new SRP PIN for this account/vehicle. Must be called
        (once) before lock()/unlock() will work, and whenever the PIN changes."""
        _LOGGER.debug("SRP enroll: generating salt/verifier for vin=%s user_id=%s pincode_len=%d",
                      self.vin, self.user_id, len(pincode))
        (salt, verifier) = SRP.enroll(self.user_id, pincode)
        _LOGGER.debug("SRP enroll: salt=%s verifier_len=%d", salt, len(verifier))

        url = '{}v1/cars/{}/actions/srp-initiates'.format(self.session.settings['car_adapter_base_url'], self.vin)
        _LOGGER.debug("POST %s (SrpInitiates)", url)
        resp = self._post(
            url,
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
        _LOGGER.debug("srp-initiates response: status=%s body=%s", resp.status_code, resp.text)
        body = resp.json()
        if 'errors' in body:
            _LOGGER.error("srp-initiates failed for vin=%s: %s", self.vin, body['errors'])
            raise ValueError(body['errors'])
        _LOGGER.info("SRP PIN enrolled for vin=%s", self.vin)
        return body

    def validate_srp(self, srp_session: 'SRP'):
        """Send the client's SRP public ephemeral value (A) to the vehicle to
        start an SRP challenge, returning the action id used to poll for the
        vehicle's response (B, salt) via _poll_srp_challenge()."""
        a = srp_session.generate_a()
        _LOGGER.debug("SRP validate: generated A=%s for vin=%s", a, self.vin)

        url = '{}v1/cars/{}/actions/srp-sets'.format(self.session.settings['car_adapter_base_url'], self.vin)
        _LOGGER.debug("POST %s (SrpSets)", url)
        resp = self._post(
            url,
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
        _LOGGER.debug("srp-sets response: status=%s body=%s", resp.status_code, resp.text)
        body = resp.json()
        if 'errors' in body:
            _LOGGER.error("srp-sets failed for vin=%s: %s", self.vin, body['errors'])
            raise ValueError(body['errors'])
        action_id = body.get('data', {}).get('id')
        if not action_id:
            _LOGGER.error("srp-sets response missing action id for vin=%s: %s", self.vin, body)
            raise ValueError('srp-sets response did not include an action id: {}'.format(body))
        _LOGGER.debug("srp-sets accepted, action_id=%s", action_id)
        return action_id

    def _poll_action_status(self, action_id: str, timeout: float=25, interval: float=1.5,
                             initial_delay: float=1.0):
        """Poll GET .../actions/status?actionId=... until the vehicle responds,
        returning the raw 'attributes' dict of the ActionStatus response.

        This hits a separate microservice (action_status_polling_base_url)
        from the one that creates the action (e.g. car_adapter_base_url via
        srp-sets), so there's a real propagation delay before an action_id
        is queryable there: a 404 "No action(s) found for this vehicle"
        shortly after creation is treated as "not indexed yet" and retried,
        rather than a hard failure.
        """
        deadline = time.monotonic() + timeout
        attempt = 0
        _LOGGER.debug("Waiting %.1fs before first actions/status poll for action_id=%s (service propagation delay)",
                      initial_delay, action_id)
        time.sleep(initial_delay)
        while True:
            attempt += 1
            resp = self._get(
                '{}v1/cars/{}/actions/status'.format(self.session.settings['action_status_polling_base_url'], self.vin),
                params={'actionId': action_id},
            )
            _LOGGER.debug("actions/status poll #%d for action_id=%s: status=%s body=%s",
                          attempt, action_id, resp.status_code, resp.text)
            body = resp.json()
            if 'errors' in body:
                error_codes = [e.get('code') for e in body.get('errors', [])]
                if resp.status_code == 404 and '404' in error_codes:
                    _LOGGER.debug("Action %s not indexed yet on attempt #%d, will keep polling",
                                  action_id, attempt)
                else:
                    _LOGGER.error("actions/status failed for action_id=%s: %s", action_id, body['errors'])
                    raise ValueError(body['errors'])
            else:
                attributes = body.get('data', {}).get('attributes', {})
                yield attributes
            if time.monotonic() >= deadline:
                _LOGGER.error("Timed out after %d polls waiting for action %s to complete", attempt, action_id)
                raise TimeoutError('Timed out waiting for action {} to complete'.format(action_id))
            time.sleep(interval)

    def _poll_srp_challenge(self, action_id: str, timeout: float=25, interval: float=1.5):
        """Poll for the vehicle's SRP challenge (salt, B) in response to a
        prior validate_srp() call. Returns (salt, b) hex strings."""
        for attributes in self._poll_action_status(action_id, timeout=timeout, interval=interval):
            values = {
                item['name']: item['value']
                for item in (attributes.get('data') or [])
                if isinstance(item, dict) and 'name' in item
            }
            status = attributes.get('status')
            _LOGGER.debug("SRP challenge poll: action_id=%s status=%s keys=%s",
                          action_id, status, list(values.keys()))
            salt = values.get('srpLoginS')
            b = values.get('srpLoginB')
            if salt and b:
                _LOGGER.debug("SRP challenge received: salt=%s B=%s", salt, b)
                return (salt, b)
            if status in ('CANCELLED', 'REJECTED'):
                # A definitive failure response, whether or not it carries a
                # 'data' payload (e.g. status=KO/errorCode=N with empty
                # srpLoginB/srpLoginS is still a rejection, not "not ready
                # yet") - don't keep polling until the overall timeout.
                error_code = values.get('errorCode', attributes.get('errorCode'))
                _LOGGER.error("SRP challenge rejected for action_id=%s: status=%s errorCode=%s values=%s",
                              action_id, values.get('status', status), error_code, values)
                raise ValueError('SRP challenge rejected: status={} errorCode={}'.format(
                    values.get('status', status), error_code))
            if status == 'TIMEOUT':
                _LOGGER.error("SRP challenge timed out server-side for action_id=%s", action_id)
                raise TimeoutError('SRP challenge timed out')
        raise TimeoutError('Timed out waiting for SRP challenge (B) from vehicle')

    def srp_proof(self, pincode: str, order: str):
        """Perform the full per-command SRP-6a authentication handshake
        (generate A, send it, wait for the vehicle's challenge, compute the
        proof) and return the resulting proof hex string, ready to be
        attached as the 'srp' attribute of the command being authorized.

        `order` must match the exact command, e.g. '<VIN>/RLU/Unlock' -
        see SRP.generate_proof for the full list of suffixes.
        """
        _LOGGER.info("Starting SRP proof handshake for vin=%s order=%s", self.vin, order)
        srp_session = SRP()
        action_id = self.validate_srp(srp_session)
        salt, b = self._poll_srp_challenge(action_id)
        proof = srp_session.generate_proof(salt, b, self.user_id, pincode, order)
        _LOGGER.debug("SRP proof computed for order=%s: %s", order, proof)
        return proof

    def _post_and_check(self, url, data=None, headers=None):
        _LOGGER.debug("POST %s data=%s", url, data)
        resp = self._post(url, data=data, headers=headers)
        _LOGGER.debug("Response from %s: status=%s body=%s", url, resp.status_code, resp.text)
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except ValueError:
                body = resp.text
            _LOGGER.error("Request to %s failed (%s): %s", url, resp.status_code, body)
            raise ValueError('Request to {} failed ({}): {}'.format(url, resp.status_code, body))
        return resp

    def generate_device_otp(self, device_id: str):
        """Trigger the one-time PIN code email required to register a new
        'device' with this vehicle. This is a prerequisite, separate from
        SRP PIN enrollment, for any SRP-gated remote command (lock/unlock,
        remote engine start, ...) to be accepted: the backend rejects such
        commands from a userId/vehicle it has no registered device for.

        `device_id` should be a stable identifier chosen once and reused for
        this integration (the app uses Android's Settings.Secure.ANDROID_ID;
        any persisted unique string works). Call this once, then pass the
        code that arrives by email to register_device().
        """
        _LOGGER.info("Requesting device registration OTP email for vin=%s user_id=%s device_id=%s",
                     self.vin, self.user_id, device_id)
        self._post_and_check(
            '{}v1/users/{}/vehicles/{}/generate-device-otp'.format(
                self.session.settings['user_base_url'], self.user_id, self.vin),
            data=json.dumps({
                'data': {
                    'type': 'GenerateDeviceOtp',
                    'attributes': {'deviceId': device_id}
                }
            }),
            headers={'Content-Type': 'application/json'}
        )
        _LOGGER.info("Device registration OTP requested successfully for device_id=%s", device_id)

    def register_device(self, device_id: str, otp: str, model_name: str='Home Assistant'):
        """Complete device registration using the one-time PIN emailed by a
        prior generate_device_otp() call for the same `device_id`. Some
        vehicles only allow a single registered device at a time (any
        previous device is unregistered), others allow up to 10.

        Idempotent: if `device_id` is already registered for this vehicle
        (HTTP 409 / error code 409010 "Device already exists" - e.g. because
        a previous attempt got this far but failed on a later step, such as
        SRP PIN enrollment), that's treated as success rather than an error,
        since the desired end state already holds.
        """
        _LOGGER.info("Registering device_id=%s (otp_len=%d, model_name=%r) for vin=%s user_id=%s",
                     device_id, len(otp), model_name, self.vin, self.user_id)
        url = '{}v1/users/{}/vehicles/{}/register-device'.format(
            self.session.settings['user_base_url'], self.user_id, self.vin)
        resp = self._post(
            url,
            data=json.dumps({
                'data': {
                    'type': 'RegisterDevice',
                    'attributes': {'deviceId': device_id, 'otp': otp, 'modelName': model_name}
                }
            }),
            headers={'Content-Type': 'application/json'}
        )
        _LOGGER.debug("register-device response: status=%s body=%s", resp.status_code, resp.text)

        if resp.status_code == 409:
            try:
                body = resp.json()
            except ValueError:
                body = {}
            error_codes = [e.get('code') for e in body.get('errors', [])]
            if '409010' in error_codes:
                _LOGGER.info(
                    "device_id=%s was already registered for vin=%s - treating as success",
                    device_id, self.vin
                )
                return
            _LOGGER.error("register-device conflict for vin=%s (unrecognised): %s", self.vin, body)
            raise ValueError('Request to {} failed ({}): {}'.format(url, resp.status_code, body))

        if resp.status_code >= 400:
            try:
                body = resp.json()
            except ValueError:
                body = resp.text
            _LOGGER.error("register-device failed for vin=%s (%s): %s", self.vin, resp.status_code, body)
            raise ValueError('Request to {} failed ({}): {}'.format(url, resp.status_code, body))

        _LOGGER.info("Device %s registered successfully for vin=%s", device_id, self.vin)

    def get_device_registration_status(self, device_id: str) -> bool:
        """Return whether `device_id` is currently a registered device for
        this vehicle/account."""
        url = '{}v1/users/{}/vehicles/{}/devices/{}/registration-status'.format(
            self.session.settings['user_base_url'], self.user_id, self.vin, device_id)
        _LOGGER.debug("GET %s", url)
        resp = self._get(url)
        _LOGGER.debug("registration-status response for device_id=%s: status=%s body=%s",
                      device_id, resp.status_code, resp.text)
        return resp.status_code < 400

    def list_registered_devices(self):
        """List the devices currently registered for this vehicle."""
        url = '{}v1/vehicles/{}/registered-devices'.format(self.session.settings['user_base_url'], self.vin)
        _LOGGER.debug("GET %s", url)
        resp = self._get(url)
        _LOGGER.debug("registered-devices response for vin=%s: status=%s body=%s",
                      self.vin, resp.status_code, resp.text)
        body = resp.json()
        if 'errors' in body:
            _LOGGER.error("registered-devices failed for vin=%s: %s", self.vin, body['errors'])
            raise ValueError(body['errors'])
        return body.get('data', {}).get('attributes', {})

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

    def lock_unlock(self, pincode: str, action: str, group: LockableDoorGroup=None):
        if Feature.APP_DOOR_LOCKING not in self.features:
            _LOGGER.debug("lock_unlock(%s) skipped: vin=%s does not have APP_DOOR_LOCKING", action, self.vin)
            return
        assert action in ('lock', 'unlock')
        if group is None:
            group = LockableDoorGroup.DOORS_AND_HATCH
        order = '{}/RLU/{}'.format(self.vin, 'Lock' if action == 'lock' else 'Unlock')
        _LOGGER.info("Requesting %s for vin=%s (target=%s)", action, self.vin, group.value)
        srp = self.srp_proof(pincode, order)

        # LockUnlock shares the same generic "VehicleControls" request shape
        # as ChargingStart/HornLights (action/target/srp attributes) -
        # confirmed from the app's IRemoteServer.lockUnlockVehicle() and
        # VehicleControls model, not a bespoke lock/doorType shape.
        #
        # Content-Type: the decompiled custom Retrofit Converter (qb.a in the
        # app) builds a RequestBody whose contentType() claims
        # "application/json; charset=utf-8", which I inferred would win on
        # the wire via OkHttp's BridgeInterceptor overriding the interface's
        # declared "vnd.api+json" - that inference was wrong. The server
        # rejects "application/json; charset=utf-8" outright ("Invalid
        # Content-Type header value"), and separately already accepted
        # vnd.api+json (got as far as parsing attributes and rejecting the
        # old field names, before this fix). vnd.api+json it is - confirmed
        # by the server's own behaviour, not decompiled code.
        url = '{}v1/cars/{}/actions/lock-unlock'.format(self.session.settings['car_adapter_base_url'], self.vin)
        _LOGGER.debug("POST %s (LockUnlock action=%s)", url, action)
        resp = self._post(
            url,
            data=json.dumps({
                'data': {
                    'type': 'LockUnlock',
                    'attributes': {
                        'action': action,
                        'target': group.value,
                        'srp': srp
                    }
                }
            }),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        _LOGGER.debug("lock-unlock response: status=%s body=%s", resp.status_code, resp.text)
        body = resp.json()
        if 'errors' in body:
            _LOGGER.error("lock-unlock (%s) failed for vin=%s: %s", action, self.vin, body['errors'])
            raise ValueError(body['errors'])
        _LOGGER.info("%s request accepted for vin=%s", action, self.vin)
        return body

    def lock(self, pincode: str, group: LockableDoorGroup=None):
        return self.lock_unlock(pincode, 'lock', group)

    def unlock(self, pincode: str, group: LockableDoorGroup=None):
        return self.lock_unlock(pincode, 'unlock', group)

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

    def fetch_battery_status_ariya(self):
        resp = self._get(
            '{}v3/cars/{}/battery-status?canGen={}'.format(self.session.settings['user_base_url'], self.vin, self.can_generation),
            headers={'Content-Type': 'application/vnd.api+json'}
        )
        body = resp.json()
        if 'errors' in body and Feature.BATTERY_STATUS in self.features:
            raise ValueError(body['errors'])

        if not 'data' in body or not 'attributes' in body['data']:
            return

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
    """SRP-6a (RFC 5054 2048-bit group, SHA-256) as used by the MyNISSAN /
    MyRenault apps to authorize remote vehicle commands (lock/unlock, HVAC,
    charging, horn/lights, ...).

    Reverse engineered from libnative-lib.so (com.srp.renault.srploaderapp.
    SrpModuleAPI / JNI functions SRPenrollJNI, SRPgenAJNI, SRPgenProofJNI) in
    the MyNISSAN Android app. It's a fairly standard SRP-6a client, with two
    Renault/Nissan-specific details:
      * x = SHA256(salt | SHA256(user_id | ':' | pincode)), K = SHA256(S)
        (plain hash of S, not the legacy RFC2945 interleaved hash)
      * the final proof is HMAC-SHA256(key=K, message=A|B|user_id|salt|order)
        i.e. the session key is bound to the exact command being authorized
        via the `order` string, rather than sent as a bare SRP M1.

    All values (salt, verifier, A, B, proof) are exchanged as upper/lower
    case-insensitive hex strings, matching the vehicle API.
    """

    N = int(SRP_N, 16)
    g = SRP_G
    N_BYTES = 256  # 2048-bit modulus

    def __init__(self):
        self.a = None
        self.A = None

    @staticmethod
    def _sha256(*parts):
        h = hashlib.sha256()
        for part in parts:
            h.update(part)
        return h.digest()

    @classmethod
    def _compute_x(cls, salt: bytes, user_id: str, secret: str) -> int:
        inner = cls._sha256(user_id.encode('utf-8'), b':', secret.encode('utf-8'))
        outer = cls._sha256(salt, inner)
        return int.from_bytes(outer, 'big')

    @classmethod
    def enroll(cls, user_id, pincode):
        """Generate a fresh (salt, verifier) pair to register a new SRP PIN
        for this account/vehicle via the srp-initiates action."""
        salt = os.urandom(10)
        x = cls._compute_x(salt, user_id, pincode)
        verifier = pow(cls.g, x, cls.N)
        salt_hex = salt.hex()
        verifier_hex = verifier.to_bytes(cls.N_BYTES, 'big').hex()
        return (salt_hex, verifier_hex)

    def generate_a(self):
        """Generate the client's SRP ephemeral keypair (a, A) and return A as
        a hex string, to be sent to the vehicle via the srp-sets action.
        The private value `a` is kept on this instance for generate_proof()."""
        self.a = int.from_bytes(os.urandom(32), 'big')
        self.A = pow(self.g, self.a, self.N)
        return self.A.to_bytes(self.N_BYTES, 'big').hex()

    def generate_proof(self, salt, b, user_id, confirm_code, order):
        """Required for remote lock / unlock (and other SRP-gated commands).

        generate_a() must have been called first (on this same instance) to
        establish (a, A) for the session; `salt` and `b` (=B) are the values
        returned by the vehicle in response to the srp-sets action.

        order = '<VIN>/<PERMISSIONS>'
        where PERMISSIONS is one of:
        * "BCI/Block"
        * "BCI/Unblock"
        * "RC/Delayed"
        * "RC/Start"
        * "RC/Stop"
        * "RES/DoubleStart"
        * "RES/Start"
        * "RES/Stop"
        * "RHL/Start/HornOnly"
        * "RHL/Start/HornLight"
        * "RHL/Start/LightOnly"
        * "RHL/Stop"
        * "RLU/Lock"
        * "RLU/Unlock"
        * "RPC_ICE/Start"
        * "RPC_ICE/Stop"
        * "RPU_CCS/Disable"
        * "RPU_CCS/Enable"
        * "RPU_SVTB/Disable"
        * "RPU_SVTB/Enable"
        """
        if self.a is None or self.A is None:
            raise RuntimeError('generate_a() must be called before generate_proof()')

        _LOGGER.debug("SRP generate_proof: user_id=%s order=%s salt=%s B=%s pincode_len=%d",
                      user_id, order, salt, b, len(confirm_code))

        salt_bytes = bytes.fromhex(salt)
        B = int(b, 16)
        if B % self.N == 0:
            raise ValueError('Invalid server public value B')

        k = int.from_bytes(
            self._sha256(self.N.to_bytes(self.N_BYTES, 'big'), bytes([self.g])), 'big')

        A_bytes = self.A.to_bytes(self.N_BYTES, 'big')
        B_bytes = B.to_bytes(self.N_BYTES, 'big')
        u = int.from_bytes(self._sha256(A_bytes, B_bytes), 'big')

        x = self._compute_x(salt_bytes, user_id, confirm_code)
        gx = pow(self.g, x, self.N)
        S = pow((B - k * gx) % self.N, self.a + u * x, self.N)
        K = self._sha256(S.to_bytes(self.N_BYTES, 'big'))

        message = A_bytes + B_bytes + user_id.encode('utf-8') + salt_bytes + order.encode('utf-8')
        proof = hmac.new(K, message, hashlib.sha256).digest()
        return proof.hex()
