#!/usr/bin/env python3
"""
Dreame PM10 (dreame.airp.cvf24a) — MiOT Property Discovery & Reverse Engineering Tool

This script connects to the Dreame Cloud API, finds your PM10 air purifier,
and systematically probes ALL possible siid/piid combinations to discover
the full property map. It also tests known actions.

Usage:
    python3 tools/discover_pm10.py --username YOUR_EMAIL --password YOUR_PASSWORD [--country us]

The output is a full report of every readable property on the device,
which you can use to update api.py for PM10 support.
"""

import argparse
import hashlib
import json
import logging
import os
import requests
import sys
import time
from datetime import datetime

# ─── Dreame Cloud Constants ─────────────────────────────────────────────────
DREAME_SALT = "RAylYC%fmSKp7%Tq"
DREAME_USER_AGENT = "Dreame_Smarthome/2.1.9 (iPhone; iOS 18.4.1; Scale/3.00)"
DREAME_AUTH_BASIC = "Basic ZHJlYW1lX2FwcHYxOkFQXmR2QHpAU1FZVnhOODg="
DREAME_TENANT_ID = "000000"

# ─── Known AP10 Property Map (for comparison) ───────────────────────────────
AP10_KNOWN = {
    (2, 1): "Power (1=on, 2=standby)",
    (2, 3): "Mode (0=Auto, 2=Sleep, 3=Custom, 4=Pet)",
    (2, 4): "Fan Speed (1-5)",
    (2, 5): "Fan Percent (read-only)",
    (2, 6): "Ionizer (-1=auto, 0=off, 1=on)",
    (3, 4): "Air Quality Level",
    (3, 5): "PM2.5",
    (4, 1): "Filter Life %",
    (4, 2): "Filter Days Total",
    (4, 3): "Filter Hours Used",
    (6, 5): "LED",
    (6, 6): "Buzzer",
    (6, 7): "Child Lock",
    (6, 8): "Light Mode",
}

# ─── PM10 Expected Differences ──────────────────────────────────────────────
PM10_NOTES = """
╔══════════════════════════════════════════════════════════════════════════╗
║  DREAME PM10 (AirPursue PM10) — Known Feature Differences vs AP10     ║
╠══════════════════════════════════════════════════════════════════════════╣
║  ✓ 10 fan speed levels (AP10 has 5)                                   ║
║  ✓ 3 modes: AI (Auto), Comfort, Pet  (AP10: Auto, Sleep, Custom, Pet)║
║  ✓ Radar presence detection (5m range, 120° coverage)                 ║
║  ✓ Tilt / follow-me airflow (dual-flow modulation)                    ║
║  ✓ Airflow angles: 0°, 45°, 90°, 180°                                ║
║  ✗ NO ionizer                                                         ║
║  ✗ NO LED/buzzer/child lock/light mode toggles                        ║
║  ✓ 7 sensors (PM2.5, formaldehyde, etc.)                              ║
║  ✓ LCD display                                                        ║
╚══════════════════════════════════════════════════════════════════════════╝
"""

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger(__name__)


class DreameCloudProber:
    """Connects to Dreame Cloud and probes device properties."""

    def __init__(self, username: str, password: str, country: str = "us"):
        self._username = username
        self._password = password
        self._country = country
        self._session = requests.Session()
        self._access_token = None
        self._refresh_token = None
        self._uid = None
        self._tenant_id = DREAME_TENANT_ID

    @property
    def api_url(self) -> str:
        return f"https://{self._country}.iot.dreame.tech:13267"

    def login(self) -> bool:
        url = f"{self.api_url}/dreame-auth/oauth/token"
        pw_hash = hashlib.md5(
            (self._password + DREAME_SALT).encode("utf-8")
        ).hexdigest()
        data = (
            f"platform=IOS&scope=all&grant_type=password"
            f"&username={self._username}&password={pw_hash}&type=account"
        )
        headers = {
            "User-Agent": DREAME_USER_AGENT,
            "Authorization": DREAME_AUTH_BASIC,
            "Tenant-Id": DREAME_TENANT_ID,
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "*/*",
        }
        try:
            r = self._session.post(url, headers=headers, data=data, timeout=15)
            if r.status_code == 200:
                result = r.json()
                if "access_token" in result:
                    self._access_token = result["access_token"]
                    self._refresh_token = result.get("refresh_token")
                    self._uid = result.get("uid")
                    self._tenant_id = result.get("tenant_id", DREAME_TENANT_ID)
                    return True
                log.error("Login failed: %s", result)
            else:
                log.error("Login HTTP %s: %s", r.status_code, r.text[:200])
        except Exception as ex:
            log.error("Login error: %s", ex)
        return False

    def _auth_headers(self) -> dict:
        return {
            "User-Agent": DREAME_USER_AGENT,
            "Authorization": DREAME_AUTH_BASIC,
            "Tenant-Id": self._tenant_id,
            "Dreame-Auth": self._access_token,
            "Content-Type": "application/json",
            "Accept": "*/*",
        }

    def get_devices(self) -> list:
        url = f"{self.api_url}/dreame-user-iot/iotuserbind/device/listV2"
        try:
            r = self._session.post(
                url, headers=self._auth_headers(), json={}, timeout=15
            )
            if r.status_code == 200:
                result = r.json()
                if result.get("code") == 0 and "data" in result:
                    return result["data"]["page"]["records"]
        except Exception as ex:
            log.error("get_devices error: %s", ex)
        return []

    def send_command(self, did: str, method: str, params, host: str = None):
        host_prefix = f"-{host.split('.')[0]}" if host else ""
        url = f"{self.api_url}/dreame-iot-com{host_prefix}/device/sendCommand"
        payload = {
            "did": str(did),
            "id": 1,
            "data": {
                "did": str(did),
                "id": 1,
                "method": method,
                "params": params,
            },
        }
        try:
            r = self._session.post(
                url, headers=self._auth_headers(), json=payload, timeout=15
            )
            if r.status_code == 200:
                result = r.json()
                if result.get("code") == 0:
                    if result.get("data") and "result" in result["data"]:
                        return result["data"]["result"]
                    if result.get("success"):
                        return {"code": 0}
                return result  # Return even on non-zero code for debugging
        except Exception as ex:
            log.error("Command error: %s", ex)
        return None

    def get_properties_batch(self, did: str, properties: list, host: str = None):
        """Get multiple properties in one call. Returns raw result list."""
        params = [{"did": str(did), "siid": s, "piid": p} for s, p in properties]
        return self.send_command(did, "get_properties", params, host)

    def call_action(self, did: str, siid: int, aiid: int, params=None, host: str = None):
        """Call an action and return the raw result."""
        action_params = {
            "did": str(did),
            "siid": siid,
            "aiid": aiid,
            "in": params or [],
        }
        return self.send_command(did, "action", action_params, host)


def find_pm10(devices: list) -> dict | None:
    """Find the PM10 among all devices."""
    purifiers = [d for d in devices if ".airp." in d.get("model", "")]
    if not purifiers:
        return None

    # Prefer cvf24a model (PM10), but return any purifier
    for p in purifiers:
        if "cvf24a" in p.get("model", "").lower():
            return p

    # If no exact match, return the first purifier
    return purifiers[0]


def probe_all_properties(prober: DreameCloudProber, did: str, host: str):
    """
    Systematically probe siid 1-20, piid 1-20 to discover all readable properties.
    This covers the standard MiOT service range for most Dreame devices.
    """
    log.info("\n" + "=" * 70)
    log.info("  PHASE 1: FULL PROPERTY SCAN (siid 1-20, piid 1-20)")
    log.info("=" * 70)

    all_results = {}
    total_found = 0

    # Probe in batches of 10 to avoid timeouts
    for siid in range(1, 21):
        batch = [(siid, piid) for piid in range(1, 21)]

        # Split into sub-batches of 10
        for i in range(0, len(batch), 10):
            sub_batch = batch[i : i + 10]
            result = prober.get_properties_batch(did, sub_batch, host)

            if result and isinstance(result, list):
                for prop in result:
                    code = prop.get("code", -1)
                    siid_r = prop.get("siid")
                    piid_r = prop.get("piid")
                    value = prop.get("value")

                    if code == 0 and value is not None:
                        key = (siid_r, piid_r)
                        all_results[key] = {
                            "value": value,
                            "type": type(value).__name__,
                        }
                        total_found += 1

                        # Check if this was known on AP10
                        ap10_label = AP10_KNOWN.get(key, "*** NEW / UNKNOWN ***")
                        log.info(
                            "  ✓ siid=%2d piid=%2d → %s (%s)  [AP10: %s]",
                            siid_r,
                            piid_r,
                            repr(value),
                            type(value).__name__,
                            ap10_label,
                        )

            # Small delay to avoid rate limiting
            time.sleep(0.3)

    log.info("\n  Total readable properties found: %d", total_found)
    return all_results


def probe_extended_properties(prober: DreameCloudProber, did: str, host: str):
    """
    Extended scan for higher siid values (21-40) and higher piid values (21-30).
    Some Dreame devices put custom/vendor-specific services at higher siid values.
    """
    log.info("\n" + "=" * 70)
    log.info("  PHASE 2: EXTENDED PROPERTY SCAN (siid 21-40, piid 1-15)")
    log.info("=" * 70)

    extended_results = {}

    for siid in range(21, 41):
        batch = [(siid, piid) for piid in range(1, 16)]
        for i in range(0, len(batch), 10):
            sub_batch = batch[i : i + 10]
            result = prober.get_properties_batch(did, sub_batch, host)

            if result and isinstance(result, list):
                for prop in result:
                    if prop.get("code", -1) == 0 and prop.get("value") is not None:
                        key = (prop["siid"], prop["piid"])
                        extended_results[key] = {
                            "value": prop["value"],
                            "type": type(prop["value"]).__name__,
                        }
                        log.info(
                            "  ✓ siid=%2d piid=%2d → %s (%s)  [CUSTOM/VENDOR]",
                            prop["siid"],
                            prop["piid"],
                            repr(prop["value"]),
                            type(prop["value"]).__name__,
                        )
            time.sleep(0.3)

    log.info("\n  Extended properties found: %d", len(extended_results))
    return extended_results


def probe_actions(prober: DreameCloudProber, did: str, host: str):
    """
    Test known and potential actions (siid/aiid combinations).
    Only probes actions that are read-safe (no state changes).
    """
    log.info("\n" + "=" * 70)
    log.info("  PHASE 3: ACTION DISCOVERY (safe read-only probes)")
    log.info("=" * 70)
    log.info("  NOTE: We only REPORT action availability, we don't invoke them.")
    log.info("  Actions will be tested with empty params to see if siid/aiid exists.\n")

    # Known AP10 action
    log.info("  Known AP10 action: siid=2 aiid=3 (Toggle Power)")

    # Potential PM10 actions to check existence of
    # We'll try to detect if the action endpoint exists without actually executing
    action_candidates = [
        (2, 1, "Start/Stop"),
        (2, 2, "Unknown action 2.2"),
        (2, 3, "Toggle Power (AP10 known)"),
        (2, 4, "Unknown action 2.4"),
        (2, 5, "Unknown action 2.5"),
        (4, 1, "Reset Filter (AP10 known)"),
        (4, 2, "Unknown action 4.2"),
        (5, 1, "Potential radar/swing action"),
        (5, 2, "Potential tilt action"),
        (6, 1, "Unknown action 6.1"),
        (7, 1, "Unknown action 7.1"),
        (8, 1, "Unknown action 8.1"),
    ]

    log.info("\n  Candidate actions to map (DO NOT EXECUTE blindly):")
    for siid, aiid, label in action_candidates:
        log.info("    siid=%d aiid=%d  — %s", siid, aiid, label)

    return action_candidates


def test_fan_speed_range(prober: DreameCloudProber, did: str, host: str, speed_prop):
    """
    Read the fan speed property to determine current level and validate
    the 1-10 range. Does NOT write any values.
    """
    log.info("\n" + "=" * 70)
    log.info("  PHASE 4: FAN SPEED RANGE DETECTION")
    log.info("=" * 70)

    siid, piid = speed_prop
    result = prober.get_properties_batch(did, [(siid, piid)], host)
    if result and isinstance(result, list):
        for prop in result:
            if prop.get("code", -1) == 0:
                current = prop.get("value")
                log.info("  Current fan speed: %s (siid=%d, piid=%d)", current, siid, piid)
                log.info("  Expected range: 1-10 for PM10 (vs 1-5 for AP10)")
                return current
    log.info("  Could not read fan speed property")
    return None


def test_mode_values(prober: DreameCloudProber, did: str, host: str, mode_prop):
    """
    Read the current mode value. The PM10 is expected to have:
    - AI mode (likely 0 or 1)
    - Comfort mode (likely 2 or a new value)
    - Pet mode (likely 4, same as AP10)
    """
    log.info("\n" + "=" * 70)
    log.info("  PHASE 5: MODE VALUE DETECTION")
    log.info("=" * 70)

    siid, piid = mode_prop
    result = prober.get_properties_batch(did, [(siid, piid)], host)
    if result and isinstance(result, list):
        for prop in result:
            if prop.get("code", -1) == 0:
                current = prop.get("value")
                log.info("  Current mode value: %s (siid=%d, piid=%d)", current, siid, piid)
                log.info("  AP10 modes: 0=Auto, 2=Sleep, 3=Custom, 4=Pet")
                log.info("  PM10 expected: AI (Auto?), Comfort, Pet")
                log.info("")
                log.info("  To discover all mode values, you'll need to:")
                log.info("    1. Use the Dreamehome app to switch to each mode")
                log.info("    2. Run this script after each switch to read the new value")
                log.info("    3. Record the mapping: mode_name → integer_value")
                return current
    return None


def generate_report(
    device_info: dict,
    standard_props: dict,
    extended_props: dict,
    output_file: str,
):
    """Generate a comprehensive report file."""
    all_props = {**standard_props, **extended_props}

    report = []
    report.append("=" * 70)
    report.append(f"  DREAME PM10 PROPERTY DISCOVERY REPORT")
    report.append(f"  Generated: {datetime.now().isoformat()}")
    report.append("=" * 70)
    report.append("")
    report.append(f"  Device: {device_info.get('customName', 'N/A')}")
    report.append(f"  Model:  {device_info.get('model', 'N/A')}")
    report.append(f"  DID:    {device_info.get('did', 'N/A')}")
    report.append(f"  MAC:    {device_info.get('mac', 'N/A')}")
    report.append(f"  Host:   {device_info.get('bindDomain', 'N/A')}")
    report.append("")

    # Property table
    report.append("-" * 70)
    report.append("  ALL DISCOVERED PROPERTIES")
    report.append("-" * 70)
    report.append(f"  {'siid':>4}  {'piid':>4}  {'Value':>20}  {'Type':>8}  AP10 Mapping")
    report.append(f"  {'----':>4}  {'----':>4}  {'----':>20}  {'----':>8}  {'----------'}")

    for (siid, piid) in sorted(all_props.keys()):
        info = all_props[(siid, piid)]
        ap10 = AP10_KNOWN.get((siid, piid), "** UNKNOWN **")
        report.append(
            f"  {siid:4d}  {piid:4d}  {str(info['value']):>20}  {info['type']:>8}  {ap10}"
        )

    report.append("")

    # Comparison with AP10
    report.append("-" * 70)
    report.append("  AP10 PROPERTIES MISSING ON THIS DEVICE")
    report.append("-" * 70)
    for key, label in sorted(AP10_KNOWN.items()):
        if key not in all_props:
            report.append(f"  siid={key[0]:2d} piid={key[1]:2d}  {label}  → NOT FOUND (removed on PM10?)")

    report.append("")
    report.append("-" * 70)
    report.append("  NEW PROPERTIES NOT ON AP10")
    report.append("-" * 70)
    for key in sorted(all_props.keys()):
        if key not in AP10_KNOWN:
            info = all_props[key]
            report.append(
                f"  siid={key[0]:2d} piid={key[1]:2d}  value={info['value']!r:>20}  ({info['type']})"
                f"  → PM10-SPECIFIC, NEEDS INVESTIGATION"
            )

    report.append("")

    # Suggested property map for api.py
    report.append("-" * 70)
    report.append("  SUGGESTED api.py PROPERTY MAP UPDATE")
    report.append("-" * 70)
    report.append("""
# === MiOT Property Map for dreame.airp.cvf24a (Dreame PM10) ===
# DISCOVERED by discover_pm10.py on {date}
#
# TODO: Label each property after testing with the Dreamehome app.
# Workflow:
#   1. Change a setting in the app (e.g., switch to Pet mode)
#   2. Re-run this script to see which property value changed
#   3. Update the labels below
""".format(date=datetime.now().strftime("%Y-%m-%d")))

    for (siid, piid) in sorted(all_props.keys()):
        info = all_props[(siid, piid)]
        ap10 = AP10_KNOWN.get((siid, piid), "UNKNOWN — needs investigation")
        var_name = f"PROP_S{siid}_P{piid}"
        report.append(
            f'PROP_S{siid}_P{piid} = {{"siid": {siid}, "piid": {piid}}}  '
            f'# value={info["value"]!r} ({info["type"]})  [{ap10}]'
        )

    report.append("")

    # Write to file
    report_text = "\n".join(report)
    with open(output_file, "w") as f:
        f.write(report_text)

    log.info("\n  📄 Report saved to: %s", output_file)
    return report_text


def interactive_mode_discovery(prober, did, host, mode_prop):
    """
    Interactive helper: waits for you to change the mode in the app,
    then reads the new value.
    """
    log.info("\n" + "=" * 70)
    log.info("  INTERACTIVE MODE DISCOVERY")
    log.info("=" * 70)
    log.info("  Switch modes in the Dreamehome app, then press Enter here.")
    log.info("  Type 'done' when finished.\n")

    mode_map = {}
    siid, piid = mode_prop

    while True:
        mode_name = input("  Mode name (or 'done'): ").strip()
        if mode_name.lower() == "done":
            break

        result = prober.get_properties_batch(did, [(siid, piid)], host)
        if result and isinstance(result, list):
            for prop in result:
                if prop.get("code", -1) == 0:
                    val = prop["value"]
                    mode_map[mode_name] = val
                    log.info("    → %s = %d", mode_name, val)

    if mode_map:
        log.info("\n  Discovered mode map:")
        for name, val in mode_map.items():
            log.info("    MODE_%s = %d", name.upper().replace(" ", "_"), val)

    return mode_map


def main():
    parser = argparse.ArgumentParser(
        description="Dreame PM10 MiOT Property Discovery Tool",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=PM10_NOTES,
    )
    parser.add_argument("--username", "-u", required=True, help="Dreame account email/phone")
    parser.add_argument("--password", "-p", required=True, help="Dreame account password")
    parser.add_argument("--country", "-c", default="us", choices=["us", "cn", "eu", "sg", "kr"],
                        help="Country/region (default: us)")
    parser.add_argument("--output", "-o", default="tools/pm10_discovery_report.txt",
                        help="Output report file path")
    parser.add_argument("--interactive", "-i", action="store_true",
                        help="Enable interactive mode discovery (switch modes in app)")
    parser.add_argument("--extended", "-e", action="store_true",
                        help="Also scan siid 21-40 (vendor-specific services)")
    parser.add_argument("--json", "-j", action="store_true",
                        help="Also output raw JSON data")
    args = parser.parse_args()

    print(PM10_NOTES)

    # ── Step 1: Login ────────────────────────────────────────────────────
    log.info("Step 1: Logging into Dreame Cloud (%s)...", args.country)
    prober = DreameCloudProber(args.username, args.password, args.country)
    if not prober.login():
        log.error("❌ Login failed. Check credentials and country setting.")
        sys.exit(1)
    log.info("✅ Login successful!")

    # ── Step 2: Discover devices ─────────────────────────────────────────
    log.info("\nStep 2: Discovering devices...")
    devices = prober.get_devices()
    if not devices:
        log.error("❌ No devices found on this account.")
        sys.exit(1)

    log.info("  Found %d device(s):", len(devices))
    for d in devices:
        log.info(
            "    • %s  model=%s  did=%s",
            d.get("customName", d.get("deviceInfo", {}).get("displayName", "?")),
            d.get("model", "?"),
            d.get("did", "?"),
        )

    # ── Step 3: Find PM10 ───────────────────────────────────────────────
    pm10 = find_pm10(devices)
    if not pm10:
        log.error("❌ No air purifier (.airp.) found. Available models:")
        for d in devices:
            log.error("    %s", d.get("model"))
        sys.exit(1)

    did = str(pm10["did"])
    host = pm10.get("bindDomain")
    model = pm10.get("model", "?")
    name = pm10.get("customName", "")

    log.info("\n✅ Found purifier: %s (%s) did=%s host=%s", name, model, did, host)

    # ── Step 4: Probe all properties ─────────────────────────────────────
    log.info("\nStep 3: Probing ALL properties (this takes ~30 seconds)...")
    standard_props = probe_all_properties(prober, did, host)

    extended_props = {}
    if args.extended:
        extended_props = probe_extended_properties(prober, did, host)

    # ── Step 5: Test specific PM10 features ──────────────────────────────
    # Try to detect fan speed and mode properties
    speed_prop = None
    mode_prop = None

    for key in [(2, 4), (2, 3)]:  # AP10 fan speed / mode locations
        if key in standard_props:
            if key == (2, 4):
                speed_prop = key
            elif key == (2, 3):
                mode_prop = key

    if speed_prop:
        test_fan_speed_range(prober, did, host, speed_prop)

    if mode_prop:
        test_mode_values(prober, did, host, mode_prop)

    # ── Step 6: Probe actions ────────────────────────────────────────────
    probe_actions(prober, did, host)

    # ── Step 7: Generate report ──────────────────────────────────────────
    report = generate_report(pm10, standard_props, extended_props, args.output)
    print("\n" + report)

    # ── Step 8: JSON output ──────────────────────────────────────────────
    if args.json:
        json_file = args.output.replace(".txt", ".json")
        json_data = {
            "device": {
                "name": name,
                "model": model,
                "did": did,
                "mac": pm10.get("mac", ""),
                "host": host,
            },
            "properties": {
                f"siid{k[0]}_piid{k[1]}": {
                    "siid": k[0],
                    "piid": k[1],
                    "value": v["value"],
                    "type": v["type"],
                    "ap10_label": AP10_KNOWN.get(k, None),
                }
                for k, v in {**standard_props, **extended_props}.items()
            },
            "timestamp": datetime.now().isoformat(),
        }
        with open(json_file, "w") as f:
            json.dump(json_data, f, indent=2)
        log.info("  📄 JSON data saved to: %s", json_file)

    # ── Step 9: Interactive mode ─────────────────────────────────────────
    if args.interactive and mode_prop:
        interactive_mode_discovery(prober, did, host, mode_prop)

    # ── Summary ──────────────────────────────────────────────────────────
    log.info("\n" + "=" * 70)
    log.info("  NEXT STEPS")
    log.info("=" * 70)
    log.info("""
  1. Review the report at: %s
  2. For UNKNOWN properties, use the Dreamehome app to toggle settings
     one at a time, then re-run this script to see which value changed.
  3. To discover mode values specifically, run with --interactive:
       python3 tools/discover_pm10.py -u EMAIL -p PASS --interactive
  4. Once you have the full property map, update api.py:
     - Change fan speed range from 1-5 to 1-10
     - Update mode constants (AI/Comfort/Pet)
     - Remove ionizer/LED/buzzer/child_lock if not found
     - Add radar/tilt/follow properties
  5. Update const.py PRESET_MODES and fan.py speed_count accordingly.
""", args.output)


if __name__ == "__main__":
    main()
