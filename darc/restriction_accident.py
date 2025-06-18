from dataclasses import dataclass
from typing import List, Self, Tuple

from bitstring import ConstBitStream

from .helpers import (
    BitReader,
    BitstreamParseError,
    DistanceUnit,
    LinkType,
    SafeIntEnumMixin,
    read_name,
)
from .l5_data import DataUnitBase, GenericDataUnit


# --------------------------------------------------------------------------- #
# Enumerations                                                                #
# --------------------------------------------------------------------------- #
class RestrictionAccidentExtFlag(SafeIntEnumMixin):
    BASIC = 0
    BASIC_EXT1 = 1
    BASIC_EXT1_EXT2 = 2
    MODE_RESERVED = 3


class CauseEvent(SafeIntEnumMixin):
    NONE = 0
    ACCIDENT = 1
    FIRE = 2
    BREAKDOWN = 3
    OBSTACLE = 4
    CONSTRUCTION = 5
    WORK = 6
    EVENT = 7
    WEATHER = 8
    DISASTER = 9
    EARTHQUAKE_WARNING = 10
    UNDEFINED_11 = 11
    UNDEFINED_12 = 12
    UNDEFINED_13 = 13
    OTHER = 14
    UNKNOWN = 15


class RestrictionContent(SafeIntEnumMixin):
    NONE = 0
    TRAFFIC_STOP = 1
    RIGHT_TURN_RESTRICT = 2
    SPEED_LIMIT = 3
    LANE_RESTRICT = 4
    SHOULDER_RESTRICT = 5
    CHAIN_RESTRICT = 6
    ON_RAMP_RESTRICT = 7
    LARGE_VEHICLE_RESTRICT = 8
    TRAFFIC_CONTROL = 9
    OFF_RAMP_RESTRICT = 10
    UNDEFINED_11 = 11
    UNDEFINED_12 = 12
    UNDEFINED_13 = 13
    OTHER = 14
    UNKNOWN = 15


# --------------------------------------------------------------------------- #
# Extension structures                                                        #
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class RestrictionAccidentExt1:
    """Extension-1 (4 bytes): distance offsets and detail codes."""

    reg_content_detail_raw: int
    cause_event_detail_raw: int
    distance_start_unit: DistanceUnit
    distance_end_unit: DistanceUnit
    dist_from_start_raw: int
    dist_from_end_raw: int

    # ---------------- convenience ----------------
    @property
    def dist_from_start_m(self) -> int | None:
        return self.distance_start_unit.decode(self.dist_from_start_raw)

    @property
    def dist_from_end_m(self) -> int | None:
        return self.distance_end_unit.decode(self.dist_from_end_raw)

    # ---------------- parser ---------------------
    @classmethod
    def parse(cls, rdr: BitReader) -> "RestrictionAccidentExt1":
        rc_detail = rdr.u(8)
        ce_detail = rdr.u(8)
        dist_start_unit = DistanceUnit(rdr.u(2))
        dist_start = rdr.u(6)
        dist_end_unit = DistanceUnit(rdr.u(2))
        dist_end = rdr.u(6)
        return cls(
            reg_content_detail_raw=rc_detail,
            cause_event_detail_raw=ce_detail,
            distance_start_unit=dist_start_unit,
            distance_end_unit=dist_end_unit,
            dist_from_start_raw=dist_start,
            dist_from_end_raw=dist_end,
        )


@dataclass(slots=True)
class RestrictionAccidentExt2:
    """Extension-2 (6 bytes): start/end month-day-time (10-minute resolution)."""

    time_flag: bool
    start_month_raw: int
    end_month_raw: int
    start_day_raw: int
    start_hour_raw: int
    start_min10_raw: int
    end_day_raw: int
    end_hour_raw: int
    end_min10_raw: int

    # ---------------- convenience ----------------
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

    # ---------------- parser ---------------------
    @classmethod
    def parse(cls, rdr: BitReader) -> "RestrictionAccidentExt2":
        time_flag = rdr.flag()
        rdr.u(7)  # undefined bits
        start_month = rdr.u(4)
        end_month = rdr.u(4)
        start_day = rdr.u(5)
        start_hour = rdr.u(5)
        start_min10 = rdr.u(6)
        end_day = rdr.u(5)
        end_hour = rdr.u(5)
        end_min10 = rdr.u(6)
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


# --------------------------------------------------------------------------- #
# Basic-info blocks                                                           #
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class RestrictionAccidentBasicInfo:
    mesh_flag: bool
    name_flag: bool
    link_type: LinkType
    link_number: int
    continuous_links: int | None  # via only
    coord_x_hi: int | None  # upper 8 bits
    coord_y_hi: int | None
    name: str | None


# --------------------------------------------------------------------------- #
# Record container                                                            #
# --------------------------------------------------------------------------- #
@dataclass(slots=True)
class RestrictionAccidentRecord:
    ext_flag: RestrictionAccidentExtFlag
    link_count: int
    cause_event: CauseEvent
    restriction_content: RestrictionContent
    distance_unit: DistanceUnit
    restriction_length_raw: int
    basics: List[RestrictionAccidentBasicInfo]
    ext1: RestrictionAccidentExt1 | None = None
    ext2: RestrictionAccidentExt2 | None = None

    # ---------------- convenience ----------------
    @property
    def restriction_length_m(self) -> int | None:
        return (
            None
            if self.restriction_length_raw in (0, 63)
            else self.restriction_length_raw
        )


# --------------------------------------------------------------------------- #
# Main data-unit parser                                                       #
# --------------------------------------------------------------------------- #
@dataclass
class RestrictionAccidentDataUnit(DataUnitBase):
    records: List[RestrictionAccidentRecord]

    # ---------------------------- factory ---------------------------------- #
    @classmethod
    def from_generic(cls, generic: GenericDataUnit) -> Self:
        rdr = BitReader(ConstBitStream(generic.data_unit_data))
        recs: List[RestrictionAccidentRecord] = []
        while rdr.pos < rdr.len:
            start_pos = rdr.pos
            try:
                recs.append(cls._parse_record(rdr))
            except BitstreamParseError:
                # truncated payload - abort parsing
                break
            if rdr.pos == start_pos:
                # safeguard against infinite loop when parser misbehaves
                break
        return cls(generic.data_unit_parameter, generic.data_unit_link_flag, recs)

    # -------------------------- record parser ------------------------------ #
    @staticmethod
    def _parse_record(rdr: BitReader) -> RestrictionAccidentRecord:
        # header (first 24 bits)
        ext_flag = RestrictionAccidentExtFlag(rdr.u(2))
        link_total = rdr.u(6)
        cause_event = CauseEvent(rdr.u(4))
        restr_content = RestrictionContent(rdr.u(4))
        distance_unit = DistanceUnit(rdr.u(2))
        restr_len_raw = rdr.u(6)

        basics: List[RestrictionAccidentBasicInfo] = []
        remaining = link_total

        # 1) start block
        basics.append(RestrictionAccidentDataUnit._parse_start(rdr))
        remaining -= 1

        # 2) end block if any
        if remaining >= 1:
            basics.append(RestrictionAccidentDataUnit._parse_end(rdr))
            remaining -= 1

        # 3) via blocks
        while remaining > 0:
            via, covered = RestrictionAccidentDataUnit._parse_via(rdr)
            basics.append(via)
            remaining -= covered
            if remaining < 0:
                raise BitstreamParseError("Via block count exceeds header link_total")

        # 4) extensions (once)
        ext1 = ext2 = None
        if ext_flag in {
            RestrictionAccidentExtFlag.BASIC_EXT1,
            RestrictionAccidentExtFlag.BASIC_EXT1_EXT2,
        }:
            ext1 = RestrictionAccidentExt1.parse(rdr)
        if ext_flag == RestrictionAccidentExtFlag.BASIC_EXT1_EXT2:
            ext2 = RestrictionAccidentExt2.parse(rdr)

        return RestrictionAccidentRecord(
            ext_flag=ext_flag,
            link_count=link_total,
            cause_event=cause_event,
            restriction_content=restr_content,
            distance_unit=distance_unit,
            restriction_length_raw=restr_len_raw,
            basics=basics,
            ext1=ext1,
            ext2=ext2,
        )

    # ----------------------- block-level parsers ---------------------------- #
    @staticmethod
    def _parse_start(rdr: BitReader) -> RestrictionAccidentBasicInfo:
        mesh = rdr.flag()
        name_f = rdr.flag()
        link_type = LinkType(rdr.u(2))
        link_hi = rdr.u(4)
        link_lo = rdr.u(8)
        name = read_name(rdr) if name_f else None
        return RestrictionAccidentBasicInfo(
            mesh_flag=mesh,
            name_flag=name_f,
            link_type=link_type,
            link_number=(link_hi << 8) | link_lo,
            continuous_links=None,
            coord_x_hi=None,
            coord_y_hi=None,
            name=name,
        )

    @staticmethod
    def _parse_end(rdr: BitReader) -> RestrictionAccidentBasicInfo:
        """Parse *End block* (always final link, present when link_count ≥ 2)."""
        mesh = rdr.flag()
        name_f = rdr.flag()
        link_type = LinkType(rdr.u(2))
        link_hi = rdr.u(4)
        link_lo = rdr.u(8)
        coord_x = coord_y = None
        if mesh:
            coord_x = rdr.u(8)
            coord_y = rdr.u(8)
        name = read_name(rdr) if name_f else None
        return RestrictionAccidentBasicInfo(
            mesh_flag=mesh,
            name_flag=name_f,
            link_type=link_type,
            link_number=(link_hi << 8) | link_lo,
            continuous_links=None,
            coord_x_hi=coord_x,
            coord_y_hi=coord_y,
            name=name,
        )

    @staticmethod
    def _parse_via(rdr: BitReader) -> Tuple[RestrictionAccidentBasicInfo, int]:
        mesh = rdr.flag()
        name_f = rdr.flag()
        link_type = LinkType(rdr.u(2))
        link_hi = rdr.u(4)
        link_lo = rdr.u(8)
        cont_links = rdr.u(8)  # additional links after the first
        coord_x = coord_y = None
        if mesh:
            coord_x = rdr.u(8)
            coord_y = rdr.u(8)
        name = read_name(rdr) if name_f else None
        info = RestrictionAccidentBasicInfo(
            mesh_flag=mesh,
            name_flag=name_f,
            link_type=link_type,
            link_number=(link_hi << 8) | link_lo,
            continuous_links=cont_links,
            coord_x_hi=coord_x,
            coord_y_hi=coord_y,
            name=name,
        )
        return info, cont_links + 1  # this block itself + subsequent links
