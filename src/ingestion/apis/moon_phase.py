"""Moon phase calculation using the ephem library.

Returns moon phase as 0.0 (new moon) → 0.5 (full moon) → 1.0 (new moon).
"""

from datetime import datetime, date
from typing import Optional

try:
    import ephem
    _EPHEM_AVAILABLE = True
except ImportError:
    _EPHEM_AVAILABLE = False


def get_moon_phase(dt: datetime) -> float:
    """Return moon phase [0.0, 1.0) for a given UTC datetime.

    0.0 = new moon, 0.25 = first quarter, 0.5 = full moon, 0.75 = last quarter

    Falls back to a simple approximation if ephem is not installed.
    """
    if _EPHEM_AVAILABLE:
        return _ephem_phase(dt)
    return _approx_phase(dt)


def get_moon_phase_series(timestamps: list[datetime]) -> list[float]:
    return [get_moon_phase(ts) for ts in timestamps]


def _ephem_phase(dt: datetime) -> float:
    moon = ephem.Moon(dt)
    return float(moon.phase) / 100.0  # ephem returns 0-100


def _approx_phase(dt: datetime) -> float:
    """Simple approximation without ephem."""
    # Known new moon: 2000-01-06 18:14 UTC
    ref = datetime(2000, 1, 6, 18, 14)
    synodic = 29.53058867  # days
    delta = (dt - ref).total_seconds() / 86400.0
    phase = (delta % synodic) / synodic
    # Convert to 0=new, 0.5=full, 1=new
    return phase


if __name__ == "__main__":
    from datetime import datetime
    dt = datetime(2024, 1, 25, 12, 0)  # full moon approximate
    print(f"Moon phase: {get_moon_phase(dt):.3f}")
