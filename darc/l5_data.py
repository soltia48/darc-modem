from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import IntEnum
from logging import getLogger
from typing import ClassVar, Final, Self, TypeGuard

from bitstring import BitStream, Bits, pack

# Constants
INFORMATION_SEPARATOR: Final[int] = 0x1E
DATA_UNIT_SEPARATOR: Final[int] = 0x1F


class DataHeaderParameter(IntEnum):
    """Data header parameter values."""

    PROGRAM_DATA_A = 0x30
    PROGRAM_DATA_B = 0x31
    PAGE_DATA_A = 0x32
    PAGE_DATA_B = 0x33
    PROGRAM_COMMON_MACRO_A = 0x34
    PROGRAM_COMMON_MACRO_B = 0x35
    CONTINUE = 0x36
    PROGRAM_INDEX = 0x37


@dataclass
class DataHeaderBase(ABC):
    """Base class for all data headers."""

    _logger: ClassVar = getLogger(__name__)

    @abstractmethod
    def to_buffer(self) -> Bits:
        """Convert data header to binary buffer."""

    @classmethod
    def peek_data_header_parameter(cls, stream: BitStream) -> int:
        """Peek next data header parameter without consuming stream."""
        buffer: bytes = stream.peek("bytes:2")  # type: ignore
        return buffer[1]

    @classmethod
    @abstractmethod
    def data_header_parameter(cls) -> DataHeaderParameter:
        """Get data header parameter value."""

    @classmethod
    @abstractmethod
    def read(cls, stream: BitStream) -> Self:
        """Read data header from bitstream."""

    @classmethod
    def read_common_header(cls, stream: BitStream) -> tuple[int, int]:
        """Read common header fields from stream."""
        information_separator: int = stream.read("uint8")
        if information_separator != INFORMATION_SEPARATOR:
            raise ValueError(
                f"Invalid information separator: {information_separator:#x}"
            )

        data_header_parameter: int = stream.read("uint8")
        if data_header_parameter != cls.data_header_parameter():
            raise ValueError(
                f"Invalid data header parameter: {data_header_parameter:#x}"
            )

        return information_separator, data_header_parameter


@dataclass
class ProgramDataHeaderA(DataHeaderBase):
    """Program data header type A."""

    program_number: int
    content_change: int
    total_pages: int
    display_instruction: int
    information_type: int
    display_format: int

    def to_buffer(self) -> Bits:
        buffer = pack(
            """uint8, uint8,
               uint8, uint2, uint6, uint8, uint4, uint4""",
            INFORMATION_SEPARATOR,
            self.data_header_parameter(),
            self.program_number,
            self.content_change,
            self.total_pages,
            self.display_instruction,
            self.information_type,
            self.display_format,
        )
        return Bits(buffer)

    @classmethod
    def data_header_parameter(cls) -> DataHeaderParameter:
        return DataHeaderParameter.PROGRAM_DATA_A

    @classmethod
    def read(cls, stream: BitStream) -> Self:
        cls.read_common_header(stream)

        return cls(
            program_number=stream.read("uint8"),
            content_change=stream.read("uint2"),
            total_pages=stream.read("uint6"),
            display_instruction=stream.read("uint8"),
            information_type=stream.read("uint4"),
            display_format=stream.read("uint4"),
        )


@dataclass
class ProgramDataHeaderB(DataHeaderBase):
    """Program data header type B with map information."""

    program_number: int
    content_update: int
    total_pages: int
    display_instruction: int
    information_type: int
    display_format: int
    undefined_0: int
    prefecture_identifier: int
    map_type: int
    map_zoom: int
    map_position_x: int
    map_position_y: int

    def to_buffer(self) -> Bits:
        buffer = pack(
            """uint8, uint8,
               uint8, uint2, uint6, uint8, uint4, uint4,
               uint2, uint6, uint4, uint4, uint8, uint8, uint4, uint4""",
            INFORMATION_SEPARATOR,
            self.data_header_parameter(),
            self.program_number,
            self.content_update,
            self.total_pages,
            self.display_instruction,
            self.information_type,
            self.display_format,
            self.undefined_0,
            self.prefecture_identifier,
            self.map_type,
            self.map_zoom,
            self.map_position_x >> 4,
            self.map_position_y >> 4,
            self.map_position_x & 0x0F,
            self.map_position_y & 0x0F,
        )
        return Bits(buffer)

    @classmethod
    def data_header_parameter(cls) -> DataHeaderParameter:
        return DataHeaderParameter.PROGRAM_DATA_B

    @classmethod
    def read(cls, stream: BitStream) -> Self:
        cls.read_common_header(stream)

        # Read basic fields
        program_number = stream.read("uint8")
        content_update = stream.read("uint2")
        total_pages = stream.read("uint6")
        display_instruction = stream.read("uint8")
        information_type = stream.read("uint4")
        display_format = stream.read("uint4")

        # Read map-related fields
        undefined_0 = stream.read("uint2")
        prefecture_identifier = stream.read("uint6")
        map_type = stream.read("uint4")
        map_zoom = stream.read("uint4")

        # Read and combine split position fields
        map_position_x = (stream.read("uint8") << 4) | stream.read("uint4")
        map_position_y = (stream.read("uint8") << 4) | stream.read("uint4")

        return cls(
            program_number=program_number,
            content_update=content_update,
            total_pages=total_pages,
            display_instruction=display_instruction,
            information_type=information_type,
            display_format=display_format,
            undefined_0=undefined_0,
            prefecture_identifier=prefecture_identifier,
            map_type=map_type,
            map_zoom=map_zoom,
            map_position_x=map_position_x,
            map_position_y=map_position_y,
        )


@dataclass
class PageDataHeaderA(DataHeaderBase):
    """Page data header type A."""

    program_number: int
    content_update: int
    total_pages: int
    display_instruction: int
    information_type: int
    display_format: int
    header_raster_color: int
    raster_color: int

    def to_buffer(self) -> Bits:
        buffer = pack(
            """uint8, uint8,
               uint8, uint2, uint6, uint8, uint4, uint4,
               uint4, uint4""",
            INFORMATION_SEPARATOR,
            self.data_header_parameter(),
            self.program_number,
            self.content_update,
            self.total_pages,
            self.display_instruction,
            self.information_type,
            self.display_format,
            self.header_raster_color,
            self.raster_color,
        )
        return Bits(buffer)

    @classmethod
    def data_header_parameter(cls) -> DataHeaderParameter:
        return DataHeaderParameter.PAGE_DATA_A

    @classmethod
    def read(cls, stream: BitStream) -> Self:
        cls.read_common_header(stream)

        return cls(
            program_number=stream.read("uint8"),
            content_update=stream.read("uint2"),
            total_pages=stream.read("uint6"),
            display_instruction=stream.read("uint8"),
            information_type=stream.read("uint4"),
            display_format=stream.read("uint4"),
            header_raster_color=stream.read("uint4"),
            raster_color=stream.read("uint4"),
        )


@dataclass
class PageDataHeaderB(DataHeaderBase):
    """Page data header type B with map information."""

    program_number: int
    content_update: int
    page_number: int
    display_instruction: int
    information_type: int
    display_format: int
    header_raster_color: int
    raster_color: int
    undefined_0: int
    prefecture_identifier: int
    map_type: int
    map_zoom: int
    map_position_x: int
    map_position_y: int
    content_type: int
    information_deliver_time_flag: int
    information_deliver_time_hour: int
    information_deliver_time_minute: int
    link_layer: int
    link_type: int
    reference_link_number: int

    def to_buffer(self) -> Bits:
        buffer = pack(
            """uint8, uint8,
               uint8, uint2, uint6, uint8, uint4, uint4,
               uint4, uint4, uint2, uint6, uint4, uint4, uint8, uint8, uint4, uint4,
               uint4, uint1, uint3, uint2, uint6, uint2, uint2, uint4, uint8""",
            INFORMATION_SEPARATOR,
            self.data_header_parameter(),
            self.program_number,
            self.content_update,
            self.page_number,
            self.display_instruction,
            self.information_type,
            self.display_format,
            self.header_raster_color,
            self.raster_color,
            self.undefined_0,
            self.prefecture_identifier,
            self.map_type,
            self.map_zoom,
            self.map_position_x >> 4,
            self.map_position_y >> 4,
            self.map_position_x & 0x0F,
            self.map_position_y & 0x0F,
            self.content_type,
            self.information_deliver_time_flag,
            self.information_deliver_time_hour >> 3,
            self.information_deliver_time_hour & 0x07,
            self.information_deliver_time_minute,
            self.link_layer,
            self.link_type,
            self.reference_link_number >> 8,
            self.reference_link_number & 0xFF,
        )
        return Bits(buffer)

    @classmethod
    def data_header_parameter(cls) -> DataHeaderParameter:
        return DataHeaderParameter.PAGE_DATA_B

    @classmethod
    def read(cls, stream: BitStream) -> Self:
        cls.read_common_header(stream)

        # Read basic fields
        program_number = stream.read("uint8")
        content_update = stream.read("uint2")
        page_number = stream.read("uint6")
        display_instruction = stream.read("uint8")
        information_type = stream.read("uint4")
        display_format = stream.read("uint4")
        header_raster_color = stream.read("uint4")
        raster_color = stream.read("uint4")

        # Read map-related fields
        undefined_0 = stream.read("uint2")
        prefecture_identifier = stream.read("uint6")
        map_type = stream.read("uint4")
        map_zoom = stream.read("uint4")
        map_position_x = (stream.read("uint8") << 4) | stream.read("uint4")
        map_position_y = (stream.read("uint8") << 4) | stream.read("uint4")

        # Read time-related fields
        content_type = stream.read("uint4")
        information_deliver_time_flag = stream.read("uint1")
        information_deliver_time_hour = (stream.read("uint3") << 2) | stream.read(
            "uint2"
        )
        information_deliver_time_minute = stream.read("uint6")

        # Read link-related fields
        link_layer = stream.read("uint2")
        link_type = stream.read("uint2")
        reference_link_number = (stream.read("uint4") << 8) | stream.read("uint8")

        return cls(
            program_number=program_number,
            content_update=content_update,
            page_number=page_number,
            display_instruction=display_instruction,
            information_type=information_type,
            display_format=display_format,
            header_raster_color=header_raster_color,
            raster_color=raster_color,
            undefined_0=undefined_0,
            prefecture_identifier=prefecture_identifier,
            map_type=map_type,
            map_zoom=map_zoom,
            map_position_x=map_position_x,
            map_position_y=map_position_y,
            content_type=content_type,
            information_deliver_time_flag=information_deliver_time_flag,
            information_deliver_time_hour=information_deliver_time_hour,
            information_deliver_time_minute=information_deliver_time_minute,
            link_layer=link_layer,
            link_type=link_type,
            reference_link_number=reference_link_number,
        )


@dataclass
class ProgramCommonMacroDataHeaderA(DataHeaderBase):
    """Program common macro data header type A."""

    display_instruction: int
    update: int
    undefined_0: int
    display_format: int
    program_common_macro_set: int
    program_common_macro_set_code: int

    def to_buffer(self) -> Bits:
        buffer = pack(
            """uint8, uint8,
               uint8, uint1, uint3, uint4, uint8, uint8, uint8""",
            INFORMATION_SEPARATOR,
            self.data_header_parameter(),
            self.display_instruction,
            self.update,
            self.undefined_0,
            self.display_format,
            self.program_common_macro_set,
            self.program_common_macro_set_code >> 8,
            self.program_common_macro_set_code & 0xFF,
        )
        return Bits(buffer)

    @classmethod
    def data_header_parameter(cls) -> DataHeaderParameter:
        return DataHeaderParameter.PROGRAM_COMMON_MACRO_A

    @classmethod
    def read(cls, stream: BitStream) -> Self:
        cls.read_common_header(stream)

        # Read basic fields
        display_instruction = stream.read("uint8")
        update = stream.read("uint1")
        undefined_0 = stream.read("uint3")
        display_format = stream.read("uint4")

        # Read macro-related fields
        program_common_macro_set = stream.read("uint8")
        program_common_macro_set_code = (stream.read("uint8") << 8) | stream.read(
            "uint8"
        )

        return cls(
            display_instruction=display_instruction,
            update=update,
            undefined_0=undefined_0,
            display_format=display_format,
            program_common_macro_set=program_common_macro_set,
            program_common_macro_set_code=program_common_macro_set_code,
        )


@dataclass
class ProgramCommonMacroDataHeaderB(DataHeaderBase):
    """Program common macro data header type B with map information."""

    display_instruction: int
    update: int
    undefined_0: int
    display_format: int
    program_common_macro_set: int
    program_common_macro_set_code: int
    undefined_1: int
    prefecture_identifier: int
    map_type: int
    map_zoom: int
    map_position_x: int
    map_position_y: int
    link_layer: int
    link_type: int
    reference_link_number: int

    def to_buffer(self) -> Bits:
        buffer = pack(
            """uint8, uint8,
               uint8, uint1, uint3, uint4, uint8, uint8, uint8,
               uint2, uint6, uint4, uint4, uint8, uint8, uint4, uint4,
               uint2, uint2, uint4, uint8""",
            INFORMATION_SEPARATOR,
            self.data_header_parameter(),
            self.display_instruction,
            self.update,
            self.undefined_0,
            self.display_format,
            self.program_common_macro_set,
            self.program_common_macro_set_code >> 8,
            self.program_common_macro_set_code & 0xFF,
            self.undefined_1,
            self.prefecture_identifier,
            self.map_type,
            self.map_zoom,
            self.map_position_x >> 4,
            self.map_position_y >> 4,
            self.map_position_x & 0x0F,
            self.map_position_y & 0x0F,
            self.link_layer,
            self.link_type,
            self.reference_link_number >> 8,
            self.reference_link_number & 0xFF,
        )
        return Bits(buffer)

    @classmethod
    def data_header_parameter(cls) -> DataHeaderParameter:
        return DataHeaderParameter.PROGRAM_COMMON_MACRO_B

    @classmethod
    def read(cls, stream: BitStream) -> Self:
        cls.read_common_header(stream)

        # Read basic fields
        display_instruction = stream.read("uint8")
        update = stream.read("uint1")
        undefined_0 = stream.read("uint3")
        display_format = stream.read("uint4")

        # Read macro-related fields
        program_common_macro_set = stream.read("uint8")
        program_common_macro_set_code = (stream.read("uint8") << 8) | stream.read(
            "uint8"
        )

        # Read map-related fields
        undefined_1 = stream.read("uint2")
        prefecture_identifier = stream.read("uint6")
        map_type = stream.read("uint4")
        map_zoom = stream.read("uint4")
        map_position_x = (stream.read("uint8") << 4) | stream.read("uint4")
        map_position_y = (stream.read("uint8") << 4) | stream.read("uint4")

        # Read link-related fields
        link_layer = stream.read("uint2")
        link_type = stream.read("uint2")
        reference_link_number = (stream.read("uint4") << 8) | stream.read("uint8")

        return cls(
            display_instruction=display_instruction,
            update=update,
            undefined_0=undefined_0,
            display_format=display_format,
            program_common_macro_set=program_common_macro_set,
            program_common_macro_set_code=program_common_macro_set_code,
            undefined_1=undefined_1,
            prefecture_identifier=prefecture_identifier,
            map_type=map_type,
            map_zoom=map_zoom,
            map_position_x=map_position_x,
            map_position_y=map_position_y,
            link_layer=link_layer,
            link_type=link_type,
            reference_link_number=reference_link_number,
        )


@dataclass
class ContinueDataHeader(DataHeaderBase):
    """Continue data header with no additional fields."""

    def to_buffer(self) -> Bits:
        buffer = pack(
            "uint8, uint8",
            INFORMATION_SEPARATOR,
            self.data_header_parameter(),
        )
        return Bits(buffer)

    @classmethod
    def data_header_parameter(cls) -> DataHeaderParameter:
        return DataHeaderParameter.CONTINUE

    @classmethod
    def read(cls, stream: BitStream) -> Self:
        cls.read_common_header(stream)
        return cls()


@dataclass
class ProgramIndexDataHeader(DataHeaderBase):
    """Program index data header."""

    undefined_0: int
    index_control: int

    def to_buffer(self) -> Bits:
        buffer = pack(
            """uint8, uint8,
               uint6, uint2""",
            INFORMATION_SEPARATOR,
            self.data_header_parameter(),
            self.undefined_0,
            self.index_control,
        )
        return Bits(buffer)

    @classmethod
    def data_header_parameter(cls) -> DataHeaderParameter:
        return DataHeaderParameter.PROGRAM_INDEX

    @classmethod
    def read(cls, stream: BitStream) -> Self:
        cls.read_common_header(stream)
        return cls(
            undefined_0=stream.read("uint6"),
            index_control=stream.read("uint2"),
        )


@dataclass
class GenericDataUnit:
    """Generic data unit structure."""

    data_unit_parameter: int
    data_unit_link_flag: int
    data_unit_data: bytes

    _logger: ClassVar = getLogger(__name__)

    @classmethod
    def is_valid_unit(cls, data: Self | bytes) -> TypeGuard[Self]:
        """Type guard to check if data is a valid GenericDataUnit."""
        return isinstance(data, cls)

    def to_buffer(self) -> Bits:
        """Convert data unit to binary buffer."""
        data_length = len(self.data_unit_data)
        buffer = pack(
            "uint8, uint8, uint1, uint7, uint8, bytes",
            DATA_UNIT_SEPARATOR,
            self.data_unit_parameter,
            self.data_unit_link_flag,
            data_length >> 8,
            data_length & 0xFF,
            self.data_unit_data,
        )
        return Bits(buffer)

    @classmethod
    def read(cls, stream: BitStream) -> Self | bytes:
        """Read data unit from bitstream."""
        data_unit_separator: int = stream.read("uint8")
        if data_unit_separator != DATA_UNIT_SEPARATOR:
            cls._logger.warning(
                f"Invalid data unit separator: {data_unit_separator:#x}"
            )
            stream.bytepos -= 1
            return stream.read("bytes")

        data_unit_parameter = stream.read("uint8")
        data_unit_link_flag = stream.read("uint1")
        data_unit_size = (stream.read("uint7") << 8) | stream.read("uint8")
        data_unit_data = stream.read(8 * data_unit_size).bytes

        return cls(
            data_unit_parameter=data_unit_parameter,
            data_unit_link_flag=data_unit_link_flag,
            data_unit_data=data_unit_data,
        )


@dataclass
class Segment:
    """Segment data structure."""

    segment_identifier: int
    other_station_number: int | None
    other_station_segment_identifier: int | None
    segment_data: bytes

    @classmethod
    def read(cls, stream: BitStream) -> Self:
        """Read segment from bitstream."""
        segment_identifier: int = stream.read("uint4")
        other_station_number = None
        other_station_segment_identifier = None

        # Read optional station fields
        if segment_identifier == 0xE:
            other_station_number = stream.read("uint4")
            other_station_segment_identifier = stream.read("uint4")

        # Read segment length and data
        segment_length: int = stream.read("uint4")
        if segment_length == 0xF:
            segment_length = stream.read("uint8")

        segment_data = stream.read(8 * segment_length).bytes

        return cls(
            segment_identifier=segment_identifier,
            other_station_number=other_station_number,
            other_station_segment_identifier=other_station_segment_identifier,
            segment_data=segment_data,
        )


def read_data_header(stream: BitStream) -> DataHeaderBase | None:
    """Read appropriate data header from stream based on parameter.

    Args:
        stream: Input bitstream

    Returns:
        Parsed data header or None if header type unknown

    Note:
        Returns None if the data header parameter is not recognized.
    """
    data_header_parameter = DataHeaderBase.peek_data_header_parameter(stream)

    # Map parameter values to header classes
    header_classes = {
        DataHeaderParameter.PROGRAM_DATA_A: ProgramDataHeaderA,
        DataHeaderParameter.PROGRAM_DATA_B: ProgramDataHeaderB,
        DataHeaderParameter.PAGE_DATA_A: PageDataHeaderA,
        DataHeaderParameter.PAGE_DATA_B: PageDataHeaderB,
        DataHeaderParameter.PROGRAM_COMMON_MACRO_A: ProgramCommonMacroDataHeaderA,
        DataHeaderParameter.PROGRAM_COMMON_MACRO_B: ProgramCommonMacroDataHeaderB,
        DataHeaderParameter.CONTINUE: ContinueDataHeader,
        DataHeaderParameter.PROGRAM_INDEX: ProgramIndexDataHeader,
    }

    try:
        parameter = DataHeaderParameter(data_header_parameter)
        if header_class := header_classes.get(parameter):
            return header_class.read(stream)
    except ValueError:
        logger = getLogger(__name__)
        logger.warning(f"Unknown data header parameter: {data_header_parameter:#x}")

    return None
