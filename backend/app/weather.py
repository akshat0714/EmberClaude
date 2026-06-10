"""Live wind from Open-Meteo (keyless, free) with graceful fallback.

Meteorological convention matches the fire model: wind_direction_10m is
the direction the wind blows FROM, exactly our `windFromDeg`.
"""

from __future__ import annotations

import json
import time
from typing import Optional

import httpx

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"
SCENARIO_LATLON = (34.06, -118.54)  # Palisades Highlands area

_cache: Optional[dict] = None
_cache_at = 0.0
CACHE_TTL_S = 300.0


def fetch_live_wind(timeout_s: float = 5.0) -> Optional[dict]:
    """Current wind at the scenario area, or None when unreachable."""
    global _cache, _cache_at
    if _cache is not None and time.time() - _cache_at < CACHE_TTL_S:
        return _cache
    try:
        resp = httpx.get(OPEN_METEO_URL, timeout=timeout_s, params={
            "latitude": SCENARIO_LATLON[0],
            "longitude": SCENARIO_LATLON[1],
            "current": "wind_speed_10m,wind_direction_10m,wind_gusts_10m",
            "wind_speed_unit": "mph",
        })
        resp.raise_for_status()
        cur = resp.json().get("current", {})
        wind = {
            "windSpeedMph": float(cur["wind_speed_10m"]),
            "windFromDeg": float(cur["wind_direction_10m"]),
            "windGustsMph": float(cur.get("wind_gusts_10m", 0.0)),
            "observedAt": cur.get("time", ""),
            "source": "open-meteo.com (live, keyless)",
        }
    except (httpx.HTTPError, json.JSONDecodeError, KeyError, ValueError, TypeError):
        return None
    _cache, _cache_at = wind, time.time()
    return wind
