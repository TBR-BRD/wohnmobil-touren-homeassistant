#!/usr/bin/env python3
"""Generate Home Assistant tour metadata and GeoJSON from Traccar positions.

The script is intentionally dependency-free and reads all installation-specific
values from a local JSON file. Keep that file outside version control.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import math
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

COLORS = [
    "#FF9800", "#00BCD4", "#4CAF50", "#E91E63", "#9C27B0",
    "#F44336", "#03A9F4", "#CDDC39", "#FFC107", "#795548",
    "#8BC34A", "#FF5722", "#3F51B5", "#009688", "#673AB7",
    "#FFEB3B", "#2196F3", "#C2185B", "#7CB342", "#F57C00",
]

MATCH_ENGINE_VERSION = 1
DEFAULT_CONFIG = "/config/wohnmobil_tours.private.json"


def parse_iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None


def ptime(point: dict[str, Any]) -> datetime | None:
    for key in ("fixTime", "deviceTime", "serverTime"):
        parsed = parse_iso(point.get(key))
        if parsed is not None:
            return parsed
    return None


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius_km = 6371.0088
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius_km * math.asin(math.sqrt(a))


def route_km(points: list[dict[str, Any]]) -> float:
    total = 0.0
    for a, b in zip(points, points[1:]):
        total += haversine_km(
            float(a["latitude"]),
            float(a["longitude"]),
            float(b["latitude"]),
            float(b["longitude"]),
        )
    return total


def load_config(path: str) -> dict[str, Any]:
    cfg_path = Path(path)
    if not cfg_path.exists():
        raise RuntimeError(
            f"Configuration file not found: {cfg_path}. "
            "Copy config/wohnmobil_tours.example.json and keep the private copy out of Git."
        )
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise RuntimeError("Configuration root must be a JSON object")
    return data


def require(cfg: dict[str, Any], section: str, key: str) -> Any:
    value = cfg.get(section, {}).get(key)
    if value in (None, "", "CHANGE_ME"):
        raise RuntimeError(f"Missing configuration value: {section}.{key}")
    return value


def fetch_positions(cfg: dict[str, Any]) -> list[dict[str, Any]]:
    traccar = cfg.get("traccar", {})
    detection = cfg.get("tour_detection", {})

    base_url = str(require(cfg, "traccar", "base_url")).rstrip("/")
    device_id = int(require(cfg, "traccar", "device_id"))
    username = str(require(cfg, "traccar", "username"))
    password = str(require(cfg, "traccar", "password"))
    date_from = str(require(cfg, "tour_detection", "from"))
    date_to = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    params = urllib.parse.urlencode(
        {"deviceId": device_id, "from": date_from, "to": date_to}
    )
    url = f"{base_url}/api/positions?{params}"

    auth = base64.b64encode(f"{username}:{password}".encode()).decode()
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Basic {auth}", "Accept": "application/json"},
    )

    timeout = int(traccar.get("timeout_seconds", 60))
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            payload = json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(f"Traccar API HTTP {exc.code}: {exc.reason}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Traccar network error: {exc.reason}") from exc

    if not isinstance(payload, list):
        raise RuntimeError("Traccar API did not return a position list")

    usable = [
        p
        for p in payload
        if isinstance(p, dict)
        and p.get("latitude") is not None
        and p.get("longitude") is not None
        and ptime(p) is not None
    ]
    usable.sort(key=lambda p: ptime(p) or datetime.min.replace(tzinfo=timezone.utc))
    return usable


def inside_home(point: dict[str, Any], home_lat: float, home_lon: float, radius_km: float) -> bool:
    return haversine_km(
        home_lat,
        home_lon,
        float(point["latitude"]),
        float(point["longitude"]),
    ) <= radius_km


def near_anchor(point: dict[str, Any], anchor: dict[str, Any], radius_km: float) -> bool:
    return haversine_km(
        float(anchor["latitude"]),
        float(anchor["longitude"]),
        float(point["latitude"]),
        float(point["longitude"]),
    ) <= radius_km


def find_confirmed_home_stays(
    points: list[dict[str, Any]],
    home_lat: float,
    home_lon: float,
    home_radius_km: float,
    return_confirm_hours: float,
    home_stay_radius_km: float,
    diagnostics: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Find stationary stays inside the broad home radius.

    The broad radius separates journeys. The narrow anchor radius prevents
    ordinary driving inside the home area from being mistaken for a return.
    """
    stays: list[dict[str, Any]] = []
    confirm_seconds = return_confirm_hours * 3600.0
    i = 0
    n = len(points)

    while i < n:
        if not inside_home(points[i], home_lat, home_lon, home_radius_km):
            i += 1
            continue

        anchor = points[i]
        start_idx = i
        j = i
        broke_on = "end_of_data"

        while j + 1 < n:
            nxt = points[j + 1]
            if not inside_home(nxt, home_lat, home_lon, home_radius_km):
                broke_on = "left_home_radius"
                break
            if not near_anchor(nxt, anchor, home_stay_radius_km):
                broke_on = "moved_from_anchor"
                break
            j += 1

        start_t = ptime(points[start_idx])
        end_t = ptime(points[j])
        duration_h = (
            (end_t - start_t).total_seconds() / 3600.0
            if start_t and end_t
            else 0.0
        )
        confirmed = bool(
            start_t and end_t and (end_t - start_t).total_seconds() >= confirm_seconds
        )

        if diagnostics is not None:
            anchor_lat = float(anchor["latitude"])
            anchor_lon = float(anchor["longitude"])
            spread_km = max(
                (
                    haversine_km(
                        anchor_lat,
                        anchor_lon,
                        float(p["latitude"]),
                        float(p["longitude"]),
                    )
                    for p in points[start_idx : j + 1]
                ),
                default=0.0,
            )
            diagnostics.append(
                {
                    "start_time": start_t.isoformat() if start_t else None,
                    "end_time": end_t.isoformat() if end_t else None,
                    "duration_hours": round(duration_h, 2),
                    "points": j - start_idx + 1,
                    "anchor_spread_km": round(spread_km, 3),
                    "window_ended_because": broke_on,
                    "confirmed": confirmed,
                    "reason": (
                        "ok"
                        if confirmed
                        else f"stay only {duration_h:.2f} h, need {return_confirm_hours:.2f} h"
                    ),
                }
            )

        if confirmed:
            stays.append(
                {
                    "start_idx": start_idx,
                    "end_idx": j,
                    "start_time": start_t,
                    "end_time": end_t,
                }
            )
            i = j + 1
        else:
            i = start_idx + 1

    return stays


def segment_has_outside(
    points: list[dict[str, Any]],
    start_idx: int,
    end_idx: int,
    home_lat: float,
    home_lon: float,
    home_radius_km: float,
) -> bool:
    return any(
        not inside_home(p, home_lat, home_lon, home_radius_km)
        for p in points[start_idx : end_idx + 1]
    )


def split_tours(
    points: list[dict[str, Any]],
    home_lat: float,
    home_lon: float,
    home_radius_km: float,
    return_confirm_hours: float,
    home_stay_radius_km: float,
    diagnostics: dict[str, Any] | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Build tours between confirmed home stays.

    The visible route starts at the last point of a confirmed home stay and
    ends at the first point of the next one, so the first and last kilometres
    inside the broad home radius remain part of the tour.
    """
    stay_candidates = (
        diagnostics.setdefault("stay_candidates", [])
        if diagnostics is not None
        else None
    )
    stays = find_confirmed_home_stays(
        points,
        home_lat,
        home_lon,
        home_radius_km,
        return_confirm_hours,
        home_stay_radius_km,
        diagnostics=stay_candidates,
    )
    tours: list[dict[str, Any]] = []

    if not points:
        return tours, stays

    if stays:
        first = stays[0]
        if first["start_idx"] > 0 and segment_has_outside(
            points, 0, first["start_idx"], home_lat, home_lon, home_radius_km
        ):
            pts = points[0 : first["start_idx"] + 1]
            if len(pts) >= 2:
                tours.append(
                    {
                        "points": pts,
                        "partial_start": not inside_home(
                            points[0], home_lat, home_lon, home_radius_km
                        ),
                        "active": False,
                    }
                )
    else:
        if segment_has_outside(
            points, 0, len(points) - 1, home_lat, home_lon, home_radius_km
        ) and len(points) >= 2:
            tours.append(
                {
                    "points": points[:],
                    "partial_start": not inside_home(
                        points[0], home_lat, home_lon, home_radius_km
                    ),
                    "active": True,
                }
            )
        return tours, stays

    for prev_stay, next_stay in zip(stays, stays[1:]):
        start_idx = prev_stay["end_idx"]
        end_idx = next_stay["start_idx"]
        if end_idx <= start_idx:
            continue
        if not segment_has_outside(
            points, start_idx, end_idx, home_lat, home_lon, home_radius_km
        ):
            continue
        pts = points[start_idx : end_idx + 1]
        if len(pts) >= 2:
            tours.append({"points": pts, "partial_start": False, "active": False})

    last_stay = stays[-1]
    if last_stay["end_idx"] < len(points) - 1:
        start_idx = last_stay["end_idx"]
        end_idx = len(points) - 1
        if segment_has_outside(
            points, start_idx, end_idx, home_lat, home_lon, home_radius_km
        ):
            pts = points[start_idx : end_idx + 1]
            if len(pts) >= 2:
                tours.append({"points": pts, "partial_start": False, "active": True})

    return tours, stays


def load_tour_stats(path: str) -> dict[str, Any]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError
        if not isinstance(data.get("tours"), dict):
            data["tours"] = {}
        data.setdefault("version", 1)
        return data
    except Exception:
        return {"version": 1, "tours": {}}


def save_tour_stats(path: str, stats: dict[str, Any]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(json.dumps(stats, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(tmp, target)


def tour_uid(tour: dict[str, Any]) -> str:
    pts = tour["points"]
    first = pts[0]
    last = pts[-1]
    start = ptime(first)
    end = ptime(last)
    raw = "|".join(
        [
            start.isoformat() if start else "",
            end.isoformat() if end else "",
            f"{float(first['latitude']):.6f}",
            f"{float(first['longitude']):.6f}",
            f"{float(last['latitude']):.6f}",
            f"{float(last['longitude']):.6f}",
            str(len(pts)),
        ]
    )
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:20]


def simplify_points_for_matching(points: list[dict[str, Any]], min_distance_m: float) -> list[dict[str, Any]]:
    if len(points) <= 2:
        return points[:]
    kept = [points[0]]
    last = points[0]
    threshold_km = min_distance_m / 1000.0
    for p in points[1:-1]:
        d = haversine_km(
            float(last["latitude"]),
            float(last["longitude"]),
            float(p["latitude"]),
            float(p["longitude"]),
        )
        if d >= threshold_km:
            kept.append(p)
            last = p
    kept.append(points[-1])
    return kept


def chunk_points(points: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    if len(points) <= size:
        return [points]
    chunks = []
    start = 0
    while start < len(points) - 1:
        end = min(start + size, len(points))
        chunk = points[start:end]
        if len(chunk) >= 2:
            chunks.append(chunk)
        if end >= len(points):
            break
        start = end - 1
    return chunks


def _read_http_error(exc: urllib.error.HTTPError) -> str:
    try:
        body = exc.read().decode("utf-8", errors="replace").strip()
    except Exception:
        body = ""
    return f"HTTP {exc.code}: {body[:500] if body else exc.reason}"


def _osrm_get(chunk: list[dict[str, Any]], mm: dict[str, Any]) -> dict[str, Any]:
    coords = ";".join(
        f"{float(p['longitude']):.6f},{float(p['latitude']):.6f}" for p in chunk
    )
    radius_m = int(mm.get("default_radius_m", 30))
    radiuses = ";".join(str(radius_m) for _ in chunk)
    query = urllib.parse.urlencode(
        {
            "steps": "false",
            "overview": "false",
            "gaps": "ignore",
            "tidy": "true",
            "radiuses": radiuses,
        },
        safe=";",
    )
    match_url = str(mm.get("url", "https://router.project-osrm.org/match/v1/driving")).rstrip("/")
    url = f"{match_url}/{coords}?{query}"
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": str(mm.get("user_agent", "wohnmobil-touren-homeassistant/1.0")),
            "Accept": "application/json",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=int(mm.get("timeout_seconds", 30))) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        raise RuntimeError(_read_http_error(exc)) from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"OSRM network error: {exc.reason}") from exc


def _combine_match_results(parts: list[dict[str, Any]]) -> dict[str, Any]:
    distance_m = sum(float(p.get("distance_m") or 0.0) for p in parts)
    weighted = sum(
        float(p.get("confidence") or 0.0) * float(p.get("distance_m") or 0.0)
        for p in parts
    )
    ratios = [float(p["matched_ratio"]) for p in parts if p.get("matched_ratio") is not None]
    return {
        "distance_m": distance_m,
        "confidence": weighted / distance_m if distance_m > 0 else 0.0,
        "matched_ratio": sum(ratios) / len(ratios) if ratios else None,
    }


def osrm_match_chunk(chunk: list[dict[str, Any]], mm: dict[str, Any]) -> dict[str, Any]:
    try:
        data = _osrm_get(chunk, mm)
    except RuntimeError as exc:
        msg = str(exc)
        too_big = "Too many trace coordinates" in msg or '"code":"TooBig"' in msg or '"code": "TooBig"' in msg
        if too_big and len(chunk) > 2:
            mid = len(chunk) // 2
            left = chunk[: mid + 1]
            right = chunk[mid:]
            left_result = osrm_match_chunk(left, mm)
            time.sleep(float(mm.get("request_delay_seconds", 1.05)))
            right_result = osrm_match_chunk(right, mm)
            return _combine_match_results([left_result, right_result])
        raise

    if data.get("code") != "Ok":
        code_value = data.get("code", "unknown")
        if code_value == "TooBig" and len(chunk) > 2:
            mid = len(chunk) // 2
            left_result = osrm_match_chunk(chunk[: mid + 1], mm)
            time.sleep(float(mm.get("request_delay_seconds", 1.05)))
            right_result = osrm_match_chunk(chunk[mid:], mm)
            return _combine_match_results([left_result, right_result])
        raise RuntimeError(f"OSRM {code_value}: {data.get('message', '')}")

    matchings = data.get("matchings") or []
    if not matchings:
        raise RuntimeError("OSRM returned no matchings")

    distance_m = 0.0
    weighted = 0.0
    for matching in matchings:
        d = float(matching.get("distance") or 0.0)
        c = float(matching.get("confidence") or 0.0)
        distance_m += d
        weighted += c * d

    tracepoints = data.get("tracepoints")
    matched_ratio = None
    if isinstance(tracepoints, list) and tracepoints:
        matched_ratio = sum(1 for p in tracepoints if p is not None) / len(tracepoints)

    return {
        "distance_m": distance_m,
        "confidence": weighted / distance_m if distance_m > 0 else 0.0,
        "matched_ratio": matched_ratio,
    }


def map_match_tour_once(
    tour: dict[str, Any],
    tour_number: int,
    gps_distance_km: float,
    stats: dict[str, Any],
    mm: dict[str, Any],
    force_rematch: bool,
) -> dict[str, Any]:
    uid = tour_uid(tour)
    now_ts = int(time.time())
    cached = stats["tours"].get(uid)

    if isinstance(cached, dict) and not force_rematch:
        cached_engine = int(cached.get("engine_version") or 0)
        if cached.get("status") == "ok" and cached_engine == MATCH_ENGINE_VERSION:
            return cached
        if cached_engine == MATCH_ENGINE_VERSION and int(cached.get("retry_after_ts") or 0) > now_ts:
            return cached

    simplified = simplify_points_for_matching(
        tour["points"], float(mm.get("min_point_distance_m", 100.0))
    )
    chunks = chunk_points(simplified, int(mm.get("chunk_points", 40)))

    base = {
        "engine_version": MATCH_ENGINE_VERSION,
        "tour_uid": uid,
        "tour_number": tour_number,
        "start": ptime(tour["points"][0]).isoformat(),
        "end": ptime(tour["points"][-1]).isoformat(),
        "distance_gps_km": round(gps_distance_km, 1),
        "provider": "OSRM / OpenStreetMap",
        "points_original": len(tour["points"]),
        "points_sent": len(simplified),
        "chunks": len(chunks),
    }

    cache_file = str(mm.get("cache_file", "/config/wohnmobil_tour_stats.json"))
    try:
        if len(simplified) < 2:
            raise RuntimeError("Not enough points for map matching")

        total_m = 0.0
        confidence_weighted = 0.0
        matched_ratios = []
        for idx, chunk in enumerate(chunks):
            result = osrm_match_chunk(chunk, mm)
            total_m += result["distance_m"]
            confidence_weighted += result["confidence"] * result["distance_m"]
            if result["matched_ratio"] is not None:
                matched_ratios.append(result["matched_ratio"])
            if idx + 1 < len(chunks):
                time.sleep(float(mm.get("request_delay_seconds", 1.05)))

        road_km = total_m / 1000.0
        ratio = road_km / gps_distance_km if gps_distance_km > 0 else 0.0
        ratio_min = float(mm.get("min_ratio_to_gps", 0.75))
        ratio_max = float(mm.get("max_ratio_to_gps", 1.50))
        if not ratio_min <= ratio <= ratio_max:
            raise RuntimeError(
                f"Implausible match: {road_km:.1f} km road vs. {gps_distance_km:.1f} km GPS "
                f"(factor {ratio:.2f})"
            )

        result = {
            **base,
            "status": "ok",
            "distance_road_km": round(road_km, 1),
            "road_to_gps_ratio": round(ratio, 4),
            "confidence": round(confidence_weighted / total_m if total_m > 0 else 0.0, 4),
            "matched_point_ratio": round(sum(matched_ratios) / len(matched_ratios), 4) if matched_ratios else None,
            "matched_at": datetime.now(timezone.utc).isoformat(),
        }
        stats["tours"][uid] = result
        save_tour_stats(cache_file, stats)
        return result
    except Exception as exc:
        result = {
            **base,
            "status": "failed",
            "error": str(exc)[:300],
            "last_attempt": datetime.now(timezone.utc).isoformat(),
            "retry_after_ts": now_ts + int(float(mm.get("retry_after_hours", 24)) * 3600),
        }
        stats["tours"][uid] = result
        save_tour_stats(cache_file, stats)
        return result


def feature(
    tour: dict[str, Any], number: int, color: str, matching: dict[str, Any] | None = None
) -> tuple[dict[str, Any], dict[str, Any]]:
    pts = tour["points"]
    start = ptime(pts[0])
    end = ptime(pts[-1])
    gps_km = round(route_km(pts), 1)
    props: dict[str, Any] = {
        "tour": number,
        "name": f"Tour {number}",
        "color": color,
        "start": start.isoformat() if start else None,
        "end": end.isoformat() if end else None,
        "duration_hours": round((end - start).total_seconds() / 3600.0, 1) if start and end else None,
        "distance_km": gps_km,
        "distance_gps_km": gps_km,
        "active": bool(tour.get("active")),
        "partial_start": bool(tour.get("partial_start")),
    }

    if isinstance(matching, dict):
        props["map_matching_status"] = matching.get("status")
        props["map_matching_provider"] = matching.get("provider")
        if matching.get("status") == "ok":
            props["distance_road_km"] = matching.get("distance_road_km")
            props["map_matching_confidence"] = matching.get("confidence")
            props["matched_point_ratio"] = matching.get("matched_point_ratio")
            props["matched_at"] = matching.get("matched_at")
        elif matching.get("status") == "failed":
            props["map_matching_error"] = matching.get("error")

    geojson = {
        "type": "Feature",
        "properties": props,
        "geometry": {
            "type": "LineString",
            "coordinates": [[float(p["longitude"]), float(p["latitude"])] for p in pts],
        },
    }
    return geojson, props


def _fill_position_diagnostics(
    diagnostics: dict[str, Any],
    positions: list[dict[str, Any]],
    home_lat: float,
    home_lon: float,
    home_radius_km: float,
) -> None:
    times = [t for t in (ptime(p) for p in positions) if t is not None]
    inside = sum(
        1 for p in positions if inside_home(p, home_lat, home_lon, home_radius_km)
    )
    gaps: list[dict[str, Any]] = []
    for a, b in zip(times, times[1:]):
        hours = (b - a).total_seconds() / 3600.0
        if hours >= 1.0:
            gaps.append({"from": a.isoformat(), "to": b.isoformat(), "hours": round(hours, 1)})
    gaps.sort(key=lambda g: g["hours"], reverse=True)
    diagnostics["positions"] = {
        "total": len(positions),
        "inside_home_radius": inside,
        "outside_home_radius": len(positions) - inside,
        "first_time": times[0].isoformat() if times else None,
        "last_time": times[-1].isoformat() if times else None,
        "largest_gaps_hours": gaps[:10],
    }


def _print_explain(diagnostics: dict[str, Any]) -> None:
    out = sys.stderr
    pos = diagnostics.get("positions", {})
    settings = diagnostics.get("settings", {})
    candidates = diagnostics.get("stay_candidates", [])
    tours = diagnostics.get("tours", [])
    confirmed = [c for c in candidates if c.get("confirmed")]
    rejected = [c for c in candidates if not c.get("confirmed")]

    print("=== Tour-Erkennung: Erklärung ===", file=out)
    print(
        f"Einstellungen: home_radius={settings.get('home_radius_km')} km, "
        f"return_confirm={settings.get('return_confirm_hours')} h, "
        f"home_stay_radius={settings.get('home_stay_radius_km')} km, "
        f"from={settings.get('from')}",
        file=out,
    )
    print(
        f"Positionen: {pos.get('total')} gesamt, "
        f"{pos.get('inside_home_radius')} im Heimatradius, "
        f"{pos.get('outside_home_radius')} außerhalb "
        f"({pos.get('first_time')} .. {pos.get('last_time')})",
        file=out,
    )
    big_gaps = pos.get("largest_gaps_hours") or []
    if big_gaps:
        print("Größte Datenlücken (>=1 h):", file=out)
        for g in big_gaps:
            print(f"  {g['hours']:>6.1f} h   {g['from']} -> {g['to']}", file=out)

    print(
        f"\nHeimataufenthalte: {len(confirmed)} bestätigt, {len(rejected)} verworfen",
        file=out,
    )
    for c in candidates:
        mark = "OK " if c.get("confirmed") else "-- "
        print(
            f"  {mark}{c.get('start_time')} .. {c.get('end_time')}  "
            f"{c.get('duration_hours'):>6.2f} h  {c.get('points')} Pkt  "
            f"Spreizung {c.get('anchor_spread_km')} km  "
            f"Ende: {c.get('window_ended_because')}  [{c.get('reason')}]",
            file=out,
        )

    print(f"\nErgebnis: {len(tours)} Tour(en)", file=out)
    for t in tours:
        state = "aktiv" if t["active"] else "abgeschlossen"
        print(
            f"  Tour {t['number']}: {t['start']} .. {t['end']}  "
            f"{t['gps_km']} km GPS  {t['points']} Pkt  ({state})",
            file=out,
        )

    n_confirmed = len(confirmed)
    print("\nHinweis:", file=out)
    if n_confirmed == 0:
        print(
            "  Kein einziger Heimataufenthalt wurde bestätigt -> alles wird zu einer "
            "aktiven Tour. Prüfe return_confirm_hours / home_stay_radius_km und ob der "
            "Tracker beim Parken zu Hause überhaupt Positionen sendet.",
            file=out,
        )
    elif n_confirmed == 1:
        print(
            "  Nur ein bestätigter Heimataufenthalt -> es kann nur eine (aktive) Tour "
            "davor/danach geben. Für mehrere abgeschlossene Touren braucht es mindestens "
            "zwei bestätigte Aufenthalte im Zeitraum.",
            file=out,
        )
    if rejected:
        near = [
            c
            for c in rejected
            if isinstance(c.get("duration_hours"), (int, float))
            and c["duration_hours"] >= 0.5
            and c.get("window_ended_because") == "moved_from_anchor"
        ]
        if near:
            print(
                "  Mehrere Aufenthalte scheiterten an 'moved_from_anchor' -> das Fahrzeug "
                "stand nicht eng genug an einem Punkt. home_stay_radius_km erhöhen "
                "(z. B. 2-3 km) hilft, wenn zu Hause an wechselnden Plätzen geparkt wird.",
                file=out,
            )


def build_result(
    cfg: dict[str, Any],
    force_rematch: bool,
    disable_map_matching: bool,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    detection = cfg.get("tour_detection", {})
    mm = cfg.get("map_matching", {})

    home_lat = float(require(cfg, "tour_detection", "home_latitude"))
    home_lon = float(require(cfg, "tour_detection", "home_longitude"))
    home_radius_km = float(detection.get("home_radius_km", 20.0))
    return_confirm_hours = float(detection.get("return_confirm_hours", 3.0))
    home_stay_radius_km = float(detection.get("home_stay_radius_km", 1.0))
    max_tours = int(detection.get("max_tours", 50))

    positions = fetch_positions(cfg)
    tours, home_stays = split_tours(
        positions,
        home_lat,
        home_lon,
        home_radius_km,
        return_confirm_hours,
        home_stay_radius_km,
        diagnostics=diagnostics,
    )

    if diagnostics is not None:
        _fill_position_diagnostics(
            diagnostics, positions, home_lat, home_lon, home_radius_km
        )
        diagnostics["settings"] = {
            "home_radius_km": home_radius_km,
            "return_confirm_hours": return_confirm_hours,
            "home_stay_radius_km": home_stay_radius_km,
            "from": str(detection.get("from", "")),
            "max_tours": max_tours,
        }
        diagnostics["tours"] = [
            {
                "number": idx + 1,
                "active": bool(t.get("active")),
                "partial_start": bool(t.get("partial_start")),
                "points": len(t["points"]),
                "start": (ptime(t["points"][0]).isoformat() if ptime(t["points"][0]) else None),
                "end": (ptime(t["points"][-1]).isoformat() if ptime(t["points"][-1]) else None),
                "gps_km": round(route_km(t["points"]), 1),
            }
            for idx, t in enumerate(tours)
        ]

    coords = [[float(p["longitude"]), float(p["latitude"])] for p in positions]
    if coords:
        lats = [c[1] for c in coords]
        lons = [c[0] for c in coords]
        bounds = {
            "min_lat": min(lats), "max_lat": max(lats),
            "min_lon": min(lons), "max_lon": max(lons),
            "center_lat": (min(lats) + max(lats)) / 2,
            "center_lon": (min(lons) + max(lons)) / 2,
        }
    else:
        bounds = {k: None for k in ("min_lat", "max_lat", "min_lon", "max_lon", "center_lat", "center_lon")}

    map_matching_enabled = bool(mm.get("enabled", True)) and not disable_map_matching
    cache_file = str(mm.get("cache_file", "/config/wohnmobil_tour_stats.json"))
    stats = load_tour_stats(cache_file)

    result: dict[str, Any] = {
        "state": len(tours),
        "position_count": len(positions),
        "tour_count": len(tours),
        "home_radius_km": home_radius_km,
        "return_confirm_hours": return_confirm_hours,
        "home_stay_radius_km": home_stay_radius_km,
        "home_stay_count": len(home_stays),
        "map_matching_enabled": map_matching_enabled,
        "map_matching_provider": "OSRM / OpenStreetMap" if map_matching_enabled else None,
        **bounds,
        "tours": [],
    }

    visible = tours[-max_tours:]
    for slot in range(1, max_tours + 1):
        key = f"tour_{slot:02d}_geojson"
        if slot <= len(visible):
            number = len(tours) - len(visible) + slot
            color = COLORS[(number - 1) % len(COLORS)]
            tour = visible[slot - 1]
            gps_km = round(route_km(tour["points"]), 1)
            matching = None
            if map_matching_enabled and not tour.get("active"):
                matching = map_match_tour_once(
                    tour, number, gps_km, stats, mm, force_rematch
                )
            geojson, metadata = feature(tour, number, color, matching)
            result[key] = geojson
            result["tours"].append(metadata)
        else:
            result[key] = {"type": "FeatureCollection", "features": []}

    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate Wohnmobil tour GeoJSON from Traccar")
    parser.add_argument("--config", default=DEFAULT_CONFIG, help="Path to private JSON configuration")
    parser.add_argument("--force-rematch", action="store_true", help="Re-run OSRM matching even for cached successful tours")
    parser.add_argument("--disable-map-matching", action="store_true", help="Skip OSRM map matching")
    parser.add_argument("--pretty", action="store_true", help="Pretty-print JSON for manual testing")
    parser.add_argument(
        "--explain",
        action="store_true",
        help="Print a human-readable report of home-stay detection and tour boundaries to stderr",
    )
    args = parser.parse_args()

    try:
        cfg = load_config(args.config)
        diagnostics: dict[str, Any] | None = {} if args.explain else None
        result = build_result(
            cfg, args.force_rematch, args.disable_map_matching, diagnostics
        )
        if diagnostics is not None:
            _print_explain(diagnostics)
        print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None))
        return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
