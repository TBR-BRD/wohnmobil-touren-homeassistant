#!/usr/bin/env python3
"""Optional PAJ -> Traccar synchronizer.

This uses PAJ web API endpoints observed by the original project. They are not
part of a stable public API contract and can change without notice.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LOGIN_URL = "https://connect.paj-gps.de/api/v1/login"
TRACK_URL = "https://connect.paj-gps.de/api/v1/trackerdata/{tracker}/date_range"
DEFAULT_CONFIG = "/config/wohnmobil_tours.private.json"


def req_json(url, method="GET", headers=None, payload=None, timeout=60):
    data = None if payload is None else json.dumps(payload).encode("utf-8")
    request_headers = dict(headers or {})
    if payload is not None:
        request_headers.setdefault("Content-Type", "application/json")
    request = Request(url, data=data, headers=request_headers, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error: {exc.reason}") from exc


def load_config(path):
    target = Path(path)
    if not target.exists():
        raise RuntimeError(f"Configuration file not found: {target}")
    data = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("Configuration root must be a JSON object")
    return data


def require(section, key, value):
    if value in (None, "", "CHANGE_ME"):
        raise RuntimeError(f"Missing configuration value: {section}.{key}")
    return value


def login(paj):
    email = require("paj", "email", paj.get("email"))
    password = require("paj", "password", paj.get("password"))
    data = req_json(
        LOGIN_URL,
        method="POST",
        headers={
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://finder-portal.com/",
            "X-App-Version": str(paj.get("app_version", "2.5.41")),
            "User-Agent": "wohnmobil-touren-homeassistant/1.0",
        },
        payload={
            "email": email,
            "password": password,
            "language": str(paj.get("language", "de")),
            "timezone": str(paj.get("timezone", "Europe/Berlin")),
        },
    )
    try:
        return data["success"]["token"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError("PAJ login response did not contain a token") from exc


def fetch(token, paj, start_ts, end_ts):
    tracker_id = require("paj", "tracker_id", paj.get("tracker_id"))
    query = urlencode({"dateStart": start_ts, "dateEnd": end_ts, "wifi": 1, "gps": 1})
    data = req_json(
        f"{TRACK_URL.format(tracker=tracker_id)}?{query}",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "application/json, text/plain, */*",
            "Referer": "https://finder-portal.com/",
            "X-App-Version": str(paj.get("app_version", "2.5.41")),
            "User-Agent": "wohnmobil-touren-homeassistant/1.0",
        },
    )
    result = data.get("success", []) if isinstance(data, dict) else []
    return result if isinstance(result, list) else []


def send_traccar(ingest, record):
    host = require("traccar_ingest", "host", ingest.get("host"))
    port = int(require("traccar_ingest", "osmand_port", ingest.get("osmand_port")))
    unique_id = require("traccar_ingest", "unique_id", ingest.get("unique_id"))
    params = {
        "id": unique_id,
        "lat": record["lat"],
        "lon": record["lng"],
        "timestamp": int(float(record["dateunix"])),
        "speed": float(record.get("speed") or 0),
        "bearing": float(record.get("direction") or 0),
        "accuracy": float(record.get("accuracy") or 0),
        "batt": float(record.get("battery_level", record.get("battery", 0)) or 0),
        "pajId": str(record.get("id", "")),
    }
    for key in ("steps", "heartbeat", "wzp"):
        if record.get(key) is not None:
            params[key] = record[key]

    url = f"http://{host}:{port}/?{urlencode(params)}"
    request = Request(url, headers={"User-Agent": "wohnmobil-touren-homeassistant/1.0"}, method="GET")
    with urlopen(request, timeout=int(ingest.get("timeout_seconds", 30))) as response:
        if not 200 <= response.status < 300:
            raise RuntimeError(f"Traccar HTTP {response.status}")


def load_state(path):
    target = Path(path)
    if not target.exists():
        return {"last_ts": 0, "seen_ids": []}
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {"last_ts": 0, "seen_ids": []}
    except Exception:
        return {"last_ts": 0, "seen_ids": []}


def save_state(path, last_ts, seen):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(
        json.dumps(
            {
                "updated": datetime.now(timezone.utc).isoformat(),
                "last_ts": int(last_ts),
                "seen_ids": list(seen)[-10000:],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    tmp.replace(target)


def main():
    parser = argparse.ArgumentParser(description="Synchronize PAJ tracker positions to Traccar")
    parser.add_argument("--config", default=DEFAULT_CONFIG)
    args = parser.parse_args()

    cfg = load_config(args.config)
    paj = cfg.get("paj", {})
    ingest = cfg.get("traccar_ingest", {})

    if not bool(paj.get("enabled", False)):
        print(json.dumps({"ok": True, "skipped": True, "reason": "paj.enabled is false"}))
        return 0

    state_path = Path(str(paj.get("state_file", "/config/paj_sync_state.json")))
    state = load_state(state_path)
    seen = set(str(x) for x in state.get("seen_ids", []))
    last_ts = int(state.get("last_ts") or 0)
    now_ts = int(time.time())
    overlap_minutes = int(paj.get("overlap_minutes", 15))
    initial_hours = int(paj.get("initial_hours", 24))
    start_ts = (
        max(0, last_ts - overlap_minutes * 60)
        if last_ts
        else max(0, now_ts - initial_hours * 3600)
    )

    token = login(paj)
    records = fetch(token, paj, start_ts, now_ts)
    records = [
        r
        for r in records
        if isinstance(r, dict)
        and r.get("id")
        and r.get("lat") is not None
        and r.get("lng") is not None
        and r.get("dateunix") is not None
    ]
    records.sort(key=lambda r: int(float(r["dateunix"])))

    imported = 0
    skipped = 0
    newest = last_ts
    delay = float(paj.get("delay_seconds", 0.05))

    for record in records:
        record_id = str(record["id"])
        timestamp = int(float(record["dateunix"]))
        newest = max(newest, timestamp)
        if record_id in seen:
            skipped += 1
            continue
        send_traccar(ingest, record)
        seen.add(record_id)
        imported += 1
        if delay:
            time.sleep(delay)

    save_state(state_path, newest, sorted(seen))
    print(
        json.dumps(
            {
                "ok": True,
                "fetched": len(records),
                "imported": imported,
                "skipped": skipped,
                "last_ts": newest,
            }
        )
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)
