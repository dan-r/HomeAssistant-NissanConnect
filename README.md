# NissanConnect for Home Assistant

An unofficial integration for interacting with NissanConnect vehicles in Europe. Based on the work of [mitchellrj](https://github.com/mitchellrj/kamereon-python) and [tobiaswk](https://github.com/Tobiaswk/dartnissanconnect). I have no affiliation with Nissan besides owning one of their cars.

_Please note this integration is only for vehicles using the NissanConnect Services app, not NissanConnect EV or any other app._

If you find any bugs or would like to request a feature, please open an issue.

## Tested Vehicles
This integration has been tested with the following vehicles:
* Nissan Leaf (2022) [@dan-r]
* Nissan Qashqai (2021) 
* Nissan Ariya
* Nissan X-Trail (2024)
* Nissan Juke (2021)

## Supported Regions
* Europe

Currently only Nissan vehicles within Europe are supported.

### North America
The API used in North America is completely separate to Europe and it appears that Nissan USA are [a lot more hostile](https://tobis.dk/blog/the-farce-of-nissanconnect-north-america/) towards third-party access. Any future US support would rely on library support (such as [dartnissanconnectna](https://gitlab.com/tobiaswkjeldsen/dartnissanconnectna)) or someone in North America maintaining that side of things. If you're interested, get in touch!

## Installation

### HACS

[![Open your Home Assistant instance and open a repository inside the Home Assistant Community Store.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=dan-r&repository=HomeAssistant-NissanConnect&category=integration)

This is the recommended installation method.
1. Search for and install the **NissanConnect [EU]** integration from HACS
2. Restart Home Assistant

### Manual
1. Download the [latest release](https://github.com/dan-r/HomeAssistant-NissanConnect/releases)
2. Copy the contents of `custom_components` into the `<config directory>/custom_components` directory of your Home Assistant installation
3. Restart Home Assistant


## Setup
From the Home Assistant Integrations page, search for and add the Nissan Connect integration.

### Remote Lock and Unlock

Remote lock and unlock is optional and must be configured separately for each
vehicle:

1. Open the NissanConnect integration options and select **Configure remote
    lock**.
2. Select a supported vehicle. Nissan sends a six-digit verification code to
    the account email address.
3. Enter the verification code, then choose a four-digit Nissan remote-control
    PIN.
4. Enter that PIN in Home Assistant's `code` field whenever you lock or unlock
    the vehicle.

Home Assistant does not store the verification code or PIN. The integration
stores only a random per-vehicle device ID and the setup state. The options
flow can disable or re-enable the entity, change the enrolled PIN, or remove
the trusted Home Assistant device from Nissan.

The lock entity is offered only when the vehicle advertises compatible lock
status, command, and security services. Availability still depends on vehicle
model, production date, equipment, country, and an active NissanConnect
subscription. Setup currently supports the vehicle owner account; vehicles
shared through a secondary account are not enabled.

## Update Time
Terminology used for this integration:
* Polling - the car is woken up and new status is reported. This is disabled by default, but can be enabled by setting the polling interval to a non-zero value
* Update - data is fetched from Nissan but the car is not woken up
* Remote lock/unlock - an explicit user command. It is never sent by a coordinator update, and the integration does not add a speculative vehicle wake-up before the command

Following the model of leaf2mqtt, this integration can be set to use a different polling time when plugged in. When HVAC is turned on the polling time always drops to once per minute.

To prevent excessive 12v battery drain when plugged in but not charging for extended periods of time, the polling interval reverts to the standard interval after 4 consecutive updates show the car as plugged in but not charging.
This logic was added to give the benefit of quicker response times on the charging status binary sensor, which can be especially useful when charging with load-balanced or 'smart' chargers.

## Translations
Translations are provided for the following languages. If you are a native speaker and spot any mistakes, please let me know.
* English
* Danish
* Dutch
* French
* German
* Italian
* Norwegian
* Polish
* Portuguese
* Russian
* Spanish

## Entities
This integration exposes the following entities. Please note that entities will only be shown if the functionality is supported by your car.

* Binary Sensors
    * Car Plugged In (EV Only)
    * Car Charging (EV Only)
    * Doors Locked
* Sensors
    * Battery Level
    * Charge Time
    * Internal Temperature
    * External Temperature
    * Range (EV Only)
    * Odometer
    * Daily Distance
    * Daily Trips
    * Daily Efficiency (EV Only)
    * Monthly Distance
    * Monthly Trips
    * Monthly Efficiency (EV Only)
* Climate
* Device Tracker
* Lock
    * Doors (requires the four-digit Nissan remote-control PIN for every command)
* Buttons
    * Update Data
    * Flash Lights
    * Honk Horn
    * Start Charge
