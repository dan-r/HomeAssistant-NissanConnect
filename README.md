# Nissan Connect for Home Assistant

A basic integration for interacting with Nissan Connect vehicles. Based on the work of @mitchellrj and tobiaswkjeldsen.

This is quite heavily EV-focussed as thats what I have.

This is an unofficial integration. I have no affiliation with Nissan besides owning one of their cars.

Tested with the following vehicles:
* Nissan Leaf Tekna (2022) - UK

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

## Entities
This integration exposes the following entities. Please note that entities will only be shown if the functionality is supported by your car.

* Binary Sensors
    * Car Connected - On when the car is plugged in (EV Only)
    * Car Charging - On when the car is plugged in and drawing power (EV Only)
* Sensors
    * Battery Level
    * Charge Time
    * Internal Temperature
    * External Temperature
    * Range
    * Odometer
* Climate
* Device Tracker
* Buttons
    * Update Data - Force an update