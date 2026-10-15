# Dreame Air Purifier for Home Assistant

A custom Home Assistant integration for Dreame air purifiers that use the **Dreame Home app** (Dreame cloud). This fork is adding support for the **Dreame TP20**.

It talks to Dreame's cloud with your Dreame account and polls the purifier every 30 seconds. There is no local control.

## Supported models

| Model | Status |
|---|---|
| PM10 | Works (upstream author's daily use) |
| TP20 | In progress. Connects and reads values; fan speeds, presets and power control still use PM10 values and need mapping |
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

- **Fan**: on/off, speed, preset modes
- **Sensors**: PM2.5, PM10, PM1, TVOC, HCHO, temperature, humidity, air quality level and %, filter life and usage
- **Switches**: continuous monitoring, human sensing, follow mode, voice assistant
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
4. Update `PROP_DEFS` in `custom_components/dreame_airpurifier/api.py`.

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
