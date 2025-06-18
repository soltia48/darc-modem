import enum
from dataclasses import dataclass
from typing import Self, TypeVar, cast

from bitstring import ConstBitStream, ReadError

from .arib_string import AribStringDecoder
from .l5_data import DataUnitBase, GenericDataUnit

# ──────────────────────────────── Exceptions ────────────────────────────────


class BitstreamEndError(RuntimeError):
    """Raised when the bitstream ends unexpectedly while parsing a field."""


# ─────────────────────────────── Helpers ────────────────────────────────
E = TypeVar("E", bound=enum.IntEnum)


def _safe_enum(enum_cls: type[E], value: int, fallback_attr: str = "UNKNOWN") -> E:
    """Return enum_cls(value) or enum_cls.UNKNOWN when *value* is out-of-range."""
    try:
        return enum_cls(value)  # type: ignore[arg-type]
    except ValueError:
        return getattr(enum_cls, fallback_attr)  # type: ignore[return-value]


def _read_name(bs: ConstBitStream) -> str:
    length = bs.read("uint:8")
    if length == 0:
        return ""
    return AribStringDecoder().decode(bs.read(length * 8).bytes)


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


class ProvideForm(enum.IntEnum):
    """`提供形態` (PB H₁ b₈)"""

    TRAVEL_TIME = 0  # 形態0 - travel-time capable format
    CONGESTION_ONLY = 1  # 形態1 - congestion-only compact format


class InfoFlag(enum.IntEnum):
    """`情報数フラグ` (PB H₁ b₆)"""

    PER_LINK = 0  # one data-info per link
    SINGLE = 1  # first data-info represents all links that follow


class ModeFlag(enum.IntEnum):
    """`モード識別` (PB H₁ b₅)"""

    CURRENT = 0  # current ARIB STD-B3 format
    RESERVED = 1  # future formats → skip remainder of DU


class TravelTimeExtFlag(enum.IntEnum):
    """`拡張フラグ／リンク旅行時間` (PB L₁ b₆‥b₁) - provide-form 0 only.

    Values **0–59** are interpreted as travel-time in *10-second* units.
    The symbolic constants below cover 60–63.
    """

    BASIC_EXT1 = 60  # + Ext-1
    BASIC_EXT1_EXT2 = 61  # + Ext-1 + Ext-2
    UNDEFINED = 62
    DISAPPEAR_OR_AGGREGATE = 63  # meaning depends on congestion degree


class PerLinkExtFlag(enum.IntEnum):
    """`拡張フラグ` (提供形態1) - 2-bit flag per link."""

    NONE = 0  # 拡張無し
    BASIC_EXT1 = 1  # 基本 + Ext-1
    DISAPPEAR = 2  # 消失リンク
    AGGREGATE_OR_INVALID = 3  # 情報集約／無効


# ─────────────────────────────── Dataclasses ────────────────────────────────


@dataclass(slots=True)
class TravelTimeExt1:
    """Distance/length related extension (Ext-1)."""

    distance_unit: DistanceUnit  # 2 bits (PB L₂ b₈, PB L₃ b₈)
    head_pos_raw: int  # 7 bits (PB L₂ b₇‥b₁)
    jam_length_raw: int  # 7 bits (PB L₃ b₇‥b₁)

    # ---------------- convenience ----------------
    @property
    def head_pos_m(self) -> int | None:
        """Distance *from the link end* to the congestion head, in metres."""

        return _decode_distance(self.distance_unit, self.head_pos_raw)

    @property
    def jam_length_m(self) -> int | None:
        return _decode_distance(self.distance_unit, self.jam_length_raw)


@dataclass(slots=True)
class TravelTimeExt2:
    """Extended travel-time (Ext-2)."""

    time_unit: TimeUnit  # 1 bit (PB L₄ b₈)
    link_travel_time_raw: int  # 7 bits (PB L₄ b₇‥b₁)

    # ---------------- convenience ----------------
    @property
    def link_travel_time_sec(self) -> int | None:
        if self.link_travel_time_raw in (0, 126, 127):
            return None  # 0 = unknown, 126/127 = reserved
        mult = 10 if self.time_unit == TimeUnit.SEC_10 else 60
        return self.link_travel_time_raw * mult


@dataclass(slots=True)
class TravelTimeLinkRecord:
    """Per-link congestion / travel-time record."""

    congestion: CongestionDegree
    travel_time_sec: int | None  # form-0 quick value, or Ext-2 decoded
    ext_flag_raw: int | None  # raw 6-bit (form-0) or 2-bit (form-1) flag
    ext1: TravelTimeExt1 | None = None
    ext2: TravelTimeExt2 | None = None

    # ---------------- helpers ----------------
    @property
    def has_ext1(self) -> bool:  # noqa: D401 - property is fine
        return self.ext1 is not None

    @property
    def has_ext2(self) -> bool:
        return self.ext2 is not None


# ──────────────────────────────── Main Unit ─────────────────────────────────


@dataclass
class TravelTimeDataUnit(DataUnitBase):
    """Fully-parsed *Congestion / Travel-Time* data-unit (parameter 0x40)."""

    provide_form: ProvideForm
    travel_time_kind: TravelTimeKind
    info_flag: InfoFlag
    mode_flag: ModeFlag
    link_type: LinkType
    link_count: int
    lead_link_number: int
    records: list[TravelTimeLinkRecord]

    # ---------------------------------------------------------------------
    def __init__(
        self,
        parameter: int,
        link_flag: int,
        provide_form: ProvideForm,
        travel_time_kind: TravelTimeKind,
        info_flag: InfoFlag,
        mode_flag: ModeFlag,
        link_type: LinkType,
        link_count: int,
        lead_link_number: int,
        records: list[TravelTimeLinkRecord],
    ) -> None:
        super().__init__(parameter, link_flag)
        self.provide_form = provide_form
        self.travel_time_kind = travel_time_kind
        self.info_flag = info_flag
        self.mode_flag = mode_flag
        self.link_type = link_type
        self.link_count = link_count
        self.lead_link_number = lead_link_number
        self.records = records

    # ------------------------------------------------------------------
    @classmethod
    def from_generic(
        cls, generic: GenericDataUnit
    ) -> "Self":  # noqa: C901 - complex parser
        bs = ConstBitStream(generic.data_unit_data)

        # ───────────────────── Header (PB H₁–H₄) ──────────────────────
        (provide_form_b, travel_time_kind_b, info_flag_b, mode_flag_b, link_cnt_hi) = (
            cast(
                tuple[bool, bool, bool, bool, int],
                bs.readlist("bool, bool, bool, bool, uint:4"),
            )
        )
        link_cnt_lo = bs.read("uint:8")  # PB H₂
        link_count = (link_cnt_hi << 8) | link_cnt_lo

        # PB H₃
        reserved_u2, link_type_u2, lead_link_hi = cast(
            tuple[int, int, int],
            bs.readlist("uint:2, uint:2, uint:4"),
        )
        lead_link_lo = bs.read("uint:8")  # PB H₄
        lead_link_number = (lead_link_hi << 8) | lead_link_lo

        provide_form = ProvideForm(provide_form_b)
        travel_kind = TravelTimeKind(travel_time_kind_b)
        info_flag = InfoFlag(info_flag_b)
        mode_flag = ModeFlag(mode_flag_b)
        link_type = _safe_enum(LinkType, link_type_u2)

        # If mode flag = 1, spec mandates we skip the remainder (future format).
        if mode_flag == ModeFlag.RESERVED:
            return cls(
                generic.data_unit_parameter,
                generic.data_unit_link_flag,
                provide_form,
                travel_kind,
                info_flag,
                mode_flag,
                link_type,
                link_count,
                lead_link_number,
                [],
            )

        # ───────────────────── Data-info blocks ────────────────────────
        records: list[TravelTimeLinkRecord] = []

        num_records_expected = 1 if info_flag == InfoFlag.SINGLE else link_count
        record_index = 0
        while record_index < num_records_expected and bs.pos < bs.len:
            try:
                if provide_form == ProvideForm.TRAVEL_TIME:
                    rec = cls._parse_link_form0(bs)
                    records.append(rec)
                    record_index += 1
                else:  # congestion-only compact form
                    # Two half-records per byte
                    byte_val = bs.read("uint:8")
                    high_nibble = byte_val >> 4
                    low_nibble = byte_val & 0xF

                    for nib in (high_nibble, low_nibble):
                        if record_index >= num_records_expected:
                            break
                        rec = cls._parse_nibble_form1(bs, nib)
                        records.append(rec)
                        record_index += 1
            except ReadError:
                break  # truncated stream

        return cls(
            generic.data_unit_parameter,
            generic.data_unit_link_flag,
            provide_form,
            travel_kind,
            info_flag,
            mode_flag,
            link_type,
            link_count,
            lead_link_number,
            records,
        )

    # ------------------------------------------------------------------
    # Per-link parsers                                                   #
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_link_form0(bs: ConstBitStream) -> TravelTimeLinkRecord:
        """Parse one *travel-time capable* link-record (提供形態0)."""
        val_u8 = bs.read("uint:8")
        congestion_u2 = (val_u8 >> 6) & 0x3
        flag_u6 = val_u8 & 0x3F

        congestion = _safe_enum(CongestionDegree, congestion_u2)

        travel_time_sec: int | None = None
        ext1 = ext2 = None

        if flag_u6 <= 59:
            travel_time_sec = None if flag_u6 == 0 else flag_u6 * 10
        elif flag_u6 == TravelTimeExtFlag.BASIC_EXT1:
            ext1 = TravelTimeDataUnit._parse_ext1(bs)
        elif flag_u6 == TravelTimeExtFlag.BASIC_EXT1_EXT2:
            ext1 = TravelTimeDataUnit._parse_ext1(bs)
            ext2 = TravelTimeDataUnit._parse_ext2(bs)
        elif flag_u6 == TravelTimeExtFlag.DISAPPEAR_OR_AGGREGATE:
            # travel_time remains None; semantics left to caller
            pass
        # flag 62 → ignored

        return TravelTimeLinkRecord(
            congestion=congestion,
            travel_time_sec=travel_time_sec,
            ext_flag_raw=flag_u6,
            ext1=ext1,
            ext2=ext2,
        )

    @staticmethod
    def _parse_nibble_form1(bs: ConstBitStream, nibble: int) -> TravelTimeLinkRecord:
        """Parse one *congestion-only* half-record (提供形態1)."""

        ext_flag_u2 = (nibble >> 2) & 0x3  # b4,b3 (or b8,b7) already aligned
        cong_u2 = nibble & 0x3  # b2,b1 (or b6,b5)

        congestion = _safe_enum(CongestionDegree, cong_u2)
        ext_flag = _safe_enum(PerLinkExtFlag, ext_flag_u2)

        ext1 = None
        if ext_flag == PerLinkExtFlag.BASIC_EXT1:
            ext1 = TravelTimeDataUnit._parse_ext1(bs)

        return TravelTimeLinkRecord(
            congestion=congestion,
            travel_time_sec=None,
            ext_flag_raw=ext_flag_u2,
            ext1=ext1,
            ext2=None,
        )

    # ------------------------------------------------------------------
    # Extension-level parsers                                            #
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_ext1(bs: ConstBitStream) -> TravelTimeExt1:
        try:
            # Read PB L₂ and PB L₃ *raw* so we can split bits manually.
            byte_l2 = bs.read("uint:8")
            byte_l3 = bs.read("uint:8")

            distance_unit_bits = ((byte_l2 >> 7) & 0x1) << 1 | ((byte_l3 >> 7) & 0x1)
            distance_unit = _safe_enum(DistanceUnit, distance_unit_bits)

            head_pos_raw = byte_l2 & 0x7F  # lower 7 bits
            jam_len_raw = byte_l3 & 0x7F  # lower 7 bits

            return TravelTimeExt1(
                distance_unit=distance_unit,
                head_pos_raw=head_pos_raw,
                jam_length_raw=jam_len_raw,
            )
        except ReadError as err:
            raise RuntimeError("Stream ended mid Ext-1") from err

    @staticmethod
    def _parse_ext2(bs: ConstBitStream) -> TravelTimeExt2:
        try:
            byte_l4 = bs.read("uint:8")
            time_unit_bit = (byte_l4 >> 7) & 0x1
            link_time_raw = byte_l4 & 0x7F
            return TravelTimeExt2(
                time_unit=_safe_enum(TimeUnit, time_unit_bit),
                link_travel_time_raw=link_time_raw,
            )
        except ReadError as err:
            raise RuntimeError("Stream ended mid Ext-2") from err


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
    coord_x_hi: int | None  # upper 8-bit
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
    """Fully-parsed *Restriction / Accident* data-unit (parameter 0x41)."""

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
    # record-level parser
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
    # block-level parsers
    # -----------------------------------------------------------
    @classmethod
    def _parse_start(cls, bs: ConstBitStream) -> RestrictionAccidentBasicInfo:
        mesh = bs.read("bool")
        name_f = bs.read("bool")
        link_type = _safe_enum(LinkType, bs.read("uint:2"))
        link_hi = bs.read("uint:4")
        link_lo = bs.read("uint:8")
        name = _read_name(bs) if name_f else None
        return RestrictionAccidentBasicInfo(
            mesh, name_f, link_type, (link_hi << 8) | link_lo, None, None, None, name
        )

    @classmethod
    def _parse_end(cls, bs: ConstBitStream) -> RestrictionAccidentBasicInfo:
        """Parse *End block* (always final link, present when link_count ≥ 2).

        According to the spec, the X/Y upper-byte rows are present regardless of
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
            coord_y = bs.read("uint:8")  # Y upper-byte
        name = _read_name(bs) if name_f else None
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
        name = _read_name(bs) if name_f else None
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
        return None if self.entrance_distance_raw == 127 else self.entrance_distance_raw


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
            pos0 = bs.pos  # loop-safety checkpoint
            try:
                records.append(cls._parse_record(bs))
            except (ReadError, BitstreamEndError):
                break  # truncated payload
            assert bs.pos > pos0, "_parse_record() must consume bits"
        return cls(generic.data_unit_parameter, generic.data_unit_link_flag, records)

    # ------------------------------------------------------------------ #
    # Low-level parsers                                                  #
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

            # --- PB L2-L3 (32 bits) ---
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


# ─────────────────────────────── Enumerations ────────────────────────────
class SectionTT_ExtFlag(enum.IntEnum):
    BASIC = 0
    BASIC_EXT1 = 1
    MODE_RESERVED_2 = 2  # future use
    MODE_RESERVED_3 = 3  # future use


class SectionTT_Priority(enum.IntEnum):
    UNDEFINED_0 = 0
    NORMAL = 1
    UNDEFINED_2 = 2
    IMPORTANT = 3


# ─────────────────────────────── Dataclasses ─────────────────────────────
@dataclass(slots=True)
class SectionPoint:
    mesh_flag: bool
    name_flag: bool
    link_type: LinkType
    link_number: int
    coord_x_hi: int | None  # absent for *start* block
    coord_y_hi: int | None
    name: str | None


@dataclass(slots=True)
class RouteBlock:
    hour_raw: int  # 5- bit travel- time hour (0- 31)
    minute_raw: int  # 6- bit travel- time minute (0- 63)
    priority: SectionTT_Priority | None  # only set for the primary route
    link_count: int
    points: list[SectionPoint]


@dataclass(slots=True)
class AltRouteGroup:
    alt_count: int  # 他経由路線数 (0- 31)
    routes: list[RouteBlock]


# ════════════════════════════════════════════════════════════════════════
# Segment ––– 0x43 ペイロードが自己再帰的に繰り返す単位
# ════════════════════════════════════════════════════════════════════════
@dataclass(slots=True)
class SectionTravelTimeSegment:
    ext_flag: SectionTT_ExtFlag
    primary_route: RouteBlock
    alt_route_groups: list[AltRouteGroup]


# ════════════════════════════════════════════════════════════════════════
# Main Data- Unit wrapper (parameter 0x43)
# ════════════════════════════════════════════════════════════════════════
@dataclass
class SectionTravelTimeDataUnit(DataUnitBase):
    """Decoder for ARIB STD- B3 §3.1.4 *Section Travel- Time* (param 0x43).

    The payload may contain **multiple segments**; each segment itself consists of
    a primary route (基本構成) and optional alternate- route groups (拡張構成1).
    """

    segments: list[SectionTravelTimeSegment]

    # ──────────────────────────────────────────────────────────────
    @classmethod  # noqa: C901 – complex parser
    def from_generic(cls, generic: GenericDataUnit) -> Self:
        bs = ConstBitStream(generic.data_unit_data)
        segments: list[SectionTravelTimeSegment] = []

        while bs.pos < bs.len:
            start_pos = bs.pos
            try:
                segments.append(cls._parse_segment(bs))
            except (ReadError, ValueError):
                # If parsing fails we stop to avoid infinite loop
                bs.pos = bs.len
            # safety: ensure progress
            if bs.pos == start_pos:
                break

        return cls(generic.data_unit_parameter, generic.data_unit_link_flag, segments)

    # ──────────────────────────────────────────────────────────────
    # Segment- level parser
    # ──────────────────────────────────────────────────────────────
    @classmethod  # noqa: C901
    def _parse_segment(cls, bs: ConstBitStream) -> SectionTravelTimeSegment:
        # ── PB L1 ──
        ext_flag_u2, _undef_bit, hour_raw = cast(
            tuple[int, bool, int], bs.readlist("uint:2, bool, uint:5")
        )
        ext_flag = SectionTT_ExtFlag(ext_flag_u2)

        # ── PB L2 ──
        priority_u2, minute_raw = cast(tuple[int, int], bs.readlist("uint:2, uint:6"))
        priority = SectionTT_Priority(priority_u2)

        # ── PB L3 ──
        link_count = bs.read("uint:8")

        # Handle future reserved modes: consume remaining bits of this segment and return stub
        if ext_flag in {
            SectionTT_ExtFlag.MODE_RESERVED_2,
            SectionTT_ExtFlag.MODE_RESERVED_3,
        }:
            # Reservation mode ⇒ remaining bits until next byte with MSB set to 1? Spec isn’t
            # crystal clear; simplest: fast- forward to end of data- unit.
            bs.pos = bs.len
            dummy_route = RouteBlock(hour_raw, minute_raw, priority, link_count, [])
            return SectionTravelTimeSegment(ext_flag, dummy_route, [])

        # ── 基本構成（primary route） ──
        start_pt = cls._parse_point(bs)
        end_pt = cls._parse_point(bs)
        vias = [cls._parse_point(bs) for _ in range(max(link_count - 2, 0))]

        primary = RouteBlock(
            hour_raw=hour_raw,
            minute_raw=minute_raw,
            priority=priority,
            link_count=link_count,
            points=[start_pt, *vias, end_pt],
        )

        # ── 拡張構成1 (optional alt- route groups) ──
        alt_groups: list[AltRouteGroup] = []
        if ext_flag == SectionTT_ExtFlag.BASIC_EXT1 and bs.pos < bs.len:
            # Ext- 1 may repeat until new segment header or stream end.
            while bs.pos < bs.len:
                # Peek next two bits – if they look like a new segment header (b8,b7 of PB L1) break.
                # We can safely peek because ConstBitStream supports pos restore.
                peek = bs.read("uint:2")
                bs.pos -= 2
                if peek in {
                    0,
                    1,
                    2,
                    3,
                }:  # could be next segment’s ext_flag value at byte boundary
                    # ensure we are byte- aligned; segment headers start at byte boundary.
                    if bs.pos % 8 == 0:
                        break
                # Otherwise parse one alt- route group
                alt_groups.append(cls._parse_alt_group(bs))

        return SectionTravelTimeSegment(ext_flag, primary, alt_groups)

    # ──────────────────────────────────────────────────────────────
    # Alt- route group parser
    # ──────────────────────────────────────────────────────────────
    @classmethod  # noqa: C901
    def _parse_alt_group(cls, bs: ConstBitStream) -> AltRouteGroup:
        try:
            alt_cnt, _reserved3 = cast(tuple[int, int], bs.readlist("uint:5, uint:3"))
        except ReadError as err:
            raise ReadError("Incomplete AltRouteGroup header") from err

        routes: list[RouteBlock] = []
        for _ in range(alt_cnt):
            try:
                hour = bs.read("uint:5")
                minute = bs.read("uint:6")
                # align to next byte boundary
                mis = bs.pos % 8
                if mis:
                    bs.read(f"pad:{8 - mis}")
                lcnt = bs.read("uint:8")
                st = cls._parse_point(bs)
                en = cls._parse_point(bs)
                vias = [cls._parse_point(bs) for _ in range(max(lcnt - 2, 0))]
            except ReadError as err:
                raise ReadError("Truncated AltRoute route block") from err
            routes.append(RouteBlock(hour, minute, None, lcnt, [st, *vias, en]))

        return AltRouteGroup(alt_cnt, routes)

    # ──────────────────────────────────────────────────────────────
    # Point parser
    # ──────────────────────────────────────────────────────────────
    @classmethod
    def _parse_point(cls, bs: ConstBitStream) -> SectionPoint:
        mesh, name_f, link_type_u2, link_hi = cast(
            tuple[bool, bool, int, int], bs.readlist("bool, bool, uint:2, uint:4")
        )
        link_lo = bs.read("uint:8")
        coord_x = coord_y = None
        if mesh:
            coord_x, coord_y = cast(tuple[int, int], bs.readlist("uint:8, uint:8"))
        name = _read_name(bs) if name_f else None
        return SectionPoint(
            mesh_flag=mesh,
            name_flag=name_f,
            link_type=_safe_enum(LinkType, link_type_u2, "OTHER"),
            link_number=(link_hi << 8) | link_lo,
            coord_x_hi=coord_x,
            coord_y_hi=coord_y,
            name=name,
        )


# ---------------------------------------------------------------------------
# Glue helper                                                               #
# ---------------------------------------------------------------------------


def data_unit_from_generic(generic: GenericDataUnit):
    """
    Wrap *GenericDataUnit* into the appropriate typed decoder.
    """
    if generic.data_unit_parameter == 0x40:
        return TravelTimeDataUnit.from_generic(generic)
    elif generic.data_unit_parameter == 0x41:
        return RestrictionAccidentDataUnit.from_generic(generic)
    elif generic.data_unit_parameter == 0x42:
        return ParkingDataUnit.from_generic(generic)
    elif generic.data_unit_parameter == 0x43:
        return SectionTravelTimeDataUnit.from_generic(generic)
    return generic
