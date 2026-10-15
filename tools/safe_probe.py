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

    # Leave out properties known to crash the device
    python3 tools/safe_probe.py -u EMAIL -p 'PASSWORD' --country sg --skip 3.10

    # Step 2 (only if every single read was fine): batched reads like the integration
    python3 tools/safe_probe.py -u EMAIL -p 'PASSWORD' --country sg --batch 5

    # Look for properties the integration doesn't know: every siid/piid in a range,
    # one at a time (here siid 1-8, piid 1-20, 5 s apart)
    python3 tools/safe_probe.py -u EMAIL -p 'PASSWORD' --country sg --scan --siids 1-8 --piids 1-20 --delay 5

Properties listed for the model in UNSAFE_PROPS (custom_components/dreame_airpurifier/const.py)
are always skipped. The device's ID and MAC are never printed, but scanned values can
include things like the device's time zone or location, so check before sharing.
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from known_props import load_known_props, unsafe_for  # noqa: E402
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
    parser.add_argument("--skip", default="", help="Comma-separated properties to leave out, e.g. 3.10,6.2")
    parser.add_argument("--scan", action="store_true",
                        help="Probe every siid/piid in --siids x --piids instead of the integration's known properties")
    parser.add_argument("--siids", default="1-8", help="siid range for --scan (default 1-8)")
    parser.add_argument("--piids", default="1-20", help="piid range for --scan (default 1-20)")
    args = parser.parse_args()

    def parse_range(text):
        try:
            lo, _, hi = text.partition("-")
            lo, hi = int(lo), int(hi or lo)
            return range(lo, hi + 1)
        except ValueError:
            parser.error(f"{text!r} should look like 1-8")

    def parse_key(text):
        try:
            s, p = (int(x) for x in text.strip().split("."))
            return (s, p)
        except ValueError:
            parser.error(f"{text!r} should look like 3.10")

    known = load_known_props()
    if not known and not args.scan:
        print(f"{RED}❌ Could not load the integration's property list{RESET}")
        sys.exit(1)

    def label_of(k):
        return known.get(k, "?")

    skip = {parse_key(t) for t in args.skip.split(",") if t.strip()}

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
    model = dev.get("model", "?")
    print(f"{GREEN}✅ Device: {dev.get('customName') or '?'} ({model}){RESET}")

    unsafe = unsafe_for(model)
    if unsafe:
        print(f"{YELLOW}Always skipping for {model} (known to crash it): "
              f"{', '.join(f'{s}.{p}' for s, p in sorted(unsafe))}{RESET}")
    skip |= unsafe
    if args.scan:
        candidates = [(s, p) for s in parse_range(args.siids) for p in parse_range(args.piids)]
    else:
        candidates = sorted(known)
    keys = [k for k in candidates if k not in skip]
    if args.start:
        start = parse_key(args.start)
        keys = [k for k in keys if k >= start]

    batches = [keys[i:i + args.batch] for i in range(0, len(keys), args.batch)]
    print(f"{BOLD}Reading {len(keys)} properties, {args.batch} per request, {args.delay}s apart. Reads only.{RESET}")
    print("Watch the purifier. If it restarts, note the time — each read is timestamped.\n")

    if not wait_for_health(client, did, host):
        print(f"{RED}❌ Device isn't answering even before the first read. Check it's on and online in the app.{RESET}")
        sys.exit(1)

    results = {}
    for batch in batches:
        label = ", ".join(f"{s}.{p} {label_of((s, p))}" for s, p in batch)
        print(f"{CYAN}{ts()}  reading {label}{RESET}")
        res, err = read_props(client, did, host, batch)
        if err:
            # The read itself got no answer: the device most likely crashed on it.
            # Stop here even if it comes back before the next health check.
            print(f"  {RED}{err}{RESET}")
        for k in batch:
            code, value = res.get(k, (None, None))
            results[k] = (code, value)
            if code == 0:
                print(f"  {GREEN}{k[0]}.{k[1]} {label_of(k)} = {value!r}{RESET}")
            elif code is not None:
                print(f"  {YELLOW}{k[0]}.{k[1]} {label_of(k)}: code {code} (device doesn't have it?){RESET}")

        if args.confirm:
            input("  Purifier still OK? Press Enter to continue, Ctrl+C to stop. ")
        else:
            time.sleep(args.delay)

        healthy = wait_for_health(client, did, host)
        if err or not healthy:
            what = "didn't answer this read" if err else "stopped answering after"
            back = " (it has answered again since)" if healthy else ""
            print(f"\n{RED}{BOLD}⛔ Device {what}: {label}{back}{RESET}")
            print(f"{RED}   Likely trigger. Once the device is back, skip it and carry on with:{RESET}")
            later = [k for k in keys if k > batch[-1]]
            skip_arg = ",".join(f"{s}.{p}" for s, p in sorted((skip - unsafe) | set(batch)))
            scan_arg = f" --scan --siids {args.siids} --piids {args.piids}" if args.scan else ""
            if later:
                print(f"   python {sys.argv[0]} -u EMAIL -p 'PASSWORD' --country {args.country}{scan_arg} --skip {skip_arg} --start {later[0][0]}.{later[0][1]}")
            print(f"{RED}   Please report it so it can be added to UNSAFE_PROPS for {model}.{RESET}")
            if len(batch) > 1:
                print(f"   (that request had {len(batch)} properties; re-run with --batch 1 to find which one)")
            break
    else:
        print(f"\n{GREEN}{BOLD}✅ Device kept answering through every read.{RESET}")

    print(f"\n{BOLD}Summary{RESET} (no device ID or MAC; in --scan mode, check values for location/time zone before sharing)")
    for k in keys:
        if k not in results:
            continue
        code, value = results[k]
        if args.scan and code not in (0, None):
            continue  # in a scan, only show properties that exist (or didn't answer)
        status = f"= {value!r}" if code == 0 else ("no answer" if code is None else f"code {code}")
        print(f"  {k[0]:>2}.{k[1]:<2}  {label_of(k):<24} {status}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Stopped.{RESET}")
