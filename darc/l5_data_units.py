import enum
from dataclasses import dataclass
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


class RestrictionAccidentExtFlag(enum.IntEnum):
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


class RestrictionContent(enum.IntEnum):
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
class RestrictionAccidentExt1:
    """Extension-1 (4 bytes) — distance-offsets & detail codes."""

    reg_content_detail_raw: int  # PBm
    cause_event_detail_raw: int  # PBm+1
    distance_start_unit: DistanceUnit  # PBm+2 b7-6
    distance_end_unit: DistanceUnit  # PBm+2 b7-6
    dist_from_start_raw: int  # PBm+2 b5-0 (0-63)
    dist_from_end_raw: int  # PBm+3 b5-0 (0-63)

    # ---- convenience -------------------------------------------------
    @property
    def dist_from_start_m(self) -> int | None:
        return _decode_distance(self.distance_start_unit, self.dist_from_start_raw)

    @property
    def dist_from_end_m(self) -> int | None:
        return _decode_distance(self.distance_end_unit, self.dist_from_end_raw)

    # ---- parser ------------------------------------------------------
    @classmethod
    def parse(cls, bs: ConstBitStream) -> Self:
        rc_detail, ce_detail = cast(tuple[int, int], bs.readlist("uint:8, uint:8"))
        dist_start_unit_u2, dist_start, dist_end_unit_u2, dist_end = cast(
            tuple[int, int, int, int],
            bs.readlist("uint:2, uint:6, uint:2, uint:6"),
        )

        return cls(
            reg_content_detail_raw=rc_detail,
            cause_event_detail_raw=ce_detail,
            distance_start_unit=DistanceUnit(dist_start_unit_u2),
            distance_end_unit=DistanceUnit(dist_end_unit_u2),
            dist_from_start_raw=dist_start,
            dist_from_end_raw=dist_end,
        )


@dataclass(slots=True)
class RestrictionAccidentExt2:
    """Extension-2 (6 bytes) — start / end month-day-time (10-minute step)."""

    time_flag: bool
    start_month_raw: int
    end_month_raw: int
    start_day_raw: int
    start_hour_raw: int
    start_min10_raw: int
    end_day_raw: int
    end_hour_raw: int
    end_min10_raw: int

    # ---- convenience -------------------------------------------------
    @property
    def start_time_tuple(self) -> tuple[int, int, int] | None:
        if self.start_month_raw == 0:
            return None
        return (self.start_day_raw, self.start_hour_raw, self.start_min10_raw * 10)

    @property
    def end_time_tuple(self) -> tuple[int, int, int] | None:
        if self.end_month_raw == 0:
            return None
        return (self.end_day_raw, self.end_hour_raw, self.end_min10_raw * 10)

    # ---- parser ------------------------------------------------------
    @classmethod
    def parse(cls, bs: ConstBitStream) -> Self:
        time_flag = bs.read("bool")
        bs.read("uint:7")  # Undefined
        start_month = bs.read("uint:4")
        end_month = bs.read("uint:4")
        start_day = bs.read("uint:5")
        start_hour = bs.read("uint:5")
        start_min10 = bs.read("uint:6")
        end_day = bs.read("uint:5")
        end_hour = bs.read("uint:5")
        end_min10 = bs.read("uint:6")
        return cls(
            time_flag=time_flag,
            start_month_raw=start_month,
            end_month_raw=end_month,
            start_day_raw=start_day,
            start_hour_raw=start_hour,
            start_min10_raw=start_min10,
            end_day_raw=end_day,
            end_hour_raw=end_hour,
            end_min10_raw=end_min10,
        )


# ---------------------------------------------------------------------
# small shared helper
# ---------------------------------------------------------------------
def _decode_distance(unit: DistanceUnit, val: int) -> int | None:
    if unit == DistanceUnit.TEN_M:
        return val * 10
    if unit == DistanceUnit.HUNDRED_M:
        return val * 100
    if unit == DistanceUnit.ONE_KM:
        return val * 1000
    return None


@dataclass(slots=True)
class RestrictionAccidentBasicInfo:
    mesh_flag: bool
    name_flag: bool
    link_type: LinkType
    link_number: int
    continuous_links: int | None  # Via only
    coord_x_hi: int | None  # upper 8‑bit
    coord_y_hi: int | None
    name: str | None


@dataclass(slots=True)
class RestrictionAccidentRecord:
    ext_flag: RestrictionAccidentExtFlag
    link_count: int
    cause_event: CauseEvent
    Restriction_content: RestrictionContent
    distance_unit: DistanceUnit
    Restriction_length_raw: int
    basics: list[RestrictionAccidentBasicInfo]
    ext1: RestrictionAccidentExt1 | None = None
    ext2: RestrictionAccidentExt2 | None = None

    @property
    def Restriction_length(self) -> int | None:
        return (
            None
            if self.Restriction_length_raw in (0, 63)
            else self.Restriction_length_raw
        )


# ──────────────────────────────── Main Unit ─────────────────────────────────


@dataclass
class RestrictionAccidentDataUnit(DataUnitBase):
    """Fully‑parsed *Restriction / Accident* data‑unit (parameter 0x41)."""

    records: list[RestrictionAccidentRecord]

    # -----------------------------------------------------------
    def __init__(
        self, parameter: int, link_flag: int, records: list[RestrictionAccidentRecord]
    ):
        super().__init__(parameter, link_flag)
        self.records = records

    # -----------------------------------------------------------
    @classmethod
    def from_generic(cls, generic: GenericDataUnit) -> Self:
        bs = ConstBitStream(generic.data_unit_data)
        recs: list[RestrictionAccidentRecord] = []
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
    ) -> RestrictionAccidentRecord:  # noqa: C901
        # ─ Header ------------------------------------------------------
        ext_flag = RestrictionAccidentExtFlag(bs.read("uint:2"))
        link_total = bs.read("uint:6")
        cause_event = _safe_enum(CauseEvent, bs.read("uint:4"))
        Restriction_content = _safe_enum(RestrictionContent, bs.read("uint:4"))
        distance_unit = _safe_enum(DistanceUnit, bs.read("uint:2"))
        Restriction_length_raw = bs.read("uint:6")

        basics: list[RestrictionAccidentBasicInfo] = []
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
            RestrictionAccidentExtFlag.BASIC_EXT1,
            RestrictionAccidentExtFlag.BASIC_EXT1_EXT2,
        ):
            ext1 = RestrictionAccidentExt1.parse(bs)
        if ext_flag == RestrictionAccidentExtFlag.BASIC_EXT1_EXT2:
            ext2 = RestrictionAccidentExt2.parse(bs)

        return RestrictionAccidentRecord(
            ext_flag=ext_flag,
            link_count=link_total,
            cause_event=cause_event,
            Restriction_content=Restriction_content,
            distance_unit=distance_unit,
            Restriction_length_raw=Restriction_length_raw,
            basics=basics,
            ext1=ext1,
            ext2=ext2,
        )

    # -----------------------------------------------------------
    # block‑level parsers
    # -----------------------------------------------------------
    @classmethod
    def _parse_start(cls, bs: ConstBitStream) -> RestrictionAccidentBasicInfo:
        mesh = bs.read("bool")
        name_f = bs.read("bool")
        link_type = _safe_enum(LinkType, bs.read("uint:2"))
        link_hi = bs.read("uint:4")
        link_lo = bs.read("uint:8")
        name = cls._read_name(bs) if name_f else None
        return RestrictionAccidentBasicInfo(
            mesh, name_f, link_type, (link_hi << 8) | link_lo, None, None, None, name
        )

    @classmethod
    def _parse_end(cls, bs: ConstBitStream) -> RestrictionAccidentBasicInfo:
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
        return RestrictionAccidentBasicInfo(
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
    def _parse_via(cls, bs: ConstBitStream) -> tuple[RestrictionAccidentBasicInfo, int]:
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
        info = RestrictionAccidentBasicInfo(
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
    entrance_distance_raw: int
    entrance_x: int | None
    entrance_y: int | None
    name: str | None

    @property
    def entrance_distance(self) -> int | None:
        return (
            None if self.entrance_distance_raw == 127 else self.entrance_distance_raw
        )


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
                entrance_distance_raw=entrance_distance,
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
        return RestrictionAccidentDataUnit.from_generic(generic)
    if generic.data_unit_parameter == 0x42:
        return ParkingDataUnit.from_generic(generic)
    return generic
