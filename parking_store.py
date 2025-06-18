"""Refactored ParkingStore and related helpers.

This module provides a thread-safe, in-memory cache that deduplicates
:class:`ParkingRecord` instances by normalized coordinates and exports them
as GeoJSON.  The API is largely compatible with the original implementation
while improving readability, separation of concerns, and testability.
"""

from __future__ import annotations

import threading
from typing import Any, Final, Dict, Tuple

import orjson

from darc.helpers import LinkType
from darc.parking import (
    CapacityClass,
    DiscountCondition,
    DistanceUnitParking,
    FeeUnit,
    HeightLimit,
    ParkingRecord,
    VacancyStatus,
    VehicleLimit,
)

# ---------------------------------------------------------------------------
# Constants (Enum-keyed dictionaries)
# ---------------------------------------------------------------------------

FEE_UNIT_TEXT: Final[dict[FeeUnit, str]] = {
    FeeUnit.MIN_30: "30分",
    FeeUnit.HOUR_1: "1時間",
    FeeUnit.HOUR_2: "2時間",
    FeeUnit.HOUR_3: "3時間",
    FeeUnit.HALF_DAY: "半日",
    FeeUnit.ONE_DAY: "1日",
    FeeUnit.ONCE: "1回",
    FeeUnit.UNKNOWN: "不明",
}

CAPACITY_CLASS_TEXT: Final[dict[CapacityClass, str]] = {
    CapacityClass.UNDER_20: "〜20台",
    CapacityClass.UNDER_50: "〜50台",
    CapacityClass.UNDER_100: "〜100台",
    CapacityClass.UNDER_200: "〜200台",
    CapacityClass.UNDER_500: "〜500台",
    CapacityClass.UNDER_1000: "〜1000台",
    CapacityClass.OVER_1000: "1000台超",
    CapacityClass.UNKNOWN: "不明",
}

VACANCY_STATUS_TEXT: Final[dict[VacancyStatus, str]] = {
    VacancyStatus.EMPTY: "空車",
    VacancyStatus.CONGESTED: "混雑",
    VacancyStatus.FULL: "満車",
    VacancyStatus.CLOSED: "閉鎖",
    VacancyStatus.UNDEFINED_4: "不明",
    VacancyStatus.UNDEFINED_5: "不明",
    VacancyStatus.UNDEFINED_6: "不明",
    VacancyStatus.UNKNOWN: "不明",
}

VACANCY_STATUS_COLOR: Final[dict[VacancyStatus, str]] = {
    VacancyStatus.EMPTY: "#28a745",  # green
    VacancyStatus.CONGESTED: "#fd7e14",  # orange
    VacancyStatus.FULL: "#dc3545",  # red
    VacancyStatus.CLOSED: "#6c757d",  # gray
}

LINK_TYPE_TEXT: Final[dict[LinkType, str]] = {
    LinkType.EXPRESSWAY: "高速道路",
    LinkType.URBAN_EXPRESSWAY: "都市高速",
    LinkType.ARTERIAL: "主要道",
    LinkType.OTHER: "その他",
}

HEIGHT_LIMIT_TEXT: Final[dict[HeightLimit, str]] = {
    HeightLimit.NONE: "制限なし",
    HeightLimit.LIMITED: "制限あり",
    HeightLimit.UNDEFINED: "不明",
    HeightLimit.UNKNOWN: "不明",
}

VEHICLE_LIMIT_TEXT: Final[dict[VehicleLimit, str]] = {
    VehicleLimit.NONE: "制限なし",
    VehicleLimit.LARGE_VEHICLE: "大型不可",
    VehicleLimit.THREE_NUMBER: "3ナンバー不可",
    VehicleLimit.OTHER: "その他制限",
}

DISCOUNT_TEXT: Final[dict[DiscountCondition, str]] = {
    DiscountCondition.NONE: "割引なし",
    DiscountCondition.EXISTS: "割引あり",
    DiscountCondition.UNDEFINED: "不明",
    DiscountCondition.UNKNOWN: "不明",
}

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

Coord = Tuple[float, float]
Feature = Dict[str, Any]


def _round_coord(value: float, digits: int = 7) -> float:
    """Round coordinate value to *digits* decimal places (default: 7)."""
    return round(value, digits)


def _format_hhmm(hour: int | None, minute: int | None) -> str:
    """Return time as "HH:MM" or "--" when either component is ``None``."""
    return "--" if hour is None or minute is None else f"{hour:02d}:{minute:02d}"


# ---------------------------------------------------------------------------
# ParkingStore
# ---------------------------------------------------------------------------


class ParkingStore:
    """Thread-safe, in-memory cache that deduplicates :class:`ParkingRecord` by
    rounded coordinates.  `precision` controls the number of decimal digits used
    for rounding (default: 7, roughly ~1.1 cm).
    """

    __slots__ = ("_data", "_lock", "_precision")

    def __init__(self, precision: int = 7) -> None:
        self._precision = precision
        # key -> ((lat, lon), record)
        self._data: dict[str, tuple[Coord, ParkingRecord]] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def upsert(self, lat: float, lon: float, record: ParkingRecord) -> None:
        """Insert *record* or overwrite an existing one at the same rounded
        coordinate.
        """
        lat_r, lon_r = _round_coord(lat, self._precision), _round_coord(
            lon, self._precision
        )
        key = f"P:{lat_r},{lon_r}"
        with self._lock:
            self._data[key] = ((lat_r, lon_r), record)

    def to_geojson(self) -> dict[str, Any]:
        """Return a GeoJSON FeatureCollection view of the current cache."""
        with self._lock:
            snapshot = list(self._data.items())  # copy to avoid long lock hold
        features = [self._to_feature(code, *payload) for code, payload in snapshot]
        return {"type": "FeatureCollection", "features": features}

    def to_geojson_bytes(self, *, opts: int | None = None) -> bytes:
        """Serialize :meth:`to_geojson` result with *orjson*.

        By default, ``OPT_NON_STR_KEYS`` and ``OPT_SERIALIZE_NUMPY`` are enabled
        but you may override *opts* if needed.
        """
        if opts is None:
            opts = orjson.OPT_NON_STR_KEYS | orjson.OPT_SERIALIZE_NUMPY
        return orjson.dumps(self.to_geojson(), option=opts)

    # Convenience dunder methods ------------------------------------------------
    def __len__(self) -> int:
        """Return the number of cached parking records."""
        with self._lock:
            return len(self._data)

    def __iter__(self):
        """Iterate over ``ParkingRecord`` instances (unsorted)."""
        with self._lock:
            return (record for (_, record) in self._data.values())

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    @staticmethod
    def _to_feature(
        code: str, coord: Coord, rec: ParkingRecord
    ) -> Feature:
        """Convert a single cache entry to a GeoJSON *Feature*."""
        lat, lon = coord
        props: dict[str, Any] = {
            "name": getattr(rec.ext1, "name", None),
            "vacancy_status": rec.vacancy_status.name,
            "vacancy_status_jp": VACANCY_STATUS_TEXT.get(rec.vacancy_status, "不明"),
            "vacancy_color": VACANCY_STATUS_COLOR.get(rec.vacancy_status, "#ffffff"),
        }

        # --- ext1 ------------------------------------------------------
        if (ext1 := getattr(rec, "ext1", None)) is not None:
            if ext1.entrance_distance is not None:
                factor = 10 if ext1.distance_unit == DistanceUnitParking.TEN_M else 100
                props["entrance_distance"] = f"{ext1.entrance_distance * factor} m"

            if ext1.link_number:
                road_prefix = LINK_TYPE_TEXT.get(ext1.link_type, "")
                props["road_link"] = f"{road_prefix} {ext1.link_number}".strip()

        # --- ext2 ------------------------------------------------------
        if (ext2 := getattr(rec, "ext2", None)) is not None:
            props.update(_props_from_ext2(ext2))

        return {
            "type": "Feature",
            "id": code,
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": props,
        }


# ---------------------------------------------------------------------------
# _props_from_ext2 (factored-out helper)
# ---------------------------------------------------------------------------


def _props_from_ext2(ext2) -> dict[str, Any]:  # type: ignore[valid-type]
    """Return a dictionary of GeoJSON properties derived from *ext2*."""
    props: dict[str, Any] = {
        "capacity_class": CAPACITY_CLASS_TEXT.get(ext2.capacity_class),
        "waiting_time": f"{ext2.waiting_time_min or 0}分",
        "height_limit": HEIGHT_LIMIT_TEXT.get(ext2.height_limit),
        "vehicle_limit": VEHICLE_LIMIT_TEXT.get(ext2.vehicle_limit),
        "discount": DISCOUNT_TEXT.get(ext2.discount_condition),
    }

    # Vacancy rate -----------------------------------------------------
    if (rate := ext2.vacancy_rate_pct) is not None:
        props["vacancy_rate"] = f"{rate}%"

    # Fees -------------------------------------------------------------
    if ext2.fee_code is None:
        props["fee_text"] = "料金不明"
    else:
        unit_label = FEE_UNIT_TEXT.get(ext2.fee_unit, "不明")
        props["fee_text"] = f"{ext2.fee_code}円 / {unit_label}"

    # Operating hours --------------------------------------------------
    props["hours_text"] = (
        f"{_format_hhmm(ext2.start_hour, ext2.start_min)} - {_format_hhmm(ext2.end_hour, ext2.end_min)}"
    )

    return props
