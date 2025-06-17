import enum
from dataclasses import dataclass
from typing import Self, cast

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


class LinkType(enum.IntEnum):
    EXPRESSWAY = 0
    URBAN_EXPRESSWAY = 1
    ARTERIAL = 2
    OTHER = 3


class DistanceUnitP(enum.IntEnum):
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
    distance_unit: DistanceUnitP
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

    # ---------- Convenience properties ----------
    @property
    def vacancy_rate_10pct(self) -> int | None:
        return (
            None if self.waiting_time_10min_raw == 15 else self.vacancy_rate_10pct_raw
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
    # Construction & public API                                          #
    # ------------------------------------------------------------------ #

    def __init__(self, parameter: int, link_flag: int, records: list[ParkingRecord]):
        super().__init__(parameter, link_flag)
        self.records = records

    @classmethod
    def from_generic(cls, generic: GenericDataUnit) -> Self:
        """Parse ``generic.data_unit_data`` into :class:`ParkingUnit`."""
        bs: ConstBitStream = ConstBitStream(generic.data_unit_data)
        records: list[ParkingRecord] = []
        while bs.pos < bs.len:
            try:
                records.append(cls._parse_record(bs))
            except ReadError:
                break  # truncated payload
        return cls(generic.data_unit_parameter, generic.data_unit_link_flag, records)

    # ------------------------------------------------------------------ #
    # Low-level parsers                                                  #
    # ------------------------------------------------------------------ #

    @classmethod
    def _parse_record(cls, bs: ConstBitStream) -> ParkingRecord:  # noqa: C901
        try:
            # --- PB L1 (8 bits) ---
            ext_flag_u2, vacancy_u3, is_general_b = cast(
                tuple[int, int, bool], bs.unpack("uint:2, uint:3, bool, pad:2")
            )
            ext_flag = ParkingExtFlag(ext_flag_u2)
            vacancy_status = VacancyStatus(vacancy_u3)

            # --- PB L2-L3 (32 bits) ---
            center_x, center_y = cast(tuple[int, int], bs.unpack("uint:16, uint:16"))

            # --- Optionals ---
            ext1 = (
                cls._parse_ext1(bs)
                if ext_flag
                in {ParkingExtFlag.BASIC_EXT1, ParkingExtFlag.BASIC_EXT1_EXT2}
                else None
            )
            ext2 = (
                cls._parse_ext2(bs)
                if ext_flag is ParkingExtFlag.BASIC_EXT1_EXT2
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
            raise BitstreamEndError("Stream ended mid-record") from err

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
                bs.unpack("bool, bool, uint:2, uint:12, uint:1, uint:7"),
            )
            link_type = LinkType(link_type_u2)
            distance_unit = DistanceUnitP(distance_unit_u1)

            entrance_x: int | None = None
            entrance_y: int | None = None
            if mesh_flag:
                entrance_x, entrance_y = cast(
                    tuple[int, int], bs.unpack("uint:16, uint:16")
                )

            name: str | None = None
            if name_flag:
                (name_len,) = cast(tuple[int], bs.unpack("uint:8"))
                name_bytes = cast(bytes, bs.read(name_len * 8).bytes)
                name = AribStringDecoder().decode(name_bytes)

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
            raise BitstreamEndError("Stream ended in Ext-1") from err

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
                tuple[
                    int,
                    int,
                    int,
                    int,
                    int,
                    int,
                    int,
                    int,
                    int,
                    int,
                    int,
                    int,
                ],
                bs.unpack(
                    "uint:4, uint:4, uint:3, uint:2, uint:3, uint:2, uint:3, uint:11, "
                    "uint:5, uint:3, uint:5, uint:3"
                ),
            )

            return ParkingExt2(
                vacancy_rate_10pct_raw=vacancy_rate_raw,
                waiting_time_10min_raw=waiting_time_raw,
                capacity_class=CapacityClass(capacity_u3),
                height_limit=HeightLimit(height_lim_u2),
                vehicle_limit=VehicleLimit(vehicle_lim_u3),
                discount_condition=DiscountCondition(discount_u2),
                fee_unit=FeeUnit(fee_unit_u3),
                fee_code_raw=fee_code_raw,
                start_hour_raw=start_hour_raw,
                start_min_raw=start_min_raw,
                end_hour_raw=end_hour_raw,
                end_min_raw=end_min_raw,
            )
        except ReadError as err:
            raise BitstreamEndError("Stream ended in Ext-2") from err


# ---------------------------------------------------------------------------
# Glue helper                                                               #
# ---------------------------------------------------------------------------


def data_unit_from_generic(generic: GenericDataUnit):
    """Return fully-parsed data-unit or original object."""
    if generic.data_unit_parameter == 0x42:
        return ParkingDataUnit.from_generic(generic)
    return generic
