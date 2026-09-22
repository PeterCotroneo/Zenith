"""SGP4 orbit propagation for Zenith.

A TLE gives a satellite's orbital elements; SGP4 propagates them to a position at
any instant. QGIS ships no SGP4 propagator, so we vendor the pure-Python ``sgp4``
library (Brandon Rhodes, MIT) under ``vendor/`` and put it on the path. SGP4
outputs a TEME (inertial) position in km; we convert it to the sub-satellite
point (lat/lon on WGS84) and altitude using Greenwich Mean Sidereal Time.

Validated against the live ISS: altitude ~420 km, speed ~7.66 km/s, latitude
within its 51.6° inclination.
"""

import logging
import math
import os
import sys

_VENDOR = os.path.join(os.path.dirname(__file__), "vendor")
if _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)

from sgp4.earth_gravity import wgs72   # noqa: E402  (vendored; path set above)
from sgp4.io import twoline2rv         # noqa: E402

_log = logging.getLogger("zenith")
_A = 6378.137                # WGS84 semi-major axis, km
_F = 1.0 / 298.257223563     # flattening
_E2 = _F * (2 - _F)


def _safe_twoline(line1, line2):
    try:
        return twoline2rv(line1, line2, wgs72)
    except Exception as exc:  # noqa: BLE001 - skip malformed TLEs
        _log.debug("bad TLE skipped: %s", exc)
        return None


def parse_tles(text):
    """Parse a CelesTrak TLE listing into ``[(name, satrec), ...]``."""
    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    out = []
    i = 0
    n = len(lines)
    while i + 2 <= n - 1:
        name, l1, l2 = lines[i], lines[i + 1], lines[i + 2]
        if l1.startswith("1 ") and l2.startswith("2 "):
            sat = _safe_twoline(l1, l2)
            if sat is not None:
                out.append((name.strip(), sat))
            i += 3
        else:
            i += 1
    return out


def _julian_date(dt):
    y, m = dt.year, dt.month
    if m <= 2:
        y -= 1
        m += 12
    a = y // 100
    b = 2 - a + a // 4
    day_frac = (dt.hour + dt.minute / 60.0 +
                (dt.second + dt.microsecond / 1e6) / 3600.0) / 24.0
    return (int(365.25 * (y + 4716)) + int(30.6001 * (m + 1)) + dt.day
            + b - 1524.5 + day_frac)


def _teme_to_geodetic(r, jd):
    """TEME position (km) + Julian date -> (lat°, lon°, alt km)."""
    x, y, z = r
    t = (jd - 2451545.0) / 36525.0
    gmst = (280.46061837 + 360.98564736629 * (jd - 2451545.0)
            + 0.000387933 * t * t - t * t * t / 38710000.0)
    gmst = math.radians(gmst % 360.0)
    cg, sg = math.cos(gmst), math.sin(gmst)
    xe = cg * x + sg * y
    ye = -sg * x + cg * y
    ze = z
    lon = math.atan2(ye, xe)
    p = math.hypot(xe, ye)
    lat = math.atan2(ze, p * (1 - _E2))
    alt = 0.0
    for _ in range(6):
        sl = math.sin(lat)
        nrm = _A / math.sqrt(1 - _E2 * sl * sl)
        alt = p / math.cos(lat) - nrm
        lat = math.atan2(ze, p * (1 - _E2 * nrm / (nrm + alt)))
    return math.degrees(lat), math.degrees(lon), alt


def propagate(satrec, dt_utc):
    """Return {lat, lon, alt, speed} for a satrec at ``dt_utc``, or None."""
    pos, vel = satrec.propagate(
        dt_utc.year, dt_utc.month, dt_utc.day,
        dt_utc.hour, dt_utc.minute, dt_utc.second + dt_utc.microsecond / 1e6)
    if pos is None or pos[0] is None or getattr(satrec, "error", 0):
        return None
    lat, lon, alt = _teme_to_geodetic(pos, _julian_date(dt_utc))
    speed = math.sqrt(vel[0] ** 2 + vel[1] ** 2 + vel[2] ** 2)
    return {"lat": lat, "lon": lon, "alt": alt, "speed": speed}
