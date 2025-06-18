from __future__ import annotations

"""ParkingStore – thread‑safe in‑memory cache for ParkingRecords.

Enhancements (2025‑06‑18)
------------------------
* **Constants enrichment**
  * Vacancy status text / color, link‑type text などを追加
* **Bug‑fix**
  * `road_link` 生成時に `None += str` が起こり得た問題を修正。
"""

import threading
from typing import Any, Final

import orjson  # 高速 JSON シリアライザ

# --- domain‑specific helpers ---------------------------------------------
from darc.l5_data_units import (
    ParkingRecord,
    DistanceUnitParking,
    CapacityClass,
    HeightLimit,
    VehicleLimit,
    DiscountCondition,
    FeeUnit,
    VacancyStatus,
    LinkType,
)

# ---------------------------------------------------------------------------
# Constants (Enum‑keyed dictionaries)
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
    VacancyStatus.CONGEST: "混雑",
    VacancyStatus.FULL: "満車",
    VacancyStatus.CLOSED: "閉鎖",
    VacancyStatus.UNDEFINED_4: "不明",
    VacancyStatus.UNDEFINED_5: "不明",
    VacancyStatus.UNDEFINED_6: "不明",
    VacancyStatus.UNKNOWN: "不明",
}

VACANCY_STATUS_COLOR: Final[dict[VacancyStatus, str]] = {
    VacancyStatus.EMPTY: "#28a745",
    VacancyStatus.CONGEST: "#fd7e14",
    VacancyStatus.FULL: "#dc3545",
    VacancyStatus.CLOSED: "#6c757d",
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
# Helper – coordinate normalization
# ---------------------------------------------------------------------------


def _round_coord(value: float, digits: int = 7) -> float:
    return round(value, digits)


# ---------------------------------------------------------------------------
# ParkingStore
# ---------------------------------------------------------------------------


class ParkingStore:
    """In‑memory cache that deduplicates :class:`ParkingRecord` by coordinates."""

    __slots__ = ("_data", "_lock")

    def __init__(self) -> None:
        self._data: dict[str, tuple[float, float, ParkingRecord]] = {}
        self._lock = threading.Lock()

    # ---------------- Public API ----------------
    def upsert(self, lat: float, lon: float, record: ParkingRecord) -> None:
        lat_r, lon_r = _round_coord(lat), _round_coord(lon)
        with self._lock:
            self._data[f"P:{lat_r},{lon_r}"] = (lat_r, lon_r, record)

    def to_geojson(self) -> dict[str, Any]:
        with self._lock:
            snapshot = list(self._data.items())
        features = [self._to_feature(k, *tpl) for k, tpl in snapshot]
        return {"type": "FeatureCollection", "features": features}

    def to_geojson_bytes(self, opts: int | None = None) -> bytes:
        if opts is None:
            opts = orjson.OPT_NON_STR_KEYS | orjson.OPT_SERIALIZE_NUMPY
        return orjson.dumps(self.to_geojson(), option=opts)

    # ---------------- Helpers ----------------
    @staticmethod
    def _to_feature(
        code: str, lat: float, lon: float, rec: ParkingRecord
    ) -> dict[str, Any]:
        props: dict[str, Any] = {
            "name": getattr(rec.ext1, "name", None),
            "vacancy_status": rec.vacancy_status.name,
            "vacancy_status_jp": VACANCY_STATUS_TEXT.get(rec.vacancy_status, "不明"),
            "vacancy_color": VACANCY_STATUS_COLOR.get(rec.vacancy_status, "#6c757d"),
        }

        # --- Ext1 --------------------------------------------------------
        if (ext1 := getattr(rec, "ext1", None)) is not None:
            if ext1.entrance_distance is not None:
                factor = 10 if ext1.distance_unit == DistanceUnitParking.TEN_M else 100
                props["entrance_distance"] = f"{ext1.entrance_distance * factor} m"
            road_label = None
            if ext1.link_number != 0:
                road_label = LINK_TYPE_TEXT.get(ext1.link_type, "")
                road_label = f"{road_label} {ext1.link_number}".strip()
            props["road_link"] = road_label

        # --- Ext2 --------------------------------------------------------
        if (ext2 := getattr(rec, "ext2", None)) is not None:
            props["capacity_class"] = CAPACITY_CLASS_TEXT.get(ext2.capacity_class)
            if (rate := ext2.vacancy_rate_10pct) is not None:
                props["vacancy_rate"] = f"{rate * 10}%"
            props["waiting_time"] = (
                f"{ext2.waiting_time_10min * 10}分"
                if ext2.waiting_time_10min is not None
                else "0分"
            )
            if ext2.fee_code is None:
                props["fee_text"] = "料金不明"
            else:
                price = ext2.fee_code * 10
                props["fee_text"] = (
                    f"{price}円 / {FEE_UNIT_TEXT.get(ext2.fee_unit, '不明')}"
                )
            _fmt = lambda h, m10: (
                "--" if h is None or m10 is None else f"{h:02d}:{m10 * 10:02d}"
            )
            props["hours_text"] = (
                f"{_fmt(ext2.start_hour, ext2.start_min10)} - {_fmt(ext2.end_hour, ext2.end_min10)}"
            )
            props["height_limit"] = HEIGHT_LIMIT_TEXT.get(ext2.height_limit)
            props["vehicle_limit"] = VEHICLE_LIMIT_TEXT.get(ext2.vehicle_limit)
            props["discount"] = DISCOUNT_TEXT.get(ext2.discount_condition)

        return {
            "type": "Feature",
            "id": code,
            "geometry": {"type": "Point", "coordinates": [lon, lat]},
            "properties": props,
        }
