#!/usr/bin/env python3
"""
Dreame air purifier — Live Property Monitor / Diff Tool

Continuously polls ALL discovered properties and highlights changes.
This is the fastest way to figure out which siid/piid maps to which feature:
  1. Run this script
  2. Change a setting in the Dreamehome app
  3. See which property value changed in the terminal

Usage:
    python3 tools/monitor_properties.py --username EMAIL --password PASS [--interval 5]
"""

import argparse
import hashlib
import json
import os
import requests
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from known_props import load_known_props, unsafe_for  # noqa: E402

DREAME_SALT = "RAylYC%fmSKp7%Tq"
DREAME_USER_AGENT = "Dreame_Smarthome/2.1.9 (iPhone; iOS 18.4.1; Scale/3.00)"
DREAME_AUTH_BASIC = "Basic ZHJlYW1lX2FwcHYxOkFQXmR2QHpAU1FZVnhOODg="
DREAME_TENANT_ID = "000000"

# ANSI colors
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


class DreameMonitor:
    def __init__(self, username, password, country="us"):
        self._username = username
        self._password = password
        self._country = country
        self._session = requests.Session()
        self._access_token = None
        self._tenant_id = DREAME_TENANT_ID

    @property
    def api_url(self):
        return f"https://{self._country}.iot.dreame.tech:13267"

    def login(self):
        pw_hash = hashlib.md5((self._password + DREAME_SALT).encode()).hexdigest()
        r = self._session.post(
            f"{self.api_url}/dreame-auth/oauth/token",
            headers={
                "User-Agent": DREAME_USER_AGENT,
                "Authorization": DREAME_AUTH_BASIC,
                "Tenant-Id": DREAME_TENANT_ID,
                "Content-Type": "application/x-www-form-urlencoded",
            },
            data=f"platform=IOS&scope=all&grant_type=password&username={self._username}&password={pw_hash}&type=account",
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            if "access_token" in data:
                self._access_token = data["access_token"]
                self._tenant_id = data.get("tenant_id", DREAME_TENANT_ID)
                return True
        return False

    def _headers(self):
        return {
            "User-Agent": DREAME_USER_AGENT,
            "Authorization": DREAME_AUTH_BASIC,
            "Tenant-Id": self._tenant_id,
            "Dreame-Auth": self._access_token,
            "Content-Type": "application/json",
        }

    def get_devices(self):
        r = self._session.post(
            f"{self.api_url}/dreame-user-iot/iotuserbind/device/listV2",
            headers=self._headers(),
            json={},
            timeout=15,
        )
        if r.status_code == 200:
            data = r.json()
            if data.get("code") == 0:
                return data["data"]["page"]["records"]
        return []

    def get_properties(self, did, props, host=None):
        host_prefix = f"-{host.split('.')[0]}" if host else ""
        params = [{"did": str(did), "siid": s, "piid": p} for s, p in props]
        payload = {
            "did": str(did),
            "id": 1,
            "data": {"did": str(did), "id": 1, "method": "get_properties", "params": params},
        }
        try:
            r = self._session.post(
                f"{self.api_url}/dreame-iot-com{host_prefix}/device/sendCommand",
                headers=self._headers(),
                json=payload,
                timeout=15,
            )
            if r.status_code == 200:
                data = r.json()
                if data.get("code") == 0 and data.get("data") and "result" in data["data"]:
                    return data["data"]["result"]
        except Exception:
            pass
        return None

    def discover_properties(self, did, host, max_siid=20, max_piid=20, skip=()):
        """Initial scan to find all readable properties. Never requests anything in skip."""
        found = []
        for siid in range(1, max_siid + 1):
            batch = [(siid, piid) for piid in range(1, max_piid + 1) if (siid, piid) not in skip]
            for i in range(0, len(batch), 10):
                result = self.get_properties(did, batch[i : i + 10], host)
                if result and isinstance(result, list):
                    for prop in result:
                        if prop.get("code", -1) == 0 and prop.get("value") is not None:
                            found.append((prop["siid"], prop["piid"]))
                time.sleep(0.2)
        return found

    def poll_snapshot(self, did, host, props):
        """Get current values for all known properties."""
        snapshot = {}
        # Poll in batches of 10
        for i in range(0, len(props), 10):
            batch = props[i : i + 10]
            result = self.get_properties(did, batch, host)
            if result and isinstance(result, list):
                for prop in result:
                    if prop.get("code", -1) == 0:
                        snapshot[(prop["siid"], prop["piid"])] = prop.get("value")
        return snapshot


class RangeTracker:
    """Tracks min/max for numeric values and unique set for all values per property."""

    def __init__(self):
        self._data = {}  # key -> {"min": ..., "max": ..., "values": set}

    def update(self, snapshot: dict):
        for key, val in snapshot.items():
            if key not in self._data:
                self._data[key] = {"min": None, "max": None, "values": set()}
            entry = self._data[key]
            try:
                entry["values"].add(val)
            except TypeError:
                pass  # unhashable
            if isinstance(val, (int, float)):
                if entry["min"] is None or val < entry["min"]:
                    entry["min"] = val
                if entry["max"] is None or val > entry["max"]:
                    entry["max"] = val

    def range_str(self, key):
        entry = self._data.get(key)
        if not entry:
            return ""
        if entry["min"] is not None:
            return f"[{entry['min']}..{entry['max']}]"
        # Non-numeric — show unique values
        vals = sorted(entry["values"], key=lambda v: str(v))
        if len(vals) <= 5:
            return "{" + ", ".join(repr(v) for v in vals) + "}"
        return f"{{{len(vals)} distinct}}"

    def print_summary(self, labels=None):
        labels = labels or {}
        print(f"\n{BOLD}{CYAN}{'═' * 72}{RESET}")
        print(f"{BOLD}{CYAN}  OBSERVED RANGES (this session){RESET}")
        print(f"{BOLD}{CYAN}{'═' * 72}{RESET}")
        print(f"  {'siid':>4}  {'piid':>4}  {'Range / Values':<30}  {'#':>3}  Label")
        print(f"  {'────':>4}  {'────':>4}  {'──────────────':<30}  {'───':>3}  ─────")
        for key in sorted(self._data.keys()):
            entry = self._data[key]
            label = labels.get(key, "")
            n = len(entry["values"])
            rng = self.range_str(key)
            print(f"  {key[0]:4d}  {key[1]:4d}  {rng:<30}  {n:3d}  {label}")
        print()


def print_diff(prev, curr, labels=None, ranges=None):
    """Print differences between two snapshots."""
    labels = labels or {}
    changes = []

    for key in sorted(set(list(prev.keys()) + list(curr.keys()))):
        old = prev.get(key)
        new = curr.get(key)
        if old != new:
            label = labels.get(key, "")
            changes.append((key, old, new, label))

    if changes:
        print(f"\n{BOLD}{YELLOW}{'─' * 60}{RESET}")
        print(f"{BOLD}{YELLOW}  ⚡ CHANGES DETECTED at {datetime.now().strftime('%H:%M:%S')}{RESET}")
        print(f"{BOLD}{YELLOW}{'─' * 60}{RESET}")
        for key, old, new, label in changes:
            siid, piid = key
            label_str = f"  {CYAN}({label}){RESET}" if label else ""
            range_str = ""
            if ranges:
                r = ranges.range_str(key)
                if r:
                    range_str = f"  {YELLOW}{r}{RESET}"
            print(
                f"  siid={siid:2d} piid={piid:2d}:  "
                f"{RED}{old!r}{RESET} → {GREEN}{new!r}{RESET}"
                f"{label_str}{range_str}"
            )
        print()
    return changes


def main():
    parser = argparse.ArgumentParser(description="Dreame air purifier Live Property Monitor")
    parser.add_argument("--username", "-u", required=True)
    parser.add_argument("--password", "-p", required=True)
    parser.add_argument("--country", "-c", default="us")
    parser.add_argument("--interval", "-i", type=int, default=5, help="Poll interval in seconds")
    parser.add_argument("--log", "-l", default="tools/property_changes.log", help="Log file for changes")
    parser.add_argument(
        "--ignore-siid", "-s",
        type=int, action="append", dest="ignore_siids", default=[], metavar="SIID",
        help="Ignore all properties from this siid (repeatable, e.g. -s 3 -s 5)",
    )
    parser.add_argument(
        "--full-scan", action="store_true",
        help="Scan siid 1-20 / piid 1-20 even on models known to crash on some reads "
             "(unsafe properties are still skipped)",
    )
    args = parser.parse_args()
    ignore_siids = set(args.ignore_siids)

    print(f"\n{BOLD}{CYAN}╔══════════════════════════════════════════════════════════╗{RESET}")
    print(f"{BOLD}{CYAN}║   Dreame Purifier — Live Property Monitor               ║{RESET}")
    print(f"{BOLD}{CYAN}║   Change settings in the Dreamehome app to see diffs    ║{RESET}")
    print(f"{BOLD}{CYAN}╚══════════════════════════════════════════════════════════╝{RESET}\n")

    # Login
    mon = DreameMonitor(args.username, args.password, args.country)
    if not mon.login():
        print(f"{RED}❌ Login failed{RESET}")
        sys.exit(1)
    print(f"{GREEN}✅ Logged in{RESET}")

    # Find device
    devices = mon.get_devices()
    purifiers = [d for d in devices if ".airp." in d.get("model", "")]
    if not purifiers:
        print(f"{RED}❌ No air purifier found{RESET}")
        sys.exit(1)

    dev = purifiers[0]
    did = str(dev["did"])
    host = dev.get("bindDomain")
    print(f"{GREEN}✅ Found: {dev.get('customName', '?')} ({dev.get('model', '?')}){RESET}")

    # Labels from the integration's property map
    labels = load_known_props()

    model = dev.get("model", "?")
    unsafe = unsafe_for(model)
    if unsafe:
        print(f"{YELLOW}Never reading on {model} (known to crash it): "
              f"{', '.join(f'{s}.{p}' for s, p in sorted(unsafe))}{RESET}")

    if unsafe and not args.full_scan:
        # Fragile model: don't fire ~40 batched requests at it. Watch only the
        # properties the integration knows; use safe_probe.py --scan to find more.
        print(f"\n{CYAN}Watching the integration's known properties only "
              f"(--full-scan to scan everything; tools/safe_probe.py --scan is safer){RESET}")
        candidates = [k for k in sorted(labels) if k not in unsafe]
        first = mon.poll_snapshot(did, host, candidates)
        props = sorted(first)  # keep only the ones this device actually has
    else:
        print(f"\n{CYAN}Scanning all properties (siid 1-20, piid 1-20)...{RESET}")
        props = mon.discover_properties(did, host, skip=unsafe)
    if ignore_siids:
        props = [(s, p) for s, p in props if s not in ignore_siids]
        print(f"{GREEN}✅ Found {len(props)} readable properties "
              f"(ignoring siid {sorted(ignore_siids)}){RESET}\n")
    else:
        print(f"{GREEN}✅ Found {len(props)} readable properties{RESET}\n")

    # Range tracker
    ranges = RangeTracker()

    # Show initial snapshot
    print(f"{BOLD}Current property values:{RESET}")
    prev = mon.poll_snapshot(did, host, props)
    ranges.update(prev)
    for key in sorted(prev.keys()):
        label = labels.get(key, "")
        label_str = f"  {CYAN}({label}){RESET}" if label else ""
        print(f"  siid={key[0]:2d} piid={key[1]:2d} = {prev[key]!r}{label_str}")

    print(f"\n{BOLD}Monitoring for changes every {args.interval}s... (Ctrl+C to stop){RESET}")
    print(f"{BOLD}Change settings in the Dreamehome app and watch here!{RESET}\n")

    # Open log file
    os.makedirs(os.path.dirname(args.log), exist_ok=True)
    log = open(args.log, "a")
    log.write(f"\n--- Session started {datetime.now().isoformat()} ---\n")

    try:
        while True:
            time.sleep(args.interval)
            curr = mon.poll_snapshot(did, host, props)
            ranges.update(curr)
            changes = print_diff(prev, curr, labels, ranges)

            if changes:
                for key, old, new, label in changes:
                    log.write(
                        f"{datetime.now().isoformat()}  "
                        f"siid={key[0]} piid={key[1]}  "
                        f"{old!r} → {new!r}  {label}\n"
                    )
                    log.flush()

            prev = curr

    except KeyboardInterrupt:
        ranges.print_summary(labels)
        print(f"{CYAN}Changes logged to: {args.log}{RESET}")
        log.close()


if __name__ == "__main__":
    main()
