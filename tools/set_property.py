#!/usr/bin/env python3
"""
Dreame air purifier — Set Property Value

Directly set a siid/piid property or call an action on the device.

Usage:
    # Set a property
    python3 tools/set_property.py -u EMAIL -p PASS --siid 2 --piid 4 --value 5

    # Set with explicit type (auto-detected by default)
    python3 tools/set_property.py -u EMAIL -p PASS --siid 2 --piid 3 --value 0 --type int

    # Call an action (e.g. toggle power)
    python3 tools/set_property.py -u EMAIL -p PASS --siid 2 --aiid 3 --action

    # Read a property first (dry-run / check current value)
    python3 tools/set_property.py -u EMAIL -p PASS --siid 2 --piid 4 --read
"""

import argparse
import hashlib
import json
import requests
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from known_props import request_id, unsafe_for  # noqa: E402

DREAME_SALT = "RAylYC%fmSKp7%Tq"
DREAME_USER_AGENT = "Dreame_Smarthome/2.1.9 (iPhone; iOS 18.4.1; Scale/3.00)"
DREAME_AUTH_BASIC = "Basic ZHJlYW1lX2FwcHYxOkFQXmR2QHpAU1FZVnhOODg="
DREAME_TENANT_ID = "000000"

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"


class DreameClient:
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

    def _send(self, did, method, params, host=None):
        host_prefix = f"-{host.split('.')[0]}" if host else ""
        rid = request_id()
        payload = {
            "did": str(did),
            "id": rid,
            "data": {"did": str(did), "id": rid, "method": method, "params": params},
        }
        r = self._session.post(
            f"{self.api_url}/dreame-iot-com{host_prefix}/device/sendCommand",
            headers=self._headers(),
            json=payload,
            timeout=15,
        )
        if r.status_code == 200:
            return r.json()
        return {"error": f"HTTP {r.status_code}", "body": r.text[:300]}

    def get_property(self, did, siid, piid, host=None):
        params = [{"did": str(did), "siid": siid, "piid": piid}]
        return self._send(did, "get_properties", params, host)

    def set_property(self, did, siid, piid, value, host=None):
        params = [{"did": str(did), "siid": siid, "piid": piid, "value": value}]
        return self._send(did, "set_properties", params, host)

    def call_action(self, did, siid, aiid, action_params=None, host=None):
        params = {"did": str(did), "siid": siid, "aiid": aiid, "in": action_params or []}
        return self._send(did, "action", params, host)


def parse_value(raw: str, force_type: str = None):
    """Auto-detect or coerce value type."""
    if force_type == "str":
        return raw
    if force_type == "int":
        return int(raw)
    if force_type == "float":
        return float(raw)
    if force_type == "bool":
        return raw.lower() in ("true", "1", "yes", "on")

    # Auto-detect
    if raw.lower() in ("true", "false"):
        return raw.lower() == "true"
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def main():
    parser = argparse.ArgumentParser(
        description="Dreame air purifier — Set/Read Property or Call Action",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Read current fan speed
  python3 tools/set_property.py -u EMAIL -p PASS --siid 2 --piid 4 --read

  # Set fan speed to 7
  python3 tools/set_property.py -u EMAIL -p PASS --siid 2 --piid 4 --value 7

  # Set mode to 0 (Auto/AI)
  python3 tools/set_property.py -u EMAIL -p PASS --siid 2 --piid 3 --value 0

  # Toggle power (action)
  python3 tools/set_property.py -u EMAIL -p PASS --siid 2 --aiid 3 --action
        """,
    )
    parser.add_argument("--username", "-u", required=True)
    parser.add_argument("--password", "-p", required=True)
    parser.add_argument("--country", "-c", default="us")
    parser.add_argument("--siid", type=int, required=True, help="Service ID")
    parser.add_argument("--piid", type=int, default=None, help="Property ID (for get/set)")
    parser.add_argument("--aiid", type=int, default=None, help="Action ID (for --action)")
    parser.add_argument("--value", "-v", default=None, help="Value to set")
    parser.add_argument("--type", "-t", choices=["int", "float", "str", "bool"], default=None,
                        help="Force value type (auto-detected by default)")
    parser.add_argument("--read", "-r", action="store_true", help="Read the property value")
    parser.add_argument("--action", "-a", action="store_true", help="Call an action (uses --siid/--aiid)")
    parser.add_argument("--force", action="store_true",
                        help="Read/write even a property known to crash this model (see UNSAFE_PROPS)")
    parser.add_argument("--action-params", default=None,
                        help="JSON array of action input params, e.g. '[1, 2]'")
    args = parser.parse_args()

    # Validate args
    if args.action:
        if args.aiid is None:
            parser.error("--action requires --aiid")
    elif args.read:
        if args.piid is None:
            parser.error("--read requires --piid")
    else:
        if args.piid is None or args.value is None:
            parser.error("Provide --piid and --value to set, or use --read / --action")

    # Login
    client = DreameClient(args.username, args.password, args.country)
    if not client.login():
        print(f"{RED}❌ Login failed{RESET}")
        sys.exit(1)
    print(f"{GREEN}✅ Logged in{RESET}")

    # Find purifier
    devices = client.get_devices()
    purifiers = [d for d in devices if ".airp." in d.get("model", "")]
    if not purifiers:
        print(f"{RED}❌ No air purifier found{RESET}")
        sys.exit(1)

    dev = purifiers[0]
    did = str(dev["did"])
    host = dev.get("bindDomain")
    print(f"{GREEN}✅ Device: {dev.get('customName', '?')} ({dev.get('model', '?')}){RESET}\n")

    # Reading (which a set also does first) some properties crashes some models.
    if not args.action and (args.siid, args.piid) in unsafe_for(dev.get("model", "")):
        if not args.force:
            print(f"{RED}❌ {args.siid}.{args.piid} is known to crash {dev.get('model')} when read "
                  f"(UNSAFE_PROPS in const.py). Not sending anything.{RESET}")
            print("   Re-run with --force if you really mean it.")
            sys.exit(1)
        print(f"{YELLOW}⚠️  --force: sending {args.siid}.{args.piid} although it's known to crash "
              f"{dev.get('model')}. Expect it to restart and come back switched off.{RESET}")

    if args.action:
        # ── Call Action ──────────────────────────────────────────────
        action_in = json.loads(args.action_params) if args.action_params else []
        print(f"{CYAN}Calling action siid={args.siid} aiid={args.aiid} in={action_in}{RESET}")
        result = client.call_action(did, args.siid, args.aiid, action_in, host)
        print(f"\n{BOLD}Result:{RESET}")
        print(json.dumps(result, indent=2))

    elif args.read:
        # ── Read Property ────────────────────────────────────────────
        print(f"{CYAN}Reading siid={args.siid} piid={args.piid}{RESET}")
        result = client.get_property(did, args.siid, args.piid, host)
        print(f"\n{BOLD}Result:{RESET}")
        print(json.dumps(result, indent=2))

        # Extract value
        if isinstance(result, dict) and result.get("code") == 0:
            data = result.get("data", {})
            if "result" in data and isinstance(data["result"], list):
                for prop in data["result"]:
                    if prop.get("code", -1) == 0 and (prop.get("siid"), prop.get("piid")) == (args.siid, args.piid):
                        print(f"\n{GREEN}Value: {prop['value']!r} ({type(prop['value']).__name__}){RESET}")

    else:
        # ── Set Property ─────────────────────────────────────────────
        typed_value = parse_value(args.value, args.type)
        print(f"{CYAN}Reading current value of siid={args.siid} piid={args.piid}...{RESET}")
        before = client.get_property(did, args.siid, args.piid, host)
        old_val = None
        if isinstance(before, dict) and before.get("code") == 0:
            data = before.get("data", {})
            if "result" in data and isinstance(data["result"], list):
                for prop in data["result"]:
                    if prop.get("code", -1) == 0 and (prop.get("siid"), prop.get("piid")) == (args.siid, args.piid):
                        old_val = prop["value"]

        print(f"  Current: {old_val!r}")
        print(f"  Setting: {typed_value!r} ({type(typed_value).__name__})")
        print()

        result = client.set_property(did, args.siid, args.piid, typed_value, host)
        print(f"{BOLD}Result:{RESET}")
        print(json.dumps(result, indent=2))

        # Check success
        success = False
        if isinstance(result, dict) and result.get("code") == 0:
            data = result.get("data", {})
            if "result" in data and isinstance(data["result"], list):
                for prop in data["result"]:
                    if prop.get("code", -1) == 0 and (prop.get("siid"), prop.get("piid")) == (args.siid, args.piid):
                        success = True

        if success:
            print(f"\n{GREEN}✅ Set siid={args.siid} piid={args.piid} = {typed_value!r}{RESET}")

            # Read back to verify
            time.sleep(0.5)
            after = client.get_property(did, args.siid, args.piid, host)
            if isinstance(after, dict) and after.get("code") == 0:
                data = after.get("data", {})
                if "result" in data and isinstance(data["result"], list):
                    for prop in data["result"]:
                        if prop.get("code", -1) == 0 and (prop.get("siid"), prop.get("piid")) == (args.siid, args.piid):
                            print(f"{GREEN}   Verified: {prop['value']!r}{RESET}")
        else:
            print(f"\n{RED}❌ Set may have failed. Check result above.{RESET}")


if __name__ == "__main__":
    main()
