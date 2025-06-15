"""
ARIB STD‑B3 24‑bit map position + 10 000‑grid relative coordinate → WGS‑84
-----------------------------------------------------------------------
This script converts the coordinate scheme described in ARIB STD‑B3 into

* **Tokyo datum** (旧日本測地系 / Bessel ellipsoid)
* **WGS‑84 / JGD2000** (世界測地系)

The input consists of two parts:
1. **Map Position X / Y** (12‑bit each)
2. **Relative X / Y** inside the corresponding *2‑nd mesh*, measured on a
   10 000 × 10 000 lattice (resolution ≈ 1 m).

Example values taken from the previous discussion:
    Map Position X = 0x8E8  (2280)
    Map Position Y = 0x848  (2120)
    Relative X     =   651
    Relative Y     =   132

Running this file as a script prints both datums in decimal degrees and
DMS.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

# ---------------------------------------------------------------------------
# Constants (angles expressed in decimal degrees)
# ---------------------------------------------------------------------------

LAT_ORIGIN_DEG = 24 + 40 / 60          # 24°40′00″ N → 24.666 666…°
LON_ORIGIN_DEG = 122.0                 # 122°00′00″ E

FIRST_MESH_LAT = 40 / 60              # 40′   = 0.666 666 …°
FIRST_MESH_LON = 1.0                  # 1°
SECOND_MESH_LAT = FIRST_MESH_LAT / 8  # 5′    = 0.083 333 …°
SECOND_MESH_LON = FIRST_MESH_LON / 8  # 7′30″ = 0.125°

# How much one relative unit (1 / 10 000) represents inside a 2nd mesh
UNIT_LAT = SECOND_MESH_LAT / 10_000   # ≈ 0.000 008 333 …°  (≈ 0.925 m)
UNIT_LON = SECOND_MESH_LON / 10_000   # ≈ 0.000 012 5°     (≈ 1.12 m @ 35 °N)

# ---------------------------------------------------------------------------
# Data classes & helpers
# ---------------------------------------------------------------------------

@dataclass
class DMS:
    deg: int
    min: int
    sec: float

    def __str__(self) -> str:  # "35°40′03.96″"
        return f"{self.deg:02d}°{self.min:02d}′{self.sec:06.3f}″"


def deg_to_dms(angle: float) -> DMS:
    """Convert decimal–degree to degree‑minute‑second."""
    neg = angle < 0
    angle = abs(angle)
    deg = int(angle)
    rem = (angle - deg) * 60
    minutes = int(rem)
    seconds = (rem - minutes) * 60
    if neg:
        deg = -deg
    return DMS(deg, minutes, seconds)


def tokyo_to_wgs84(lat_t: float, lon_t: float) -> Tuple[float, float]:
    """Approximate Tokyo‑datum → WGS‑84 conversion.
    Formula: Geospatial Information Authority of Japan (GSI),
    accuracy ≈ a few metres in Japan.
    """
    lat_w = (
        lat_t
        - 0.00010695 * lat_t
        + 0.000017464 * lon_t
        + 0.0046017
    )
    lon_w = (
        lon_t
        - 0.000046038 * lat_t
        - 0.000083043 * lon_t
        + 0.010040
    )
    return lat_w, lon_w


# ---------------------------------------------------------------------------
# Core calculation
# ---------------------------------------------------------------------------

def parse_mesh(value: int) -> Tuple[int, int, int]:
    """Return (1st_mesh_idx, 2nd_mesh_idx, 4‑bit_rel) from 12‑bit value."""
    first = (value >> 7) & 0x1F  # upper 5 bits
    second = (value >> 4) & 0x07  # next 3 bits
    rel4 = value & 0x0F           # lower 4 bits
    return first, second, rel4


def arib_to_tokyo_deg(
    map_x: int,
    map_y: int,
    rel_x: int,
    rel_y: int,
    ignore_rel4: bool = True,
) -> Tuple[float, float]:
    """Convert ARIB coordinates to Tokyo datum (decimal degrees).

    Parameters
    ----------
    map_x, map_y : int (0‑4095)
        12‑bit Map Position X / Y
    rel_x, rel_y : int (0‑10 000)
        Relative position inside the 2‑nd mesh (10 000 × 10 000 grid).
    ignore_rel4 : bool, default True
        If False, 4‑bit sub‑mesh offsets contained in map_x/map_y are added
        *before* applying the 10 000‑grid offset. The ARIB spec often uses
        either the 4‑bit or the 10 000‑grid refinement—not both—so the
        default is to ignore them.
    """
    x1, x2, x_rel4 = parse_mesh(map_x)
    y1, y2, y_rel4 = parse_mesh(map_y)

    # Base (south‑west corner of the 2‑nd mesh)
    lat = LAT_ORIGIN_DEG + y1 * FIRST_MESH_LAT + y2 * SECOND_MESH_LAT
    lon = LON_ORIGIN_DEG + x1 * FIRST_MESH_LON + x2 * SECOND_MESH_LON

    if not ignore_rel4:
        lat += y_rel4 * (SECOND_MESH_LAT / 16)
        lon += x_rel4 * (SECOND_MESH_LON / 16)

    # Apply 10 000‑grid relative offset
    lat += rel_y * UNIT_LAT
    lon += rel_x * UNIT_LON

    return lat, lon


# ---------------------------------------------------------------------------
# Command‑line demo
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    # Example values from the discussion
    map_x = 0x8E8  # 2280
    map_y = 0x848  # 2120
    rel_x = 651
    rel_y = 132

    lat_t, lon_t = arib_to_tokyo_deg(map_x, map_y, rel_x, rel_y)
    lat_w, lon_w = tokyo_to_wgs84(lat_t, lon_t)

    print("ARIB STD‑B3 coordinate conversion demo\n")
    print("Input:")
    print(f"  Map Position X: {map_x} (0x{map_x:X})")
    print(f"  Map Position Y: {map_y} (0x{map_y:X})")
    print(f"  Relative X:     {rel_x}")
    print(f"  Relative Y:     {rel_y}\n")

    print("Tokyo Datum (旧日本測地系 / Bessel):")
    print(
        f"  {lat_t:.6f}°, {lon_t:.6f}°  ( {deg_to_dms(lat_t)} N , {deg_to_dms(lon_t)} E )"
    )

    print("\nWGS‑84 / JGD2000 (世界測地系):")
    print(
        f"  {lat_w:.6f}°, {lon_w:.6f}°  ( {deg_to_dms(lat_w)} N , {deg_to_dms(lon_w)} E )"
    )
