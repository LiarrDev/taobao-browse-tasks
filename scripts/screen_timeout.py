#!/usr/bin/env python3
"""Record, temporarily extend, and restore the device screen_off_timeout.

A long task run needs the screen to stay awake (a sleeping screen kills
uiautomator dumps and swipe injection), but changing a user's system setting
must be undone. This module records the original value into
<run_dir>/screen_timeout.json, applies the longer value, and restores the
original when the run finishes.

CLI:
    screen_timeout.py --device <serial> --run-dir <dir> --save [--set 1800000]
    screen_timeout.py --device <serial> --run-dir <dir> --restore
    screen_timeout.py --device <serial> --run-dir <dir> --status

save()     reads the current value first; if it cannot be read nothing is
           written or changed, so restore() can never restore a guessed value.
restore()  is idempotent: a second call reports noop instead of writing again.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime

STATE_NAME = "screen_timeout.json"
DEFAULT_TIMEOUT_MS = 1800000  # 30 minutes


def _adb(adb_path=None):
    return adb_path or os.environ.get("ADB") or shutil.which("adb")


def _run_shell(device, args, adb_path=None, timeout=20):
    adb = _adb(adb_path)
    if not adb:
        raise RuntimeError("adb not found in PATH (set --adb or ADB)")
    proc = subprocess.run(
        [adb, "-s", device, "shell", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip()
        raise RuntimeError(f"adb {' '.join(args)} failed: {detail or proc.returncode}")
    return proc.stdout.strip()


def read_timeout(device, adb_path=None):
    out = _run_shell(device, ["settings", "get", "system", "screen_off_timeout"], adb_path)
    try:
        return int(out)
    except ValueError:
        return None


def write_timeout(device, ms, adb_path=None):
    _run_shell(device, ["settings", "put", "system", "screen_off_timeout", str(int(ms))], adb_path)


def _state_path(run_dir):
    return os.path.join(os.path.expanduser(run_dir), STATE_NAME)


def _load(run_dir):
    path = _state_path(run_dir)
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def _dump(run_dir, data):
    path = _state_path(run_dir)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)


def save(device, run_dir, applied_ms=None, adb_path=None):
    """Record the current timeout, then optionally apply applied_ms."""
    original = read_timeout(device, adb_path)
    if original is None:
        return {"ok": False, "error": "cannot read screen_off_timeout"}
    data = {
        "device": device,
        "original_ms": original,
        "applied_ms": None,
        "saved_at": datetime.now().isoformat(timespec="seconds"),
    }
    if applied_ms and int(applied_ms) > 0:
        write_timeout(device, applied_ms, adb_path)
        data["applied_ms"] = int(applied_ms)
    _dump(run_dir, data)
    return {"ok": True, **data, "path": _state_path(run_dir)}


def restore(device=None, run_dir=None, adb_path=None):
    """Restore the value saved by save(). Idempotent."""
    data = _load(run_dir)
    if not data:
        return {"ok": False, "noop": True, "error": "no saved screen timeout"}
    if data.get("restored_at"):
        return {"ok": True, "noop": True, **data}
    original = data.get("original_ms")
    if not isinstance(original, int):
        return {"ok": False, "error": "saved original_ms is invalid", **data}
    target_device = device or data.get("device")
    if not target_device:
        return {"ok": False, "error": "device unknown", **data}
    write_timeout(target_device, original, adb_path)
    data["restored_at"] = datetime.now().isoformat(timespec="seconds")
    data["restored_ms"] = original
    _dump(run_dir, data)
    return {"ok": True, **data}


def status(device, run_dir):
    return {
        "ok": True,
        "device": device,
        "current_ms": read_timeout(device),
        "saved": _load(run_dir),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Record / extend / restore the phone screen_off_timeout for one run."
    )
    parser.add_argument("--device", required=True, help="Device id from mobile_list_available_devices")
    parser.add_argument("--run-dir", required=True, help="Run directory created by init_run.py")
    parser.add_argument("--save", action="store_true", help="Record the current value (and apply --set)")
    parser.add_argument("--restore", action="store_true", help="Restore the recorded value")
    parser.add_argument("--status", action="store_true", help="Show current and recorded values")
    parser.add_argument(
        "--set",
        type=int,
        default=None,
        help=f"Timeout to apply while saving, in ms (default when saving: {DEFAULT_TIMEOUT_MS})",
    )
    parser.add_argument("--adb", default="", help="Path to adb (default: PATH / $ADB)")
    args = parser.parse_args()

    adb_path = args.adb or None
    try:
        if args.save:
            applied = DEFAULT_TIMEOUT_MS if args.set is None else args.set
            result = save(args.device, args.run_dir, applied_ms=applied, adb_path=adb_path)
        elif args.restore:
            result = restore(args.device, args.run_dir, adb_path=adb_path)
        else:
            result = status(args.device, args.run_dir)
    except Exception as exc:  # adb missing / device offline / settings rejected
        result = {"ok": False, "error": repr(exc)}

    print(json.dumps(result, ensure_ascii=False))
    return 0 if (result.get("ok") or result.get("noop")) else 1


if __name__ == "__main__":
    sys.exit(main())
