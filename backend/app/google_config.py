"""Runtime configuration for live-data integrations.

GOOGLE_MAPS_API_KEY (env var or backend/.env) unlocks LIVE MODE:
  * Google Photorealistic 3D Tiles (Map Tiles API) in the Cesium scene
  * Google Routes API driving directions (real roads, real instructions)
  * Google Elevation API terrain grid feeding the fire model's slope term

Without a key the app transparently falls back to the synthetic twin
(analytic terrain + demo road graph) so the demo always runs.
Live wind (Open-Meteo) needs no key at all.
"""

from __future__ import annotations

import os
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_DIR.parent / "data"
CACHE_DIR = DATA_DIR / "cache"


def _load_dotenv() -> None:
    """Tiny .env reader (KEY=VALUE lines) so users avoid exporting vars."""
    for candidate in (BACKEND_DIR / ".env", BACKEND_DIR.parent / ".env"):
        if not candidate.exists():
            continue
        for line in candidate.read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def google_api_key() -> str:
    return os.environ.get("GOOGLE_MAPS_API_KEY", "").strip()


def google_enabled() -> bool:
    return bool(google_api_key())


def live_wind_enabled() -> bool:
    """Open-Meteo is keyless; only an explicit opt-out disables it."""
    return os.environ.get("DISABLE_LIVE_WIND", "").strip() != "1"


def public_config() -> dict:
    """What the frontend needs to know (the Maps key is browser-class by
    design — restrict it by HTTP referrer in the Google Cloud console)."""
    return {
        "googleEnabled": google_enabled(),
        "googleMapsApiKey": google_api_key() if google_enabled() else "",
        "liveWindEnabled": live_wind_enabled(),
        "mode": "live_google" if google_enabled() else "synthetic_twin",
        "modeLabel": ("LIVE — Google 3D tiles · Google Directions · real elevation"
                      if google_enabled() else
                      "SYNTHETIC TWIN — demo terrain/roads (set GOOGLE_MAPS_API_KEY for live mode)"),
    }
