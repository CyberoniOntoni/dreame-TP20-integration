# Dreame Air Purifier for Home Assistant

A custom Home Assistant integration for Dreame air purifiers that use the **Dreame Home app** (Dreame cloud). It supports the **PM10** and the **TP20**.

It talks to Dreame's cloud with your Dreame account and polls the purifier every 30 seconds. There is no local control.

## Supported models

| Model | Status |
|---|---|
| TP20 (`dreame.airp.u2630`) | Supported. Every property was mapped and read/written on a real TP20 |
| PM10 (`dreame.airp.cvf24a`) | Supported (the upstream author's daily use) |
| PM20 | Expected to work except heating |
| Other `dreame.airp.*` models | May work partially. Entities are only created for properties the device reports. See [Adding a model](#adding-a-model) |

Devices paired with Mi Home (Xiaomi cloud) are not supported.

## Installation

### HACS (custom repository)

1. HACS → ⋮ → **Custom repositories**.
2. Add `https://github.com/CyberoniOntoni/dreame-TP20-integration`, category **Integration**.
3. Install **Dreame Air Purifier** and restart Home Assistant.

HACS offers updates when a new [release](https://github.com/CyberoniOntoni/dreame-TP20-integration/releases) is published.

### Manual

1. Copy `custom_components/dreame_airpurifier` into your Home Assistant `config/custom_components/` folder (create it if needed).
2. Restart Home Assistant.

## Setup

**Settings → Devices & services → Add integration → Dreame Air Purifier**, then enter:

- **Email or phone** and **password** for your Dreame Home account. There's no OAuth, so use the account's own password.
- **Server region**: `us`, `eu`, `cn`, `sg` or `kr`. Pick the region your Dreame app account is on.

Every purifier on the account is added.

## Entities

Only entities for features your purifier actually has are created.

| | TP20 | PM10 |
|---|---|---|
| **Fan** | 3 speeds, presets **AI Purify** / **Sleep** / **Custom**. No on/off: switch it on and off from the Dreame app or its power button | On/off, 10 speeds, presets Auto / Comfort / Custom / Pet |
| **Sensors** | PM2.5, Air Quality Level (Excellent / Good / Moderate / Poor / Bad), Fan Level, HEPA Filter Life, HEPA Filter Days Left | PM2.5, PM10, PM1, TVOC, HCHO, temperature, humidity, air quality level and %, HEPA and carbon filter life and usage |
| **Switches** | Child Lock, Continuous Monitoring (measures air quality while off) | Continuous Monitoring, Human Sensing, Follow Mode, Voice Assistant |
| **Selects** | Temperature unit | Swivel angle, temperature unit |
| **Number** | Timer (up to 12 h) | Timer (up to 24 h) |

Setting a fan speed switches the purifier to its manual mode (Custom) first, since that's the only mode that accepts a speed. If the purifier doesn't confirm a change, Home Assistant shows an error instead of the control silently snapping back.

## Upgrading

### To 2.0.0 on a TP20

Versions before 2.0.0 used the PM10's property map on the TP20. After updating, remove these leftover entities, which will show as unavailable:

- **Air Quality** (the old percentage; replaced by Air Quality Level)
- **HEPA Filter Days Total** (replaced by HEPA Filter Days Left)

The existing **Continuous Monitoring** switch is kept and now controls the right setting.

## Troubleshooting

- **Diagnostics:** device page → ⋮ → **Download diagnostics** lists every raw property the purifier reported (`siid.piid`: value), which attributes it doesn't have, and any skipped as unsafe. It contains no credentials, device IDs or MACs.
- **Startup log:** the same list is logged once at INFO level. To see it:
  ```yaml
  logger:
    logs:
      custom_components.dreame_airpurifier: info
  ```
- **The purifier restarts or switches itself off when Home Assistant polls it:** disable the integration entry, then find the cause with `tools/safe_probe.py` (see below).

## Known issues

- The Dreame API is IPv4-only. It can fail if Home Assistant routes through a Tailscale exit node.
- **TP20:** reading property 3.10 crashes the purifier (it restarts switched off). The integration and the tools never read it.
- **TP20:** Home Assistant can't switch it on or off. The power property is read-only, and the action that toggles power on the PM10 (2/3) crashes the TP20: it goes dead until its power button is pressed, and may then not reconnect to Wi-Fi. The integration never sends that action (`UNSAFE_ACTIONS` in `const.py`), and `set_property.py` refuses it. Speed and preset changes are refused while the TP20 is off (its power state is read fresh first), because writes to a switched-off TP20 haven't been tested. Settings (child lock, continuous monitoring, timer, temperature unit) can still be changed while it's off, as in the Dreame app.
- **TP20:** the Air Quality Level names assume level 1 is Excellent and 5 is Bad. If Home Assistant and the app disagree, please open an issue.
- **PM10:** the swivel range stays as set when follow mode is on. The Dreame app behaves the same way.
- **PM10:** the follow-mode mmWave radar is handled on the device and isn't exposed through the API.

## Adding a model

The scripts in `tools/` map a purifier's properties through the Dreame cloud. They need Python 3 and `requests` (`pip install requests`), and run from the `tools` folder:

| Script | What it does |
|---|---|
| `safe_probe.py` | Reads properties **one at a time**, checks the purifier still answers after each, and stops at the first one that causes trouble. `--scan --siids 1-8 --piids 1-20` probes a whole range to find unknown properties. **Start here**, especially if the purifier misbehaves |
| `monitor_properties.py` | Watches values change live while you use the Dreame app: the quickest way to work out what each property means |
| `discover_properties.py` | Fast batched scan of every property. Refused on models known to crash on some reads, unless `--force` |
| `set_property.py` | Reads or writes a single property, or calls an action |

```sh
python safe_probe.py -u <email> -p '<password>' --country <region> --confirm
python monitor_properties.py -u <email> -p '<password>' --country <region>
```

Use single quotes around the password: some shells drop characters like `$` otherwise. The scripts never print device IDs or MACs, but full scans can show values such as the device's time zone, so check before sharing output.

To add a model to the integration (`custom_components/dreame_airpurifier/`):

1. **Property table:** if its property numbers differ from the PM10's `PROP_DEFS`, add its own table to `MODEL_PROP_DEFS` in `api.py` (see `TP20_PROP_DEFS`).
2. **Profile:** add a `ModelProfile` to `PROFILES` in `const.py` for its modes, speed count, manual mode, timer limit and, if the app names them, air quality levels.
3. **Unsafe reads and actions:** if reading a property crashes it, add it to `UNSAFE_PROPS` in `const.py`; if calling an action does, add it to `UNSAFE_ACTIONS`. The integration and the tools will never send them. A model without a safe power action gets `power_action=None` in its profile.

The tools read these tables, so they label properties for the new model automatically. `re.txt` has the PM10's map as a reference.

## Credits

Forked from [shaunsingh/dreame-pm10-integration](https://github.com/shaunsingh/dreame-pm10-integration), itself a fork of [CodyJon/dreame-ap10-integration](https://github.com/CodyJon/dreame-ap10-integration).

Not affiliated with Dreame. Use at your own risk.
