import enum
from dataclasses import dataclass
from datetime import time
from typing import Self, TypeVar, cast

from bitstring import ConstBitStream, ReadError

from .arib_string import AribStringDecoder
from .l5_data import DataUnitBase, GenericDataUnit

# ──────────────────────────────── Exceptions ────────────────────────────────


class BitstreamEndError(RuntimeError):
    """Raised when the bitstream ends unexpectedly while parsing a field."""


# ─────────────────────────────── Enumerations ───────────────────────────────


class CongestionDegree(enum.IntEnum):
    UNKNOWN = 0
    FREE = 1
    SLOW = 2
    JAM = 3


class DistanceUnit(enum.IntEnum):
    TEN_M = 0
    HUNDRED_M = 1
    ONE_KM = 2
    UNDEFINED = 3


class TimeUnit(enum.IntEnum):
    SEC_10 = 0
    MINUTE = 1


class TravelTimeKind(enum.IntEnum):
    CURRENT = 0
    PREDICTION = 1


class LinkType(enum.IntEnum):
    EXPRESSWAY = 0
    URBAN_EXPRESSWAY = 1
    ARTERIAL = 2
    OTHER = 3


# ─────────────────────────────── Enumerations ───────────────────────────────


class RegulationAccidentExtFlag(enum.IntEnum):
    BASIC = 0  # 基本情報のみ
    BASIC_EXT1 = 1  # + 拡張構成1
    BASIC_EXT1_EXT2 = 2  # + 拡張構成1 + 2
    MODE_RESERVED = 3  # 予約（現行規格では未使用）


class CauseEvent(enum.IntEnum):
    NONE = 0  # 原因事象なし
    ACCIDENT = 1  # 事故
    FIRE = 2  # 火災
    BREAKDOWN = 3  # 故障車
    OBSTACLE = 4  # 路上障害物
    CONSTRUCTION = 5  # 工事
    WORK = 6  # 作業
    EVENT = 7  # 行事等
    WEATHER = 8  # 気象
    DISASTER = 9  # 災害
    EARTHQUAKE_WARNING = 10  # 地震警戒宣言
    UNDEFINED_11 = 11
    UNDEFINED_12 = 12
    UNDEFINED_13 = 13
    OTHER = 14
    UNKNOWN = 15


class RegulationContent(enum.IntEnum):
    NONE = 0
    TRAFFIC_STOP = 1  # 通行止め
    RIGHT_TURN_RESTRICT = 2  # 右左折規制
    SPEED_LIMIT = 3
    LANE_RESTRICT = 4
    SHOULDER_RESTRICT = 5
    CHAIN_RESTRICT = 6
    ON_RAMP_RESTRICT = 7
    LARGE_VEHICLE_RESTRICT = 8  # 大型通行止め
    TRAFFIC_CONTROL = 9  # 移動規制
    OFF_RAMP_RESTRICT = 10
    UNDEFINED_11 = 11
    UNDEFINED_12 = 12
    UNDEFINED_13 = 13
    OTHER = 14
    UNKNOWN = 15


# ─────────────────────────────── Dataclasses ────────────────────────────────


@dataclass(slots=True)
class RegulationAccidentExt1:
    distance_unit: DistanceUnit
    distance_len_raw: int  # 0-63
    congestion_degree: CongestionDegree
    travel_time_kind: TravelTimeKind
    travel_time_unit: TimeUnit
    travel_time_val_raw: int  # 0-15

    # convenience
    @property
    def distance_m(self) -> int | None:
        if self.distance_unit == DistanceUnit.TEN_M:
            return self.distance_len_raw * 10
        if self.distance_unit == DistanceUnit.HUNDRED_M:
            return self.distance_len_raw * 100
        if self.distance_unit == DistanceUnit.ONE_KM:
            return self.distance_len_raw * 1000
        return None

    @property
    def travel_time_s(self) -> int:
        base = 10 if self.travel_time_unit == TimeUnit.SEC_10 else 60
        return self.travel_time_val_raw * base

    # --- parser -----------------------------------------------------
    @classmethod
    def parse(cls, bs: ConstBitStream) -> Self:
        du = DistanceUnit(bs.read("uint:2"))
        dist = bs.read("uint:6")
        cong = CongestionDegree(bs.read("uint:2"))
        _ = bs.read("uint:2")  # spare bits
        ttk = TravelTimeKind(bs.read("uint:1"))
        ttu = TimeUnit(bs.read("uint:1"))
        ttval = bs.read("uint:4")
        bs.read("pad:14")  # skip remaining spare
        return cls(du, dist, cong, ttk, ttu, ttval)


@dataclass(slots=True)
class RegulationAccidentExt2:
    start_month_raw: int  # 1-12 (0=none)
    start_day_raw: int  # 1-31
    start_hour_raw: int  # 0-23
    start_min10_raw: int  # 0-5  (×10)
    end_hour_raw: int  # 0-23
    end_min10_raw: int  # 0-5

    # convenience
    @property
    def start_time(self) -> time | None:
        if self.start_month_raw == 0:
            return None
        return time(self.start_hour_raw, self.start_min10_raw * 10)

    @property
    def end_time(self) -> time | None:
        return time(self.end_hour_raw, self.end_min10_raw * 10)

    # --- parser -----------------------------------------------------
    @classmethod
    def parse(cls, bs: ConstBitStream) -> Self:
        mon = bs.read("uint:4")
        day = bs.read("uint:5")
        sh = bs.read("uint:5")
        sm10 = bs.read("uint:6")
        eh = bs.read("uint:5")
        em10 = bs.read("uint:6")
        bs.read("pad:17")  # spare bits
        return cls(mon, day, sh, sm10, eh, em10)


@dataclass(slots=True)
class RegulationAccidentBasicInfo:
    mesh_flag: bool
    name_flag: bool
    link_type: LinkType
    link_number: int
    continuous_links: int | None  # Via only
    coord_x_hi: int | None  # upper 8‑bit
    coord_y_hi: int | None
    name: str | None


@dataclass(slots=True)
class RegulationAccidentRecord:
    ext_flag: RegulationAccidentExtFlag
    link_count: int
    cause_event: CauseEvent
    regulation_content: RegulationContent
    distance_unit: DistanceUnit
    regulation_length_raw: int
    basics: list[RegulationAccidentBasicInfo]
    ext1: RegulationAccidentExt1 | None = None
    ext2: RegulationAccidentExt2 | None = None

    @property
    def regulation_length(self) -> int | None:
        return (
            None
            if self.regulation_length_raw in (0, 63)
            else self.regulation_length_raw
        )


# ──────────────────────────────── Main Unit ─────────────────────────────────


@dataclass
class RegulationAccidentDataUnit(DataUnitBase):
    """Fully‑parsed *Regulation / Accident* data‑unit (parameter 0x41)."""

    records: list[RegulationAccidentRecord]

    # -----------------------------------------------------------
    def __init__(
        self, parameter: int, link_flag: int, records: list[RegulationAccidentRecord]
    ):
        super().__init__(parameter, link_flag)
        self.records = records

    # -----------------------------------------------------------
    @classmethod
    def from_generic(cls, generic: GenericDataUnit) -> Self:
        bs = ConstBitStream(generic.data_unit_data)
        recs: list[RegulationAccidentRecord] = []
        while bs.pos < bs.len:
            start = bs.pos
            try:
                recs.append(cls._parse_record(bs))
            except (ReadError, BitstreamEndError):
                break
            assert bs.pos > start
        return cls(generic.data_unit_parameter, generic.data_unit_link_flag, recs)

    # -----------------------------------------------------------
    # low‑level helpers
    # -----------------------------------------------------------
    @staticmethod
    def _read_name(bs: ConstBitStream) -> str:
        length = bs.read("uint:8")
        data = bs.read(length * 8).bytes if length else b""
        return AribStringDecoder().decode(data)

    # -----------------------------------------------------------
    # record‑level parser
    # -----------------------------------------------------------
    @classmethod
    def _parse_record(
        cls, bs: ConstBitStream
    ) -> RegulationAccidentRecord:  # noqa: C901
        # ─ Header ------------------------------------------------------
        ext_flag = RegulationAccidentExtFlag(bs.read("uint:2"))
        link_total = bs.read("uint:6")
        cause_event = _safe_enum(CauseEvent, bs.read("uint:4"))
        regulation_content = _safe_enum(RegulationContent, bs.read("uint:4"))
        distance_unit = _safe_enum(DistanceUnit, bs.read("uint:2"))
        regulation_length_raw = bs.read("uint:6")

        basics: list[RegulationAccidentBasicInfo] = []
        remaining = link_total

        # 1) Start block -----------------------------------------------
        basics.append(cls._parse_start(bs))
        remaining -= 1

        # 2) End block (if more links) ---------------------------------
        if remaining >= 1:
            basics.append(cls._parse_end(bs))
            remaining -= 1

        # 3) Via blocks -------------------------------------------------
        while remaining > 0:
            via, covered = cls._parse_via(bs)
            basics.append(via)
            remaining -= 1
            if remaining < 0:
                raise BitstreamEndError("Via block count exceeds header link_total")

        # 4) Extensions (once) -----------------------------------------
        ext1 = ext2 = None
        if ext_flag in (
            RegulationAccidentExtFlag.BASIC_EXT1,
            RegulationAccidentExtFlag.BASIC_EXT1_EXT2,
        ):
            ext1 = RegulationAccidentExt1.parse(bs)
        if ext_flag == RegulationAccidentExtFlag.BASIC_EXT1_EXT2:
            ext2 = RegulationAccidentExt2.parse(bs)

        return RegulationAccidentRecord(
            ext_flag=ext_flag,
            link_count=link_total,
            cause_event=cause_event,
            regulation_content=regulation_content,
            distance_unit=distance_unit,
            regulation_length_raw=regulation_length_raw,
            basics=basics,
            ext1=ext1,
            ext2=ext2,
        )

    # -----------------------------------------------------------
    # block‑level parsers
    # -----------------------------------------------------------
    @classmethod
    def _parse_start(cls, bs: ConstBitStream) -> RegulationAccidentBasicInfo:
        mesh = bs.read("bool")
        name_f = bs.read("bool")
        link_type = _safe_enum(LinkType, bs.read("uint:2"))
        link_hi = bs.read("uint:4")
        link_lo = bs.read("uint:8")
        name = cls._read_name(bs) if name_f else None
        return RegulationAccidentBasicInfo(
            mesh, name_f, link_type, (link_hi << 8) | link_lo, None, None, None, name
        )

    @classmethod
    def _parse_end(cls, bs: ConstBitStream) -> RegulationAccidentBasicInfo:
        """Parse *End block* (always final link, present when link_count ≥ 2).

        According to the spec, the X/Y upper‑byte rows are present regardless of
        *mesh_flag* for this block, so we read them unconditionally.
        """
        mesh = bs.read("bool")  # may still be useful for receiver
        name_f = bs.read("bool")
        link_type = _safe_enum(LinkType, bs.read("uint:2"))
        link_hi = bs.read("uint:4")
        link_lo = bs.read("uint:8")
        coord_x = coord_y = None
        if mesh:
            coord_x = bs.read("uint:8")
            coord_y = bs.read("uint:8")  # Y upper‑byte
        name = cls._read_name(bs) if name_f else None
        return RegulationAccidentBasicInfo(
            mesh,
            name_f,
            link_type,
            (link_hi << 8) | link_lo,
            None,
            coord_x,
            coord_y,
            name,
        )

    # -----------------------------------------------------------
    @classmethod
    def _parse_via(cls, bs: ConstBitStream) -> tuple[RegulationAccidentBasicInfo, int]:
        """Parse *Via block* and return (block, links_covered)."""
        mesh = bs.read("bool")
        name_f = bs.read("bool")
        link_type = _safe_enum(LinkType, bs.read("uint:2"))
        link_hi = bs.read("uint:4")
        link_lo = bs.read("uint:8")
        cont_links = bs.read("uint:8")  # additional links after the first
        coord_x = coord_y = None
        if mesh:
            coord_x = bs.read("uint:8")
            coord_y = bs.read("uint:8")
        name = cls._read_name(bs) if name_f else None
        info = RegulationAccidentBasicInfo(
            mesh,
            name_f,
            link_type,
            (link_hi << 8) | link_lo,
            cont_links,
            coord_x,
            coord_y,
            name,
        )
        return info, cont_links + 1  # this block itself + cont_links


# ────────────────────────────────── Parking ──────────────────────────────────


class ParkingExtFlag(enum.IntEnum):
    BASIC = 0
    BASIC_EXT1 = 1
    BASIC_EXT1_EXT2 = 2
    MODE = 3  # reserved


class VacancyStatus(enum.IntEnum):
    EMPTY = 0
    CONGEST = 1
    FULL = 2
    CLOSED = 3
    UNDEFINED_4 = 4
    UNDEFINED_5 = 5
    UNDEFINED_6 = 6
    UNKNOWN = 7


class DistanceUnitParking(enum.IntEnum):
    TEN_M = 0
    HUNDRED_M = 1


class CapacityClass(enum.IntEnum):
    UNDER_20 = 0
    UNDER_50 = 1
    UNDER_100 = 2
    UNDER_200 = 3
    UNDER_500 = 4
    UNDER_1000 = 5
    OVER_1000 = 6
    UNKNOWN = 7


class HeightLimit(enum.IntEnum):
    NONE = 0
    LIMITED = 1
    UNDEFINED = 2
    UNKNOWN = 3


class VehicleLimit(enum.IntEnum):
    NONE = 0
    LARGE_VEHICLE = 1
    THREE_NUMBER = 2
    UNDEFINED_3 = 3
    UNDEFINED_4 = 4
    UNDEFINED_5 = 5
    OTHER = 6
    UNKNOWN = 7


class DiscountCondition(enum.IntEnum):
    NONE = 0
    EXISTS = 1
    UNDEFINED = 2
    UNKNOWN = 3


class FeeUnit(enum.IntEnum):
    MIN_30 = 0
    HOUR_1 = 1
    HOUR_2 = 2
    HOUR_3 = 3
    HALF_DAY = 4
    ONE_DAY = 5
    ONCE = 6
    UNKNOWN = 7


# ─────────────────────────────── Helper -------------------------------------

E = TypeVar("E", bound=enum.IntEnum)


def _safe_enum(enum_cls: type[E], value: int, fallback_attr: str = "UNKNOWN") -> E:
    """Return *enum_cls(value)*, or *enum_cls.UNKNOWN* if *value* is invalid.
    Keeps static type – useful for mypy/pyright.
    """
    try:
        return enum_cls(value)  # type: ignore[arg-type]
    except ValueError:
        return getattr(enum_cls, fallback_attr)  # type: ignore[return-value]


# ─────────────────────────────── Dataclasses ────────────────────────────────


@dataclass(slots=True)
class ParkingExt1:
    mesh_flag: bool
    name_flag: bool
    link_type: LinkType
    link_number: int
    distance_unit: DistanceUnitParking
    entrance_distance: int
    entrance_x: int | None
    entrance_y: int | None
    name: str | None


@dataclass(slots=True)
class ParkingExt2:
    vacancy_rate_10pct_raw: int
    waiting_time_10min_raw: int
    capacity_class: CapacityClass
    height_limit: HeightLimit
    vehicle_limit: VehicleLimit
    discount_condition: DiscountCondition
    fee_unit: FeeUnit
    fee_code_raw: int
    start_hour_raw: int
    start_min_raw: int
    end_hour_raw: int
    end_min_raw: int

    # ---------- Convenience ----------
    @property
    def vacancy_rate_10pct(self) -> int | None:
        return (
            None if self.vacancy_rate_10pct_raw == 15 else self.vacancy_rate_10pct_raw
        )

    @property
    def waiting_time_10min(self) -> int | None:
        return (
            None if self.waiting_time_10min_raw == 15 else self.waiting_time_10min_raw
        )

    @property
    def fee_code(self) -> int | None:
        return None if self.fee_code_raw == 2047 else self.fee_code_raw

    @property
    def start_hour(self) -> int | None:
        return None if self.start_hour_raw >= 24 else self.start_hour_raw

    @property
    def start_min10(self) -> int | None:
        return None if self.start_min_raw >= 6 else self.start_min_raw

    @property
    def end_hour(self) -> int | None:
        return None if self.end_hour_raw >= 24 else self.end_hour_raw

    @property
    def end_min10(self) -> int | None:
        return None if self.end_min_raw >= 6 else self.end_min_raw


@dataclass(slots=True)
class ParkingRecord:
    ext_flag: ParkingExtFlag
    vacancy_status: VacancyStatus
    is_general: bool
    center_x: int
    center_y: int
    ext1: ParkingExt1 | None = None
    ext2: ParkingExt2 | None = None


# ──────────────────────────────── Main Unit ─────────────────────────────────


@dataclass
class ParkingDataUnit(DataUnitBase):
    """Decoder for the *0x42 Parking Unit* which holds multiple parking records."""

    records: list[ParkingRecord]

    # ------------------------------------------------------------------ #
    def __init__(self, parameter: int, link_flag: int, records: list[ParkingRecord]):
        super().__init__(parameter, link_flag)
        self.records = records

    @classmethod
    def from_generic(cls, generic: GenericDataUnit) -> Self:
        """Parse ``generic.data_unit_data`` into :class:`ParkingDataUnit`."""
        bs = ConstBitStream(generic.data_unit_data)
        records: list[ParkingRecord] = []
        while bs.pos < bs.len:
            pos0 = bs.pos  # loop‑safety checkpoint
            try:
                records.append(cls._parse_record(bs))
            except (ReadError, BitstreamEndError):
                break  # truncated payload
            assert bs.pos > pos0, "_parse_record() must consume bits"
        return cls(generic.data_unit_parameter, generic.data_unit_link_flag, records)

    # ------------------------------------------------------------------ #
    # Low‑level parsers                                                  #
    # ------------------------------------------------------------------ #

    @classmethod
    def _parse_record(cls, bs: ConstBitStream) -> ParkingRecord:  # noqa: C901
        try:
            # --- PB L1 (8 bits) ---
            ext_flag_u2, vacancy_u3, is_general_b = cast(
                tuple[int, int, bool], bs.readlist("uint:2, uint:3, bool, pad:2")
            )
            ext_flag = _safe_enum(ParkingExtFlag, ext_flag_u2)
            vacancy_status = _safe_enum(VacancyStatus, vacancy_u3)

            # --- PB L2‑L3 (32 bits) ---
            center_x, center_y = cast(tuple[int, int], bs.readlist("uint:16, uint:16"))

            # --- Optionals ---
            ext1 = (
                cls._parse_ext1(bs)
                if ext_flag
                in {ParkingExtFlag.BASIC_EXT1, ParkingExtFlag.BASIC_EXT1_EXT2}
                else None
            )
            ext2 = (
                cls._parse_ext2(bs)
                if ext_flag == ParkingExtFlag.BASIC_EXT1_EXT2
                else None
            )

            return ParkingRecord(
                ext_flag=ext_flag,
                vacancy_status=vacancy_status,
                is_general=is_general_b,
                center_x=center_x,
                center_y=center_y,
                ext1=ext1,
                ext2=ext2,
            )
        except ReadError as err:
            raise BitstreamEndError(f"Stream ended mid-record (bit {bs.pos})") from err

    # ------------------------------------------------------------------ #
    # Ext-1 / Ext-2 helpers                                              #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _parse_ext1(bs: ConstBitStream) -> ParkingExt1:  # noqa: C901
        try:
            (
                mesh_flag,
                name_flag,
                link_type_u2,
                link_number,
                distance_unit_u1,
                entrance_distance,
            ) = cast(
                tuple[bool, bool, int, int, int, int],
                bs.readlist("bool, bool, uint:2, uint:12, uint:1, uint:7"),
            )
            link_type = _safe_enum(LinkType, link_type_u2, "OTHER")
            distance_unit = DistanceUnitParking(distance_unit_u1)

            entrance_x = entrance_y = None
            if mesh_flag:
                entrance_x, entrance_y = cast(
                    tuple[int, int], bs.readlist("uint:16, uint:16")
                )

            name = None
            if name_flag:
                (name_len,) = cast(tuple[int], bs.readlist("uint:8"))
                if name_len:
                    name_bytes = cast(bytes, bs.read(name_len * 8).bytes)
                    name = AribStringDecoder().decode(name_bytes)
                else:
                    name = ""

            return ParkingExt1(
                mesh_flag=mesh_flag,
                name_flag=name_flag,
                link_type=link_type,
                link_number=link_number,
                distance_unit=distance_unit,
                entrance_distance=entrance_distance,
                entrance_x=entrance_x,
                entrance_y=entrance_y,
                name=name,
            )
        except ReadError as err:
            raise BitstreamEndError(f"Stream ended in Ext-1 (bit {bs.pos})") from err

    @staticmethod
    def _parse_ext2(bs: ConstBitStream) -> ParkingExt2:
        try:
            (
                vacancy_rate_raw,
                waiting_time_raw,
                capacity_u3,
                height_lim_u2,
                vehicle_lim_u3,
                discount_u2,
                fee_unit_u3,
                fee_code_raw,
                start_hour_raw,
                start_min_raw,
                end_hour_raw,
                end_min_raw,
            ) = cast(
                tuple[int, int, int, int, int, int, int, int, int, int, int, int],
                bs.readlist(
                    "uint:4, uint:4, uint:3, uint:2, uint:3, uint:2, uint:3, uint:11, "
                    "uint:5, uint:3, uint:5, uint:3"
                ),
            )
            return ParkingExt2(
                vacancy_rate_10pct_raw=vacancy_rate_raw,
                waiting_time_10min_raw=waiting_time_raw,
                capacity_class=_safe_enum(CapacityClass, capacity_u3),
                height_limit=_safe_enum(HeightLimit, height_lim_u2),
                vehicle_limit=_safe_enum(VehicleLimit, vehicle_lim_u3),
                discount_condition=_safe_enum(DiscountCondition, discount_u2),
                fee_unit=_safe_enum(FeeUnit, fee_unit_u3),
                fee_code_raw=fee_code_raw,
                start_hour_raw=start_hour_raw,
                start_min_raw=start_min_raw,
                end_hour_raw=end_hour_raw,
                end_min_raw=end_min_raw,
            )
        except ReadError as err:
            raise BitstreamEndError(f"Stream ended in Ext-2 (bit {bs.pos})") from err


# ---------------------------------------------------------------------------
# Glue helper                                                               #
# ---------------------------------------------------------------------------


def data_unit_from_generic(generic: GenericDataUnit):
    """
    Wrap *GenericDataUnit* into the appropriate typed decoder.
    """
    if generic.data_unit_parameter == 0x41:
        return RegulationAccidentDataUnit.from_generic(generic)
    if generic.data_unit_parameter == 0x42:
        return ParkingDataUnit.from_generic(generic)
    return generic
