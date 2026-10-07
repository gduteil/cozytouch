# 🏠 Atlantic Cozytouch

A Home Assistant integration for Atlantic's Cozytouch cloud: boilers, heat
pumps, water heaters, towel rails, radiators and air conditioners, from
Atlantic, Thermor and Sauter.

Atlantic runs several protocols behind the Cozytouch brand. This one talks to
the API the Cozytouch mobile app uses, which is not the one the official
`overkiz` integration covers. It fills the gap for the hardware Overkiz does
not see.

## ✨ What it does

- 🌡️ **Climate entities** with the modes, presets, fan and swing your hardware
  actually has, and the room temperature read back.
- 🔥 **Sensors per device**: burner, flame and pumps on a boiler, compressor
  and backup heater on a heat pump, tank temperatures and remaining hot water
  on a water heater, wifi signal, firmware.
- 🗓️ **The weekly program** the device runs on its own, shown as a calendar
  and editable from Home Assistant.
- ✈️ **Away mode** for the whole account, set in one action.
- ⚡ **Today's consumption** (energy, peak and off-peak, cost, water) where the
  installation reports it.
- 🚨 **Faults** raised in Repairs, in Atlantic's own words.
- 🌍 **English, French, Spanish, German and Italian**, following Home
  Assistant's language.

Everything runs over the cloud: one login and one poll for the whole account,
every 60 seconds by default, plus an immediate re-read whenever you change
something.

## 📋 Supported devices

There is no list, and that is the point. 🎯

The integration works out what a device is from what the API sends about it:
the `productId` Atlantic assigns it, the family it declares, and the gateway
it hangs off. That is what Atlantic's own app reads. A device nobody has ever
reported still arrives as the right kind of thing, with the modes it supports,
and named from Atlantic's catalogue of more than 2,000 models.

Boilers, heat pumps, water heaters, towel rails, room air conditioners,
electric radiators, heating circuits, gateways and the zones of a ducted unit
are all recognised this way.

### ❓ A value missing or wrong?

Your device will be recognised. What can still be missing is what its
*capabilities* mean: a device reports a list of numbered values, and the same
number can mean something different from one product family to the next. So
what is worth reporting now looks like:

- 🔢 **an unnamed value**: Home Assistant raises a notice listing the
  capability ids your devices report and nothing names yet;
- 🧪 **a value read wrong**: the wrong unit, a raw number where the app shows
  a word, a reading that never moves;
- 🎛️ **a control that does nothing**, or one the app offers and Home
  Assistant does not.

Open a [device report](https://github.com/gduteil/cozytouch/issues/new?template=device_report.yml)
with:

1. 📄 **The diagnostics file**: `Settings → Devices & services → Cozytouch →
   ⋮ → Download diagnostics`. One file covers the whole account, with every
   value each device reports and what Atlantic's catalogue says about it.
   Your credentials and address are stripped out.
2. 📱 **Screenshots of the Cozytouch app**: the device's screen and the ones
   behind it. The file says what a device *reports*, only the app says what a
   value means and what you can *do* with it.
3. 🤔 **What you expected, and what you got.**

To see unnamed values as entities while you investigate, tick
`Create entities for unknown capabilities` in the integration's options.

## 📦 Installation

### With HACS

[![Add HACS repository.](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=gduteil&repository=cozytouch&category=integration)

Or in HACS: `⋮ → Custom repositories`, URL `https://github.com/gduteil/cozytouch`,
type `Integration`. More about HACS [here](https://hacs.xyz/).

### Manually

Copy `custom_components/cozytouch` into your Home Assistant config directory
(`config/custom_components/cozytouch`) and restart Home Assistant.

## ⚙️ Configuration

1. `Settings → Devices & services → Add integration`, search for `cozytouch`.
2. Enter your Cozytouch login.
3. Keep the devices you want. They are all selected by default, and added
   together under one entry for your account.

Add or remove a device later from the integration page. The poll interval is
under `Configure`, from 15 seconds to 10 minutes. Going below a minute buys
little: Atlantic's cloud hears from your hardware on its own schedule.

### ⬆️ Updating from 1.4

1.4 made one entry per device. On the first start after updating, they become
one entry for your account with every device under it. Entity ids and their
history are kept. A few entities this version no longer builds are removed:
the per-day program sensors are disabled (a calendar replaces them), and the
eco switch on air conditioners and the min/max temperature readings are gone.

## 🗓️ Scheduling

A Cozytouch device holds its own weekly program and keeps running it when Home
Assistant is off. That is the difference with scheduling a climate entity from
an automation. Everything is in **[docs/scheduling.md](docs/scheduling.md)**:

| | |
| --- | --- |
| 🛠️ **Actions** | `cozytouch.set_schedule` writes a day to as many days as you pick, `cozytouch.get_schedule` reads a week back. |
| ⚡ **Triggers** | Device triggers, so an automation can run when the program changes what it asks for. |
| 📅 **Entities** | A calendar per program. |
| 🃏 **The card** | `custom:cozytouch-schedule-card`, served by the integration. |
| 🗣️ **Your voice** | Assist can read the program and hold a temperature between two times. |

A day holds ten slots at most, the first starts at `00:00`, and temperatures
are whole degrees.

## ✈️ Away mode

The absence belongs to the account: turning it on switches every device that
has an away mode.

- 🖱️ **From the device page**: set the dates, then turn the *Away mode* switch on.
- 🤖 **From an automation**: `cozytouch.set_away_mode` does both in one
  action, `cozytouch.clear_away_mode` ends it.
- 🗣️ **By voice**: "on part du 3 au 10 octobre", if your Assist agent can use
  tools.

```yaml
action: cozytouch.set_away_mode
target:
  entity_id: switch.boiler_away_mode
data:
  start: "2026-10-01 08:00:00"   # optional, defaults to a minute from now
  end: "2026-10-08 18:00:00"     # or duration: {days: 7}
```

## 🏷️ Versioning

Releases use CalVer: `YEAR.MONTH.PATCH`, from `2026.10.0` on. The release
before it was `1.4`.

## 🙏 Credits

Maintained by [@gduteil](https://github.com/gduteil) and
[@mathieuletyrant](https://github.com/mathieuletyrant). Several device mappings
come from people who owned the hardware and worked out what it reported:

| Device | modelId | By |
| ------ | ------: | -- |
| ACI HYB water heaters (PHAZY / AQUEO / DURALIS) | 386-394 | [@FreeTHX](https://github.com/FreeTHX), [@beorn-](https://github.com/beorn-) |
| Doris étroit 1300W CARAT | 1595 | [@tomcastleman](https://github.com/tomcastleman) |
| Doris étroit 1500W BLC | 1588 | [@jojeju9428](https://github.com/jojeju9428) |
| Calypso connecté | 1658 | [@picosam](https://github.com/picosam) |
| FLAT/S4 IOTHUB gateway | 1763 | [@Joonel](https://github.com/Joonel) |
| Thermor Malicio 3 65L | 1962 | [@genmllc](https://github.com/genmllc) |
| Egeo VS 250L | 2346 | [@Mathieu-Pasco-Breillot](https://github.com/Mathieu-Pasco-Breillot) |
| Explorer EVO 3 (270L) | 2374 | [@StefanWokusch](https://github.com/StefanWokusch) |
| Calypso SPLIT VM 200L | 1368 | [@mplessis](https://github.com/mplessis) |
| CV5 Aeromax Premium 100L | 1669 | [@Racailloux](https://github.com/Racailloux) |

The consumption sensors come from [@mmnlfrrr](https://github.com/mmnlfrrr)'s
fork, which worked out the endpoint and its tariff periods on a Duralis ACI
HYB.
