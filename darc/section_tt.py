from dataclasses import dataclass
from typing import Self

from bitstring import ConstBitStream, ReadError

from .helpers import (
    BitReader,
    BitstreamParseError,
    LinkType,
    SafeIntEnumMixin,
    read_name,
)
from .l5_data import DataUnitBase, GenericDataUnit

# --------------------------------------------------------------------------- #
# Enum definitions                                                            #
# --------------------------------------------------------------------------- #


class SectionTTExtFlag(SafeIntEnumMixin):
    """Segment-level extension flag (PB L1 b8-b7)."""

    BASIC = 0
    BASIC_EXT1 = 1
    MODE_RESERVED_2 = 2  # future use
    MODE_RESERVED_3 = 3  # future use


class SectionTTPriority(SafeIntEnumMixin):
    """Route priority (PB L2 b8-b7)."""

    UNDEFINED_0 = 0
    NORMAL = 1
    UNDEFINED_2 = 2
    IMPORTANT = 3


# --------------------------------------------------------------------------- #
# Dataclasses                                                                 #
# --------------------------------------------------------------------------- #


@dataclass(slots=True)
class SectionPoint:
    """A single link reference with optional coordinates and name."""

    mesh_flag: bool
    name_flag: bool
    link_type: LinkType
    link_number: int
    coord_x_hi: int | None  # none when *mesh_flag* is False or for start block
    coord_y_hi: int | None
    name: str | None


@dataclass(slots=True)
class RouteBlock:
    """Sequence of links representing a route (primary or alternate)."""

    hour_raw: int  # 5-bit travel-time hour (0-31)
    minute_raw: int  # 6-bit travel-time minute (0-63)
    priority: SectionTTPriority | None  # only set for the primary route
    link_count: int
    points: list[SectionPoint]


@dataclass(slots=True)
class AltRouteGroup:
    """One *拡張構成1* group containing between 0 and 31 alternate routes."""

    alt_count: int
    routes: list[RouteBlock]


@dataclass(slots=True)
class SectionTravelTimeSegment:
    """A self-contained segment that can repeat within one data-unit."""

    ext_flag: SectionTTExtFlag
    primary_route: RouteBlock
    alt_route_groups: list[AltRouteGroup]


# --------------------------------------------------------------------------- #
# Main data-unit wrapper                                                      #
# --------------------------------------------------------------------------- #


@dataclass
class SectionTravelTimeDataUnit(DataUnitBase):
    segments: list[SectionTravelTimeSegment]

    # ------------------------------------------------------------------ #
    # Factory                                                            #
    # ------------------------------------------------------------------ #
    @classmethod
    def from_generic(cls, generic: GenericDataUnit) -> Self:
        reader = BitReader(ConstBitStream(generic.data_unit_data))
        segments: list[SectionTravelTimeSegment] = []

        while reader.pos < reader.len:
            start_pos = reader.pos  # progress guard
            try:
                segments.append(cls._parse_segment(reader))
            except (BitstreamParseError, ReadError, ValueError):
                # Parsing failed - abort to avoid infinite loop
                break
            if reader.pos == start_pos:  # should never happen
                break

        return cls(
            data_unit_parameter=generic.data_unit_parameter,
            data_unit_link_flag=generic.data_unit_link_flag,
            segments=segments,
        )

    # ------------------------------------------------------------------ #
    # Segment-level parser                                               #
    # ------------------------------------------------------------------ #
    @classmethod
    def _parse_segment(cls, reader: BitReader) -> SectionTravelTimeSegment:
        # ─ PB L1 ─
        ext_flag = SectionTTExtFlag(reader.u(2))
        reader.flag()  # 1 undefined bit
        hour_raw = reader.u(5)

        # ─ PB L2 ─
        priority = SectionTTPriority(reader.u(2))
        minute_raw = reader.u(6)

        # ─ PB L3 ─
        link_count = reader.u(8)

        # Handle future reserved modes quickly: consume remaining bits and return stub
        if ext_flag in {
            SectionTTExtFlag.MODE_RESERVED_2,
            SectionTTExtFlag.MODE_RESERVED_3,
        }:
            reader.pos = reader.len
            dummy_route = RouteBlock(hour_raw, minute_raw, priority, link_count, [])
            return SectionTravelTimeSegment(ext_flag, dummy_route, [])

        # ─ Primary route (basic structure) ─
        start_pt = cls._parse_point(reader)
        end_pt = cls._parse_point(reader)
        vias = [cls._parse_point(reader) for _ in range(max(link_count - 2, 0))]

        primary = RouteBlock(
            hour_raw=hour_raw,
            minute_raw=minute_raw,
            priority=priority,
            link_count=link_count,
            points=[start_pt, *vias, end_pt],
        )

        # ─ Optional Alt-route groups (extension-1) ─
        alt_groups: list[AltRouteGroup] = []
        if ext_flag == SectionTTExtFlag.BASIC_EXT1 and reader.pos < reader.len:
            while reader.pos < reader.len:
                # If byte-aligned, peek next 2 bits - could be the ext_flag of the next segment
                if reader.pos % 8 == 0 and reader._bs.peek("uint:2") in {0, 1, 2, 3}:  # type: ignore[attr-defined]
                    break
                alt_groups.append(cls._parse_alt_group(reader))

        return SectionTravelTimeSegment(ext_flag, primary, alt_groups)

    # ------------------------------------------------------------------ #
    # Alt-route group parser                                             #
    # ------------------------------------------------------------------ #
    @classmethod
    def _parse_alt_group(cls, reader: BitReader) -> AltRouteGroup:
        alt_cnt = reader.u(5)
        reader.u(3)  # reserved bits
        routes: list[RouteBlock] = []

        for _ in range(alt_cnt):
            hour_raw = reader.u(5)
            minute_raw = reader.u(6)
            reader.align_byte()  # route blocks start on a byte boundary
            link_count = reader.u(8)
            start_pt = cls._parse_point(reader)
            end_pt = cls._parse_point(reader)
            vias = [cls._parse_point(reader) for _ in range(max(link_count - 2, 0))]
            routes.append(
                RouteBlock(
                    hour_raw, minute_raw, None, link_count, [start_pt, *vias, end_pt]
                )
            )

        return AltRouteGroup(alt_cnt, routes)

    # ------------------------------------------------------------------ #
    # Point parser                                                       #
    # ------------------------------------------------------------------ #
    @classmethod
    def _parse_point(cls, reader: BitReader) -> SectionPoint:
        mesh_flag = reader.flag()
        name_flag = reader.flag()
        link_type = LinkType(reader.u(2))
        link_hi = reader.u(4)
        link_lo = reader.u(8)

        coord_x = coord_y = None
        if mesh_flag:
            coord_x = reader.u(8)
            coord_y = reader.u(8)

        name = read_name(reader) if name_flag else None

        return SectionPoint(
            mesh_flag=mesh_flag,
            name_flag=name_flag,
            link_type=link_type,
            link_number=(link_hi << 8) | link_lo,
            coord_x_hi=coord_x,
            coord_y_hi=coord_y,
            name=name,
        )
