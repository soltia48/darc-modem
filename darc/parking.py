from dataclasses import dataclass
from typing import List, Self

from bitstring import ConstBitStream, ReadError

from .helpers import (
    BitReader,
    BitstreamParseError,
    DistanceUnit,
    LinkType,
    SafeIntEnumMixin,
    read_name,
)
from .l5_data import DataUnitBase, GenericDataUnit  # existing project modules

# ────────────────────────────────────────────────────────────────────────────
# Enumerations
# ────────────────────────────────────────────────────────────────────────────


class ParkingExtFlag(SafeIntEnumMixin):
    BASIC = 0
    BASIC_EXT1 = 1
    BASIC_EXT1_EXT2 = 2
    MODE_RESERVED = 3  # reserved for future formats


class VacancyStatus(SafeIntEnumMixin):
    EMPTY = 0
    CONGESTED = 1
    FULL = 2
    CLOSED = 3
    UNDEFINED_4 = 4
    UNDEFINED_5 = 5
    UNDEFINED_6 = 6
    UNKNOWN = 7


class DistanceUnitParking(SafeIntEnumMixin):
    TEN_M = 0
    HUNDRED_M = 1


class CapacityClass(SafeIntEnumMixin):
    UNDER_20 = 0
    UNDER_50 = 1
    UNDER_100 = 2
    UNDER_200 = 3
    UNDER_500 = 4
    UNDER_1000 = 5
    OVER_1000 = 6
    UNKNOWN = 7


class HeightLimit(SafeIntEnumMixin):
    NONE = 0
    LIMITED = 1
    UNDEFINED = 2
    UNKNOWN = 3


class VehicleLimit(SafeIntEnumMixin):
    NONE = 0
    LARGE_VEHICLE = 1
    THREE_NUMBER = 2
    UNDEFINED_3 = 3
    UNDEFINED_4 = 4
    UNDEFINED_5 = 5
    OTHER = 6
    UNKNOWN = 7


class DiscountCondition(SafeIntEnumMixin):
    NONE = 0
    EXISTS = 1
    UNDEFINED = 2
    UNKNOWN = 3


class FeeUnit(SafeIntEnumMixin):
    MIN_30 = 0
    HOUR_1 = 1
    HOUR_2 = 2
    HOUR_3 = 3
    HALF_DAY = 4
    ONE_DAY = 5
    ONCE = 6
    UNKNOWN = 7


# ────────────────────────────────────────────────────────────────────────────
# Dataclasses - extensions and record
# ────────────────────────────────────────────────────────────────────────────


@dataclass(slots=True)
class ParkingExt1:
    """Optional extension with entrance information."""

    mesh_flag: bool
    name_flag: bool
    link_type: LinkType
    link_number: int
    distance_unit: DistanceUnitParking
    entrance_distance_raw: int
    entrance_x: int | None
    entrance_y: int | None
    name: str | None

    # convenience -------------------------------------------------------
    @property
    def entrance_distance(self) -> int | None:
        return None if self.entrance_distance_raw == 127 else self.entrance_distance_raw


@dataclass(slots=True)
class ParkingExt2:
    """Optional extension with vacancy rate, fee and opening hours."""

    vacancy_rate_raw: int  # 0-14 → value *10 %, 15 → unknown
    waiting_time_raw: int  # 0-14 → value *10 min, 15 → unknown
    capacity_class: CapacityClass
    height_limit: HeightLimit
    vehicle_limit: VehicleLimit
    discount_condition: DiscountCondition
    fee_unit: FeeUnit
    fee_code_raw: int  # 0-2046 valid, 2047 unknown
    start_hour_raw: int  # 0-23 or 24-31 (invalid → None)
    start_min_raw: int  # 0-5 for 10-min steps, 6-7 invalid → None
    end_hour_raw: int
    end_min_raw: int

    # convenience -------------------------------------------------------
    @property
    def vacancy_rate_pct(self) -> int | None:
        return None if self.vacancy_rate_raw == 15 else self.vacancy_rate_raw * 10

    @property
    def waiting_time_min(self) -> int | None:
        return None if self.waiting_time_raw == 15 else self.waiting_time_raw * 10

    @property
    def fee_code(self) -> int | None:
        return None if self.fee_code_raw == 2047 else self.fee_code_raw * 10

    @property
    def start_hour(self) -> int | None:  # 0-23 valid
        return None if self.start_hour_raw >= 24 else self.start_hour_raw

    @property
    def start_min(self) -> int | None:  # 0-5 → 0-50 min
        return None if self.start_min_raw >= 6 else self.start_min_raw * 10

    @property
    def end_hour(self) -> int | None:
        return None if self.end_hour_raw >= 24 else self.end_hour_raw

    @property
    def end_min(self) -> int | None:
        return None if self.end_min_raw >= 6 else self.end_min_raw * 10


@dataclass(slots=True)
class ParkingRecord:
    """Complete parking record with optional extensions."""

    ext_flag: ParkingExtFlag
    vacancy_status: VacancyStatus
    is_general: bool  # False → reserved parking only
    center_x: int  # 16-bit X coordinate
    center_y: int  # 16-bit Y coordinate
    ext1: ParkingExt1 | None = None
    ext2: ParkingExt2 | None = None


# ────────────────────────────────────────────────────────────────────────────
# Main data-unit parser
# ────────────────────────────────────────────────────────────────────────────

@dataclass
class ParkingDataUnit(DataUnitBase):
    records: List[ParkingRecord]

    # ------------------------------------------------------------------
    @classmethod
    def from_generic(cls, generic: GenericDataUnit) -> Self:
        """Convert :class:`GenericDataUnit` into a typed *ParkingDataUnit*."""
        reader = BitReader(ConstBitStream(generic.data_unit_data))
        records: list[ParkingRecord] = []

        while reader.pos < reader.len:
            start_bit = reader.pos
            try:
                records.append(cls._parse_record(reader))
            except BitstreamParseError:
                # stop on truncated stream to prevent infinite loop
                break
            # safety check: ensure progress
            if reader.pos == start_bit:
                raise BitstreamParseError("parser made no progress")

        return cls(generic.data_unit_parameter, generic.data_unit_link_flag, records)

    # ------------------------------------------------------------------
    # Record-level parser
    # ------------------------------------------------------------------
    @classmethod
    def _parse_record(cls, r: BitReader) -> ParkingRecord:
        """Parse exactly one parking record."""
        try:
            # --- PB L1 (8 bits) ----------------------------------------
            ext_flag_u2, vacancy_u3, is_general = r.readlist("uint:2, uint:3, bool")
            r.readlist("pad:2")  # unused bits
            ext_flag = ParkingExtFlag(ext_flag_u2)
            vacancy_status = VacancyStatus(vacancy_u3)

            # --- PB L2-L3 (32 bits) ------------------------------------
            center_x, center_y = r.readlist("uint:16, uint:16")

            # --- Optional extensions -----------------------------------
            ext1 = (
                cls._parse_ext1(r)
                if ext_flag
                in {ParkingExtFlag.BASIC_EXT1, ParkingExtFlag.BASIC_EXT1_EXT2}
                else None
            )
            ext2 = (
                cls._parse_ext2(r)
                if ext_flag is ParkingExtFlag.BASIC_EXT1_EXT2
                else None
            )

            return ParkingRecord(
                ext_flag=ext_flag,
                vacancy_status=vacancy_status,
                is_general=is_general,
                center_x=center_x,
                center_y=center_y,
                ext1=ext1,
                ext2=ext2,
            )
        except ReadError as err:
            raise BitstreamParseError("stream ended mid-record") from err

    # ------------------------------------------------------------------
    # Extension parsers
    # ------------------------------------------------------------------
    @staticmethod
    def _parse_ext1(r: BitReader) -> ParkingExt1:
        """Parse extension-1 (entrance information)."""
        try:
            (
                mesh_flag,
                name_flag,
                link_type_u2,
                link_number,
                dist_unit_u1,
                entrance_dist,
            ) = r.readlist("bool, bool, uint:2, uint:12, uint:1, uint:7")
            link_type = LinkType(link_type_u2)
            distance_unit = DistanceUnitParking(dist_unit_u1)

            entrance_x = entrance_y = None
            if mesh_flag:  # 32-bit X/Y only if *mesh_flag* set
                entrance_x, entrance_y = r.readlist("uint:16, uint:16")

            name: str | None = None
            if name_flag:
                name = read_name(r)

            return ParkingExt1(
                mesh_flag=mesh_flag,
                name_flag=name_flag,
                link_type=link_type,
                link_number=link_number,
                distance_unit=distance_unit,
                entrance_distance_raw=entrance_dist,
                entrance_x=entrance_x,
                entrance_y=entrance_y,
                name=name,
            )
        except ReadError as err:
            raise BitstreamParseError("stream ended in Ext-1") from err

    # ------------------------------------------------------------------
    @staticmethod
    def _parse_ext2(r: BitReader) -> ParkingExt2:
        """Parse extension-2 (vacancy + fee details)."""
        try:
            (
                vacancy_raw,
                waiting_raw,
                capacity_u3,
                height_u2,
                vehicle_u3,
                discount_u2,
                fee_unit_u3,
                fee_code_raw,
                start_hour_raw,
                start_min_raw,
                end_hour_raw,
                end_min_raw,
            ) = r.readlist(
                "uint:4, uint:4, uint:3, uint:2, uint:3, uint:2, uint:3, uint:11, "
                "uint:5, uint:3, uint:5, uint:3"
            )

            return ParkingExt2(
                vacancy_rate_raw=vacancy_raw,
                waiting_time_raw=waiting_raw,
                capacity_class=CapacityClass(capacity_u3),
                height_limit=HeightLimit(height_u2),
                vehicle_limit=VehicleLimit(vehicle_u3),
                discount_condition=DiscountCondition(discount_u2),
                fee_unit=FeeUnit(fee_unit_u3),
                fee_code_raw=fee_code_raw,
                start_hour_raw=start_hour_raw,
                start_min_raw=start_min_raw,
                end_hour_raw=end_hour_raw,
                end_min_raw=end_min_raw,
            )
        except ReadError as err:
            raise BitstreamParseError("stream ended in Ext-2") from err
