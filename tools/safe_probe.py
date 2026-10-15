#!/usr/bin/env python3
"""
Dreame air purifier — slow, one-at-a-time property probe.

For devices that misbehave (e.g. reboot) when polled. Reads the properties the
integration knows about ONE AT A TIME, waits between reads, and checks the
device still answers before moving on. Stops at the first sign of trouble and
tells you which read came just before it.

Reads only — never writes a property or calls an action.

Usage:
    # Step 1: single reads, 20 s apart (default)
    python3 tools/safe_probe.py -u EMAIL -p 'PASSWORD' --country sg

    # Wait for Enter after each read, so you can look at the purifier first
    python3 tools/safe_probe.py -u EMAIL -p 'PASSWORD' --country sg --confirm

    # Resume after a stop, from a given property (siid.piid)
    python3 tools/safe_probe.py -u EMAIL -p 'PASSWORD' --country sg --start 3.5

    # Step 2 (only if every single read was fine): batched reads like the integration
    python3 tools/safe_probe.py -u EMAIL -p 'PASSWORD' --country sg --batch 5

The device's ID and MAC are never printed.
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from known_props import load_known_props  # noqa: E402
from set_property import DreameClient, GREEN, RED, YELLOW, CYAN, BOLD, RESET  # noqa: E402

HEALTH_PROP = (2, 1)  # power — a single read of this is known to be safe
HEALTH_RETRIES = 6    # how many times to re-check a silent device before stopping
HEALTH_RETRY_WAIT = 10


def ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def read_props(client, did, host, keys):
    """Read properties in one request. Returns ({key: (code, value)}, error_or_None)."""
    params = [{"did": str(did), "siid": s, "piid": p} for s, p in keys]
    try:
        resp = client._send(did, "get_properties", params, host)
    except Exception as ex:  # network errors, timeouts
        return {}, f"request failed: {ex}"
    if not isinstance(resp, dict) or resp.get("code") != 0:
        return {}, f"cloud returned {resp.get('code') if isinstance(resp, dict) else resp!r}: {resp.get('msg') if isinstance(resp, dict) else ''}"
    results = (resp.get("data") or {}).get("result")
    if not isinstance(results, list):
        return {}, "no result from device (offline or not answering)"
    out = {}
    for r in results:
        out[(r.get("siid"), r.get("piid"))] = (r.get("code"), r.get("value"))
    return out, None


def device_answers(client, did, host) -> bool:
    res, err = read_props(client, did, host, [HEALTH_PROP])
    return err is None and res.get(HEALTH_PROP, (None,))[0] == 0


def wait_for_health(client, did, host) -> bool:
    """True if the device answers now or within HEALTH_RETRIES checks."""
    if device_answers(client, did, host):
        return True
    for i in range(HEALTH_RETRIES):
        print(f"  {YELLOW}{ts()}  device not answering, re-checking in {HEALTH_RETRY_WAIT}s ({i + 1}/{HEALTH_RETRIES}){RESET}")
        time.sleep(HEALTH_RETRY_WAIT)
        if device_answers(client, did, host):
            return True
    return False


def main():
    parser = argparse.ArgumentParser(description="Slow, one-at-a-time property probe (reads only)")
    parser.add_argument("--username", "-u", required=True)
    parser.add_argument("--password", "-p", required=True)
    parser.add_argument("--country", "-c", default="us", choices=["us", "cn", "eu", "sg", "kr"])
    parser.add_argument("--delay", "-d", type=int, default=20, help="Seconds to wait after each read (default 20)")
    parser.add_argument("--confirm", action="store_true", help="Wait for Enter after each read")
    parser.add_argument("--start", default=None, help="Resume from this property, e.g. 3.5")
    parser.add_argument("--batch", type=int, default=1, help="Properties per request (default 1)")
    args = parser.parse_args()

    known = load_known_props()
    if not known:
        print(f"{RED}❌ Could not load the integration's property list{RESET}")
        sys.exit(1)
    keys = sorted(known)
    if args.start:
        try:
            s, p = (int(x) for x in args.start.split("."))
        except ValueError:
            parser.error("--start must look like 3.5")
        keys = [k for k in keys if k >= (s, p)]

    client = DreameClient(args.username, args.password, args.country)
    if not client.login():
        print(f"{RED}❌ Login failed{RESET}")
        sys.exit(1)
    purifiers = [d for d in client.get_devices() if ".airp." in d.get("model", "")]
    if not purifiers:
        print(f"{RED}❌ No air purifier found{RESET}")
        sys.exit(1)
    dev = purifiers[0]
    did, host = str(dev["did"]), dev.get("bindDomain")
    print(f"{GREEN}✅ Device: {dev.get('customName') or '?'} ({dev.get('model', '?')}){RESET}")

    batches = [keys[i:i + args.batch] for i in range(0, len(keys), args.batch)]
    print(f"{BOLD}Reading {len(keys)} properties, {args.batch} per request, {args.delay}s apart. Reads only.{RESET}")
    print("Watch the purifier. If it restarts, note the time — each read is timestamped.\n")

    if not wait_for_health(client, did, host):
        print(f"{RED}❌ Device isn't answering even before the first read. Check it's on and online in the app.{RESET}")
        sys.exit(1)

    results = {}
    for batch in batches:
        label = ", ".join(f"{s}.{p} {known[(s, p)]}" for s, p in batch)
        print(f"{CYAN}{ts()}  reading {label}{RESET}")
        res, err = read_props(client, did, host, batch)
        if err:
            print(f"  {YELLOW}{err}{RESET}")
        for k in batch:
            code, value = res.get(k, (None, None))
            results[k] = (code, value)
            if code == 0:
                print(f"  {GREEN}{k[0]}.{k[1]} {known[k]} = {value!r}{RESET}")
            elif code is not None:
                print(f"  {YELLOW}{k[0]}.{k[1]} {known[k]}: code {code} (device doesn't have it?){RESET}")

        if args.confirm:
            input("  Purifier still OK? Press Enter to continue, Ctrl+C to stop. ")
        else:
            time.sleep(args.delay)

        if not wait_for_health(client, did, host):
            nxt = batch[0]
            print(f"\n{RED}{BOLD}⛔ Device stopped answering after reading: {label}{RESET}")
            print(f"{RED}   Likely trigger. Wait for it to come back, then resume after it with:{RESET}")
            later = [k for k in keys if k > batch[-1]]
            if later:
                print(f"   python {sys.argv[0]} -u EMAIL -p 'PASSWORD' --country {args.country} --start {later[0][0]}.{later[0][1]}")
            print(f"   (first property in the batch that stopped it: {nxt[0]}.{nxt[1]})")
            break
    else:
        print(f"\n{GREEN}{BOLD}✅ Device kept answering through every read.{RESET}")

    print(f"\n{BOLD}Summary{RESET} (share this — it has no device ID or MAC)")
    for k in keys:
        if k not in results:
            continue
        code, value = results[k]
        status = f"= {value!r}" if code == 0 else ("no answer" if code is None else f"code {code}")
        print(f"  {k[0]:>2}.{k[1]:<2}  {known[k]:<24} {status}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Stopped.{RESET}")
