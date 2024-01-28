# Cozytouch
This is an Atlantic Cozytouch cloud integration. Atlantic use multiple protocols, in my case the protocol is different than the one implemented by official integration (overkiz).

This has been tested using a `Navilink 128 radio connect` connected on a `Atlantic Naema 2 micro duo 25`, but it should work for other devices.

Only some capabilities have been mapped for now, an option is available during configuration to add all found capabilities as generic sensors.



## Installation

You can install it using HACS or manually.

#### With HACS

[![Add HACS repository.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=gduteil&repository=cozytouch&category=integration)

More informations about HACS [here](https://hacs.xyz/).

#### Manually

Clone this repository and copy `custom_components/cozytouch` to your Home Assistant config durectory (ex : `config/custom_components/cozytouch`)

Restart Home Assistant.

## Configuration

Once your Home Assistant has restarted, go to `Settings -> Devices & Services -> Add an  intégration`.

Search for `cozytouch` and select the `Atlantic Cozytouch` integration.

Enter your Cozytouch credentials.

If connection is working, you should have a list of devices configured on your account.

Select the device you want to add.

Only some values are mapped for now, you can select `Create entities for unknown capabilities` if you want to add all detected capabilities (this can be useful to help mapping).

