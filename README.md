# Nissan Connect for Home Assistant

An integration for interacting with Nissan Connect vehicles. Based on the work of [mitchellrj](https://github.com/mitchellrj) and [tobiaswk](https://github.com/Tobiaswk/dartnissanconnect).

This is quite heavily EV-focussed as thats what I have.

This is an unofficial integration. I have no affiliation with Nissan besides owning one of their cars.

Tested with the following vehicles:
* Nissan Leaf Tekna (2022) - UK
* Nissan Qashqai (2021) - EU 

If you find any bugs or would like to request a feature, please open an issue.


## Installation

### HACS
This is the recommended installation method.
1. Add this repository to HACS as a [custom repository](https://hacs.xyz/docs/faq/custom_repositories)
2. Search for and install the Ohme addon from HACS
3. Restart Home Assistant

### Manual
1. Download the [latest release](https://github.com/dan-r/HomeAssistant-NissanConnect/releases)
2. Copy the contents of `custom_components` into the `<config directory>/custom_components` directory of your Home Assistant installation
3. Restart Home Assistant


## Setup
From the Home Assistant Integrations page, search for and add the Nissan Connect integration.

## Update Time
Following the model of leaf2mqtt, this integration can be set to use a different update time when plugged in. When HVAC is turned on the update time drops to once per minute.

## Translations
I have provided machine translations from English to the following languages as a start, but welcome native speakers to give feedback on these and to improve them:
* French
* Italian

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
* Buttons
    * Update Data
    * Flash Lights
    * Honk Horn
