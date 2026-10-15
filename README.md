# Dreame Air Purifier for Home Assistant

A custom Home Assistant integration for Dreame air purifiers that use the **Dreame Home app** (Dreame cloud). This fork is adding support for the **Dreame TP20**.

It talks to Dreame's cloud with your Dreame account and polls the purifier every 30 seconds. There is no local control.

## Supported models

| Model | Status |
|---|---|
| PM10 | Works (upstream author's daily use) |
| TP20 (`dreame.airp.u2630`) | Mapped from the device: fan with 3 speeds and AI Purify / Sleep / Custom presets, power, PM2.5, air quality, fan level, HEPA life, child lock, continuous monitoring, temperature unit, timer. Each was read and written on a real TP20 with the scripts in `tools/`; the integration's own controls haven't been tried in Home Assistant yet |
| PM20 | Expected to work except heating |
| Other `dreame.airp.*` models | May work partially. Entities are only created for properties the device reports |

Devices paired with Mi Home (Xiaomi cloud) are not supported.

## Installation

### HACS (custom repository)

1. HACS → ⋮ → **Custom repositories**.
2. Add `https://github.com/CyberoniOntoni/dreame-TP20-integration`, category **Integration**.
3. Install **Dreame Air Purifier** and restart Home Assistant.

### Manual

1. Copy `custom_components/dreame_airpurifier` into your Home Assistant `config/custom_components/` folder (create it if needed).
2. Restart Home Assistant.

## Setup

**Settings → Devices & services → Add integration → Dreame Air Purifier**, then enter:

- **Email or phone** and **password** for your Dreame Home account. There's no OAuth, so use the account's own password.
- **Server region**: `us`, `eu`, `cn`, `sg` or `kr`. Pick the region your Dreame app account is on.

Every purifier on the account is added.

## Entities

What you get depends on what your model reports. Features it doesn't have are not created.

- **Fan**: on/off, speed, preset modes (speeds and preset names depend on the model)
- **Sensors**: PM2.5, PM10, PM1, TVOC, HCHO, temperature, humidity, air quality level and %, fan level, filter life and usage
- **Switches**: continuous monitoring, child lock, human sensing, follow mode, voice assistant
- **Selects**: swivel angle, temperature unit
- **Number**: shutdown timer

## Adding or mapping a model

1. Install the integration and add your account.
2. Go to the device page → ⋮ → **Download diagnostics**. The file lists every raw property the device reported (`siid.piid`: value) and which known attributes are missing. It contains no credentials, device IDs or MACs.
3. For properties outside the known map, scan everything with:
   ```sh
   python3 tools/discover_properties.py -u <email> -p <password> --country <region>
   ```
   `tools/monitor_properties.py` watches values change live while you use the app, and `tools/set_property.py` writes a single property. `re.txt` has the PM10 map as a reference.

   If polling makes your purifier misbehave (e.g. reboot), use `tools/safe_probe.py` first: it reads one property at a time, checks the device is still answering after each, and stops at the first one that causes trouble. With `--scan --siids 1-8 --piids 1-20` it does the same over a whole range, to find properties the integration doesn't know yet.

   Properties found to crash a model go in `UNSAFE_PROPS` in `const.py`. The integration never reads them, and all the tools skip them. On such models `discover_properties.py` refuses its batched scan unless you pass `--force`, and `monitor_properties.py` watches only known properties unless you pass `--full-scan`. The TP20 (`dreame.airp.u2630`) crashes, and comes back switched off, when 3.10 is read.
4. Add the model to `custom_components/dreame_airpurifier/`: its own property table in `MODEL_PROP_DEFS` (`api.py`) if its property numbers differ from the PM10's `PROP_DEFS`, and a `ModelProfile` in `PROFILES` (`const.py`) for its modes, speed count and timer limit. The tools pick up the model's table automatically.

The same property list is logged once at startup at INFO level. To see it:

```yaml
logger:
  logs:
    custom_components.dreame_airpurifier: info
```

## Known issues

- The Dreame API is IPv4-only. It can fail if Home Assistant routes through a Tailscale exit node.
- On the PM10, the swivel range stays as set when follow mode is on. The Dreame app behaves the same way.
- The follow-mode mmWave radar is handled on the device and isn't exposed through the API.

## Credits

Forked from [shaunsingh/dreame-pm10-integration](https://github.com/shaunsingh/dreame-pm10-integration), itself a fork of [CodyJon/dreame-ap10-integration](https://github.com/CodyJon/dreame-ap10-integration).

Not affiliated with Dreame. Use at your own risk.
