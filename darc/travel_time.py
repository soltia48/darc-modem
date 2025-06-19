import enum
from dataclasses import dataclass
from typing import Self

from bitstring import ConstBitStream

from .helpers import (
    BitReader,
    BitstreamParseError,
    DistanceUnit,
    SafeIntEnumMixin,
    TimeUnit,
)
from .l5_data import DataUnitBase, GenericDataUnit

# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class CongestionDegree(SafeIntEnumMixin):
    UNKNOWN = 0
    FREE = 1
    SLOW = 2
    JAM = 3


class ProvideForm(SafeIntEnumMixin):
    """Single-bit field that selects data layout for every link record."""

    TRAVEL_TIME = 0  # rich format — may contain travel-time & extensions
    CONGESTION_ONLY = 1  # compact format — congestion degree plus optional Ext-1


class TravelTimeExtFlag(enum.IntEnum):
    """6-bit flag for provide-form 0 (see ARIB table 43)."""

    BASIC_EXT1 = 60
    BASIC_EXT1_EXT2 = 61
    UNDEFINED = 62
    DISAPPEAR_OR_AGGREGATE = 63


class PerLinkExtFlag(enum.IntEnum):
    """2-bit flag for provide-form 1 (compact)."""

    NONE = 0
    BASIC_EXT1 = 1
    DISAPPEAR = 2
    AGGREGATE_OR_INVALID = 3


# ---------------------------------------------------------------------------
# Dataclasses — Extensions & Records
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class TravelTimeExt1:
    """Distance-related extension (Ext-1, 2 bytes)."""

    distance_unit: DistanceUnit
    head_pos_raw: int  # 0-127 — distance *from link end* to congestion head
    jam_length_raw: int  # 0-127 — congestion length

    # Convenience getters ------------------------------------------------
    @property
    def head_pos_m(self) -> int | None:
        return self.distance_unit.decode(self.head_pos_raw)

    @property
    def jam_length_m(self) -> int | None:
        return self.distance_unit.decode(self.jam_length_raw)


@dataclass(slots=True)
class TravelTimeExt2:
    """Extended travel-time (Ext-2, 1 byte)."""

    time_unit: TimeUnit
    link_travel_time_raw: int  # 0/126/127 ⇒ undefined

    @property
    def link_travel_time_sec(self) -> int | None:
        return self.time_unit.decode(self.link_travel_time_raw)


@dataclass(slots=True)
class TravelTimeLinkRecord:
    """One per-link record produced by the decoder."""

    congestion: CongestionDegree
    travel_time_sec: int | None
    ext_flag_raw: int | None  # raw 6-bit (form-0) or 2-bit (form-1)
    ext1: TravelTimeExt1 | None = None
    ext2: TravelTimeExt2 | None = None

    # Helper props -------------------------------------------------------
    @property
    def has_ext1(self) -> bool:
        return self.ext1 is not None

    @property
    def has_ext2(self) -> bool:
        return self.ext2 is not None


# ---------------------------------------------------------------------------
# Main Data-Unit class
# ---------------------------------------------------------------------------


@dataclass
class TravelTimeDataUnit(DataUnitBase):
    provide_form: ProvideForm
    link_count: int
    records: list[TravelTimeLinkRecord]

    # --------------------------------------------------------------
    # Factory
    # --------------------------------------------------------------
    @classmethod
    def from_generic(cls, generic: GenericDataUnit) -> Self:
        """Create a typed instance from :class:`GenericDataUnit`."""

        r = BitReader(ConstBitStream(generic.data_unit_data))

        # ─ Header byte 1 (PB H1) ─
        provide_form = ProvideForm(r.flag())
        _travel_time_kind = r.flag()  # spec-reserved, always 0 as of 2025
        info_single = r.flag()  # 0 ⇒ per-link info / 1 ⇒ first record covers all links
        _mode_flag = r.flag()  # 0 ⇒ current format / 1 ⇒ future reserved
        link_cnt_hi = r.u(4)

        # ─ Header byte 2 (PB H2) ─
        link_cnt_lo = r.u(8)
        link_count = (link_cnt_hi << 8) | link_cnt_lo

        # ─ Header bytes 3-4 we currently ignore (link-type etc.) ─
        _ = r.u(16)

        # If the mode flag was set we bail out because spec says to skip the unit
        if _mode_flag:
            return cls(
                generic.data_unit_parameter,
                generic.data_unit_link_flag,
                provide_form,
                link_count,
                [],
            )

        # ─ Record parsing ─
        num_records = 1 if info_single else link_count
        records: list[TravelTimeLinkRecord] = []

        if provide_form is ProvideForm.TRAVEL_TIME:
            for _ in range(num_records):
                records.append(cls._parse_form0(r))
        else:  # CONGESTION_ONLY
            for _ in range(num_records):
                nibble = r.u(4)
                records.append(cls._parse_form1(r, nibble))

        return cls(
            generic.data_unit_parameter,
            generic.data_unit_link_flag,
            provide_form,
            link_count,
            records,
        )

    # --------------------------------------------------------------
    # Low-level parsers
    # --------------------------------------------------------------
    @staticmethod
    def _parse_form0(reader: BitReader) -> TravelTimeLinkRecord:
        """Parse one **provide-form 0** record (8+ bits)."""

        byte = reader.u(8)
        congestion = CongestionDegree((byte >> 6) & 0x03)
        flag_u6 = byte & 0x3F

        travel_time: int | None = None
        ext1 = ext2 = None

        # 0-59 → quick travel-time in 10-second units; 0 means unknown
        if flag_u6 <= 59:
            travel_time = None if flag_u6 == 0 else flag_u6 * 10
        elif flag_u6 == TravelTimeExtFlag.BASIC_EXT1:
            ext1 = TravelTimeDataUnit._parse_ext1(reader)
        elif flag_u6 == TravelTimeExtFlag.BASIC_EXT1_EXT2:
            ext1 = TravelTimeDataUnit._parse_ext1(reader)
            ext2 = TravelTimeDataUnit._parse_ext2(reader)
        # flags 62/63 carry no additional bytes for current spec

        return TravelTimeLinkRecord(
            congestion=congestion,
            travel_time_sec=travel_time,
            ext_flag_raw=flag_u6,
            ext1=ext1,
            ext2=ext2,
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _parse_form1(reader: BitReader, nibble: int) -> TravelTimeLinkRecord:
        """Parse one **provide-form 1** record (4 bits + optional Ext-1)."""

        congestion = CongestionDegree(nibble & 0x03)
        ext_flag = (nibble >> 2) & 0x03

        ext1 = None
        if ext_flag == PerLinkExtFlag.BASIC_EXT1:
            ext1 = TravelTimeDataUnit._parse_ext1(reader)

        return TravelTimeLinkRecord(
            congestion=congestion,
            travel_time_sec=None,
            ext_flag_raw=ext_flag,
            ext1=ext1,
            ext2=None,
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _parse_ext1(reader: BitReader) -> TravelTimeExt1:
        """Read Ext-1 (2 bytes)."""

        try:
            b2, b3 = reader.u(8), reader.u(8)
        except BitstreamParseError as err:
            raise BitstreamParseError("Stream ended within Ext-1") from err

        unit_bits = ((b2 >> 7) << 1) | (b3 >> 7)
        distance_unit = DistanceUnit(unit_bits)
        return TravelTimeExt1(
            distance_unit=distance_unit,
            head_pos_raw=b2 & 0x7F,
            jam_length_raw=b3 & 0x7F,
        )

    # ------------------------------------------------------------------
    @staticmethod
    def _parse_ext2(reader: BitReader) -> TravelTimeExt2:
        """Read Ext-2 (1 byte)."""

        try:
            byte = reader.u(8)
        except BitstreamParseError as err:
            raise BitstreamParseError("Stream ended within Ext-2") from err

        time_unit = TimeUnit((byte >> 7) & 0x01)
        raw_time = byte & 0x7F
        return TravelTimeExt2(time_unit, raw_time)
