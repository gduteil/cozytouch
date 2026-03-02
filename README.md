# Cozytouch
This is an Atlantic Cozytouch cloud integration. Atlantic use multiple protocols, in my case the protocol is different than the one implemented by official integration (overkiz).

This has been tested using on : 
  - `Atlantic Naema 2 Micro 25` gas boiler using a `Ǹavilink Radio-Connect 128` thermostat
  - `Atlantic Naema 2 Duo 25` gas boiler using a `Ǹavilink Radio-Connect 128` thermostat
  - `Atlantic Naia 2 Micro 25` gas boiler using a `Ǹavilink Radio-Connect 128` thermostat
  - `Atlantic Loria Duo 6006 R32` heat pump using a `Navilink Radio-Connect 128` thermostat
  - `Atlantic Alfea Excellia Duo` heat pump using a `Navilink Radio-Connect 228` thermostat
  - `Takao M3` air conditionning
  - `Kelud 1750W` towel rack
  - `Sauter Asama Connecté II Ventilo 1750W` towel rack

A special mapping needs to be done for each model type, feel free to create an issue to help supporting your device.


## Installation

You can install it using HACS or manually.

#### With HACS

[![Add HACS repository.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=gduteil&repository=cozytouch&category=integration)

More informations about HACS [here](https://hacs.xyz/).

#### Manually

Clone this repository and copy `custom_components/cozytouch` to your Home Assistant config directory (ex : `config/custom_components/cozytouch`)

Restart Home Assistant.

## Configuration

Once your Home Assistant has restarted, go to `Settings -> Devices & Services -> Add an  integration`.

Search for `cozytouch` and select the `Atlantic Cozytouch` integration.

Enter your Cozytouch credentials.

If connection is working, you should have a list of devices configured on your account.

Select the device you want to add.

Only some values are mapped for now, you can select `Create entities for unknown capabilities` if you want to add all detected capabilities (this can be useful to help mapping).

