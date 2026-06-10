"""Dynamic safe-zone management.

The person is always routed to the nearest VIABLE safe zone. Every
simulation tick re-evaluates each candidate against the fire model's
predicted spread; when the predicted zone grows to encompass (or
critically threaten) the active destination, the destination MOVES to the
next viable zone and the route engine re-plans. This mirrors what
happened on Jan 7, 2025, when early refuge areas had to be abandoned.

Status ladder (modeled, per scenario inputs):
  safe        — outside the predicted envelope, buffer >= AT_RISK_MIN
  at_risk     — buffer < AT_RISK_MIN or inside the +30 min predicted zone soon
  compromised — inside the predicted (t+30) perimeter or buffer < COMPROMISED_MIN
"""

from __future__ import annotations

from typing import Callable, List, Optional, Sequence, Tuple

from . import demo_world, fire_model, geo
from .models import SafeZone

AT_RISK_MIN = 55.0
COMPROMISED_MIN = 40.0
PREDICTION_LOOKAHEAD_MIN = 30.0


class SafeZoneStatus:
    def __init__(self, zone: SafeZone, status: str, buffer_min: float,
                 inside_predicted: bool, note: str):
        self.zone = zone
        self.status = status
        self.buffer_min = buffer_min
        self.inside_predicted = inside_predicted
        self.note = note

    def to_dict(self) -> dict:
        return {"zone": self.zone.model_dump(), "status": self.status,
                "bufferMinutes": round(self.buffer_min, 1),
                "insidePredictedZone": self.inside_predicted, "note": self.note}


def evaluate_zones(cells: Sequence[fire_model.Cell], minute: float,
                   fire_arrival: Callable[[float, float], float],
                   zones: Optional[List[SafeZone]] = None) -> List[SafeZoneStatus]:
    zones = zones if zones is not None else demo_world.SAFE_ZONES
    predicted = fire_model.perimeter_polygon(list(cells), minute + PREDICTION_LOOKAHEAD_MIN)
    out: List[SafeZoneStatus] = []
    for z in zones:
        buffer_min = fire_arrival(z.lon, z.lat) - minute
        inside = bool(predicted) and geo.point_in_polygon(z.lon, z.lat, predicted)  # type: ignore[arg-type]
        if inside or buffer_min < COMPROMISED_MIN:
            status = "compromised"
            note = ("Inside the modeled predicted spread zone."
                    if inside else
                    f"Modeled fire buffer only ~{buffer_min:.0f} min — treated as compromised.")
        elif buffer_min < AT_RISK_MIN:
            status = "at_risk"
            note = f"Viable but monitored: ~{buffer_min:.0f} min modeled buffer."
        else:
            status = "safe"
            note = f"~{min(buffer_min, 240):.0f} min modeled buffer."
        out.append(SafeZoneStatus(z, status, buffer_min, inside, note))
    return out


def select_destination(statuses: List[SafeZoneStatus],
                       user: Tuple[float, float]) -> SafeZoneStatus:
    """Nearest non-compromised zone (people head to the closest refuge);
    if everything is compromised, the least-bad (largest buffer) wins so the
    engine always has somewhere to send the person."""
    viable = [s for s in statuses if s.status != "compromised"]
    if viable:
        return min(viable, key=lambda s: geo.haversine_m(user[0], user[1],
                                                         s.zone.lon, s.zone.lat))
    return max(statuses, key=lambda s: s.buffer_min)
