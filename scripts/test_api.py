#!/usr/bin/env python3
"""Standalone live-API test for the Viessmann ViCare API (Vitocal 200-S).

Run this BEFORE installing the HA integration to verify what your device and
API plan actually support.

Usage:
    export VICARE_EMAIL="you@example.com"
    export VICARE_PASSWORD="..."
    export VICARE_CLIENT_ID="..."        # from https://app.developer.viessmann-climatesolutions.com/

    python3 scripts/test_api.py               # read-only: discovery, schedules, constraints, backup
    python3 scripts/test_api.py --write       # additionally: round-trip write tests (restores backup)

Requires: pip install PyViCare==2.60.2
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path

from PyViCare.PyViCare import PyViCare
from PyViCare.PyViCareUtils import (
    PyViCareCommandError,
    PyViCareNotSupportedFeatureError,
)

TOKEN_FILE = str(Path(__file__).parent / ".vicare_token.save")
BACKUP_FILE = Path(__file__).parent / "schedule_backup.json"

DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

CIRCULATION_FEATURE = "heating.dhw.pumps.circulation.schedule"
DHW_SCHEDULE_FEATURE = "heating.dhw.schedule"


def get_env(name):
    value = os.environ.get(name)
    if not value:
        sys.exit(f"Missing environment variable {name}")
    return value


def safe_call(label, fn):
    try:
        result = fn()
        print(f"\n=== {label} ===")
        print(json.dumps(result, indent=2, default=str))
        return result
    except PyViCareNotSupportedFeatureError:
        print(f"\n=== {label} ===\nNOT SUPPORTED on this device")
        return None
    except Exception as err:  # noqa: BLE001 - diagnostic script
        print(f"\n=== {label} ===\nERROR: {type(err).__name__}: {err}")
        return None


def print_command_constraints(raw_feature, label):
    """Extract setSchedule command constraints from raw feature JSON."""
    print(f"\n=== {label}: setSchedule constraints ===")
    try:
        commands = raw_feature["data"]["commands"]
    except (KeyError, TypeError):
        commands = (raw_feature or {}).get("commands", {})
    set_schedule = commands.get("setSchedule", {})
    print(f"  isExecutable: {set_schedule.get('isExecutable')}")
    params = set_schedule.get("params", {}).get("newSchedule", {})
    constraints = params.get("constraints", {})
    print(json.dumps(constraints, indent=2))
    modes = constraints.get("modes", [])
    max_entries = constraints.get("maxEntries")
    resolution = constraints.get("resolution")
    print(f"  -> valid modes: {modes}")
    print(f"  -> maxEntries/day: {max_entries}, resolution: {resolution} min")
    return constraints


def read_schedule_entries(feature_json):
    """Return the schedule entries dict from raw feature JSON."""
    try:
        props = feature_json["data"]["properties"]
    except (KeyError, TypeError):
        props = (feature_json or {}).get("properties", {})
    return props.get("entries", {}).get("value", {})


def write_and_verify(device, feature, schedule, description):
    print(f"\n--- Writing {feature}: {description} ---")
    try:
        response = device.service.setProperty(
            feature, "setSchedule", {"newSchedule": schedule}
        )
        print(f"  API response: {response}")
    except PyViCareCommandError as err:
        print(f"  REJECTED: {err}")
        return False
    time.sleep(5)
    raw = device.service.getProperty(feature)
    readback = read_schedule_entries(raw)
    print(f"  Read-back: {json.dumps(readback)}")
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write",
        action="store_true",
        help="Run round-trip write tests (current schedule is backed up and restored)",
    )
    args = parser.parse_args()

    email = get_env("VICARE_EMAIL")
    password = get_env("VICARE_PASSWORD")
    client_id = get_env("VICARE_CLIENT_ID")

    print("Logging in...")
    vicare = PyViCare()
    vicare.initWithCredentials(email, password, client_id, TOKEN_FILE)

    print(f"\nFound {len(vicare.devices)} device(s):")
    for d in vicare.devices:
        print(
            f"  - model={d.getModel()} id={d.device_id} "
            f"serial={getattr(d.service.accessor, 'serial', '?')} online={d.isOnline()}"
        )

    device_config = next(
        (d for d in vicare.devices if d.getModel() not in ("Heatbox1", "E3_TCU41_x04")),
        vicare.devices[0],
    )
    print(f"\nUsing device: {device_config.getModel()}")
    device = device_config.asAutoDetectDevice()

    # --- Read-only pass ---
    circ_schedule = safe_call(
        "Circulation pump schedule (PyViCare)",
        device.getDomesticHotWaterCirculationSchedule,
    )
    safe_call(
        "Circulation schedule modes (PyViCare)",
        device.getDomesticHotWaterCirculationScheduleModes,
    )
    safe_call(
        "Circulation pump active (PyViCare)",
        device.getDomesticHotWaterCirculationPumpActive,
    )
    dhw_schedule = safe_call(
        "DHW time program (PyViCare)", device.getDomesticHotWaterSchedule
    )

    circ_raw = safe_call(
        f"Raw feature: {CIRCULATION_FEATURE}",
        lambda: device.service.getProperty(CIRCULATION_FEATURE),
    )
    dhw_raw = safe_call(
        f"Raw feature: {DHW_SCHEDULE_FEATURE}",
        lambda: device.service.getProperty(DHW_SCHEDULE_FEATURE),
    )

    circ_constraints = {}
    if circ_raw:
        circ_constraints = print_command_constraints(circ_raw, CIRCULATION_FEATURE)
    if dhw_raw:
        print_command_constraints(dhw_raw, DHW_SCHEDULE_FEATURE)

    # --- Backup current schedules ---
    backup = {
        "circulation": read_schedule_entries(circ_raw) if circ_raw else circ_schedule,
        "dhw": read_schedule_entries(dhw_raw) if dhw_raw else dhw_schedule,
    }
    BACKUP_FILE.write_text(json.dumps(backup, indent=2, default=str))
    print(f"\nBacked up current schedules to {BACKUP_FILE}")

    if not args.write:
        print("\nRead-only pass complete. Re-run with --write for round-trip tests.")
        return

    # --- Write pass (circulation pump) ---
    if backup["circulation"] is None:
        print("\nSkipping circulation write tests (feature not readable).")
    else:
        modes = circ_constraints.get("modes") or ["on"]
        on_mode = "on" if "on" in modes else modes[0]

        write_and_verify(
            device,
            CIRCULATION_FEATURE,
            backup["circulation"],
            "no-op re-upload of current schedule",
        )

        always_on_2400 = {
            day: [{"start": "00:00", "end": "24:00", "mode": on_mode, "position": 0}]
            for day in DAYS
        }
        if not write_and_verify(
            device, CIRCULATION_FEATURE, always_on_2400, "always-on with end=24:00"
        ):
            always_on_2359 = {
                day: [{"start": "00:00", "end": "23:59", "mode": on_mode, "position": 0}]
                for day in DAYS
            }
            write_and_verify(
                device,
                CIRCULATION_FEATURE,
                always_on_2359,
                "always-on with end=23:59 (24:00 fallback)",
            )

        write_and_verify(device, CIRCULATION_FEATURE, {}, "empty schedule (pump off)")
        write_and_verify(
            device, CIRCULATION_FEATURE, backup["circulation"], "RESTORE backup"
        )

    # --- Write pass (DHW time program) ---
    if backup["dhw"] is None:
        print("\nSkipping DHW schedule write tests (feature not readable).")
    else:
        write_and_verify(
            device,
            DHW_SCHEDULE_FEATURE,
            backup["dhw"],
            "no-op re-upload of current DHW schedule",
        )

    print("\nWrite pass complete. Verify schedules look correct in the ViCare app.")
    print(f"If anything is wrong, restore manually from {BACKUP_FILE}")


if __name__ == "__main__":
    main()
