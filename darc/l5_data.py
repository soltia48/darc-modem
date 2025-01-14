from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import IntEnum
from logging import getLogger
from typing import ClassVar, Final, Self, TypeAlias, Sequence

from bitstring import BitStream, Bits, pack

INFORMATION_SEPARATOR: Final[int] = 0x1E
DATA_UNIT_SEPARATOR: Final[int] = 0x1F

Buffer: TypeAlias = Bits


@dataclass
class DataHeaderBase:
    _logger: ClassVar = getLogger(__name__)

    @abstractmethod
    def to_buffer(self) -> Buffer:
        pass

    @classmethod
    def peek_data_header_parameter(cls, stream: BitStream) -> int:
        buffer = stream.peek("bytes2")
        return buffer[1]

    @abstractmethod
    @classmethod
    def data_header_parameter(cls) -> int:
        pass

    @abstractmethod
    @classmethod
    def read(cls, stream: BitStream) -> Self:
        pass


@dataclass
class ProgramDataHeaderA(DataHeaderBase):
    program_number: int
    content_change: int
    total_pages: int
    display_instruction: int
    information_type: int
    display_format: int

    def to_buffer(self) -> Buffer:
        buffer = pack(
            f"""uint8, uint8,
                uint8, uint6, uint2, uint8, uint4, uint4
            """,
            INFORMATION_SEPARATOR,
            self.data_header_parameter(),
            self.program_number,
            self.total_pages,
            self.content_change,
            self.display_instruction,
            self.display_format,
            self.information_type,
        )
        return Buffer(buffer)

    @classmethod
    def data_header_parameter(cls):
        return 0x30

    @classmethod
    def read(cls, stream: BitStream) -> Self:
        information_separator: int = stream.read("uint8")
        if information_separator != INFORMATION_SEPARATOR:
            cls._logger.warning(
                "Invalid information separator: %s", hex(information_separator)
            )
        data_header_parameter: int = stream.read("uint8")
        if data_header_parameter != cls.data_header_parameter():
            cls._logger.warning(
                "Invalid data header parameter: %s", hex(data_header_parameter)
            )

        program_number: int = stream.read("uint8")
        total_pages: int = stream.read("uint6")
        content_change: int = stream.read("uint2")
        display_instruction: int = stream.read("uint8")
        display_format: int = stream.read("uint4")
        information_type: int = stream.read("uint4")

        return cls(
            program_number=program_number,
            total_pages=total_pages,
            content_change=content_change,
            display_instruction=display_instruction,
            display_format=display_format,
            information_type=information_type,
        )


@dataclass
class ProgramDataHeaderB(DataHeaderBase):
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

    def to_buffer(self) -> Buffer:
        buffer = pack(
            f"""uint8, uint8,
                uint8, uint6, uint2, uint8, uint4, uint4,
                uint6, uint2, uint4, uint4, uint8, uint8, uint4, uint4
            """,
            INFORMATION_SEPARATOR,
            self.data_header_parameter(),
            self.program_number,
            self.total_pages,
            self.content_update,
            self.display_instruction,
            self.display_format,
            self.information_type,
            self.prefecture_identifier,
            self.undefined_0,
            self.map_zoom,
            self.map_type,
            self.map_position_x >> 4,
            self.map_position_y >> 4,
            self.map_position_y & 0x0F,
            self.map_position_x & 0x0F,
        )
        return Buffer(buffer)

    @classmethod
    def data_header_parameter(cls):
        return 0x31

    @classmethod
    def read(cls, stream: BitStream) -> Self:
        information_separator: int = stream.read("uint8")
        if information_separator != INFORMATION_SEPARATOR:
            cls._logger.warning(
                "Invalid information separator: %s", hex(information_separator)
            )
        data_header_parameter: int = stream.read("uint8")
        if data_header_parameter != cls.data_header_parameter():
            cls._logger.warning(
                "Invalid data header parameter: %s", hex(data_header_parameter)
            )

        program_number: int = stream.read("uint8")
        total_pages: int = stream.read("uint6")
        content_update: int = stream.read("uint2")
        display_instruction: int = stream.read("uint8")
        display_format: int = stream.read("uint4")
        information_type: int = stream.read("uint4")
        prefecture_identifier: int = stream.read("uint6")
        undefined_0: int = stream.read("uint2")
        map_zoom: int = stream.read("uint4")
        map_type: int = stream.read("uint4")
        map_position_x_high: int = stream.read("uint8")
        map_position_y_high: int = stream.read("uint8")
        map_position_y_low: int = stream.read("uint4")
        map_position_x_low: int = stream.read("uint4")
        map_position_x = map_position_x_high << 4 | map_position_x_low
        map_position_y = map_position_y_high << 4 | map_position_y_low

        return cls(
            program_number=program_number,
            total_pages=total_pages,
            content_update=content_update,
            display_instruction=display_instruction,
            display_format=display_format,
            information_type=information_type,
            prefecture_identifier=prefecture_identifier,
            undefined_0=undefined_0,
            map_zoom=map_zoom,
            map_type=map_type,
            map_position_x=map_position_x,
            map_position_y=map_position_y,
        )


@dataclass
class PageDataHeaderA(DataHeaderBase):
    program_number: int
    content_update: int
    total_pages: int
    display_instruction: int
    information_type: int
    display_format: int
    header_raster_color: int
    raster_color: int

    def to_buffer(self) -> Buffer:
        """Convert data group to binary buffer.

        Returns:
            Binary buffer containing packed data group
        """
        buffer = pack(
            f"""uint8, uint8,
                uint8, uint6, uint2, uint8, uint4, uint4,
                uint4, uint4
            """,
            INFORMATION_SEPARATOR,
            self.data_header_parameter(),
            self.program_number,
            self.total_pages,
            self.content_update,
            self.display_instruction,
            self.display_format,
            self.information_type,
            self.raster_color,
            self.header_raster_color,
        )
        return Buffer(buffer)

    @classmethod
    def data_header_parameter(cls):
        return 0x32

    @classmethod
    def read(cls, stream: BitStream) -> Self:
        information_separator: int = stream.read("uint8")
        if information_separator != INFORMATION_SEPARATOR:
            cls._logger.warning(
                "Invalid information separator: %s", hex(information_separator)
            )
        data_header_parameter: int = stream.read("uint8")
        if data_header_parameter != cls.data_header_parameter():
            cls._logger.warning(
                "Invalid data header parameter: %s", hex(data_header_parameter)
            )

        program_number: int = stream.read("uint8")
        total_pages: int = stream.read("uint6")
        content_update: int = stream.read("uint2")
        display_instruction: int = stream.read("uint8")
        display_format: int = stream.read("uint4")
        information_type: int = stream.read("uint4")
        raster_color: int = stream.read("uint4")
        header_raster_color: int = stream.read("uint4")

        return cls(
            program_number=program_number,
            total_pages=total_pages,
            content_update=content_update,
            display_instruction=display_instruction,
            display_format=display_format,
            information_type=information_type,
            header_raster_color=header_raster_color,
            raster_color=raster_color,
        )


@dataclass
class PageDataHeaderB(DataHeaderBase):
    program_number: int
    content_update: int
    total_pages: int
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

    def to_buffer(self) -> Buffer:
        """Convert data group to binary buffer.

        Returns:
            Binary buffer containing packed data group
        """
        buffer = pack(
            f"""uint8, uint8,
                uint8, uint6, uint2, uint8, uint4, uint4,
                uint4, uint4, uint6, uint2, uint4, uint4, uint8, uint8, uint4, uint4,
                uint6, uint2, uint4, uint4, uint8, uint8, uint4, uint4,
                uint3, uint1, uint4, uint6, uint6, uint4, uint2, uint2, uint8
            """,
            INFORMATION_SEPARATOR,
            self.data_header_parameter(),
            self.program_number,
            self.total_pages,
            self.content_update,
            self.display_instruction,
            self.display_format,
            self.information_type,
            self.raster_color,
            self.header_raster_color,
            self.prefecture_identifier,
            self.undefined_0,
            self.map_zoom,
            self.map_type,
            self.map_position_x >> 4,
            self.map_position_y >> 4,
            self.map_position_y & 0x0F,
            self.map_position_x & 0x0F,
            self.information_deliver_time_hour >> 3,
            self.information_deliver_time_flag,
            self.content_type,
            self.information_deliver_time_minute,
            self.information_deliver_time_hour & 0x07,
            self.reference_link_number >> 8,
            self.link_type,
            self.link_layer,
            self.reference_link_number & 0xFF,
        )
        return Buffer(buffer)

    @classmethod
    def data_header_parameter(cls):
        return 0x32

    @classmethod
    def read(cls, stream: BitStream) -> Self:
        information_separator: int = stream.read("uint8")
        if information_separator != INFORMATION_SEPARATOR:
            cls._logger.warning(
                "Invalid information separator: %s", hex(information_separator)
            )
        data_header_parameter: int = stream.read("uint8")
        if data_header_parameter != cls.data_header_parameter():
            cls._logger.warning(
                "Invalid data header parameter: %s", hex(data_header_parameter)
            )

        program_number: int = stream.read("uint8")
        total_pages: int = stream.read("uint6")
        content_update: int = stream.read("uint2")
        display_instruction: int = stream.read("uint8")
        display_format: int = stream.read("uint4")
        information_type: int = stream.read("uint4")
        raster_color: int = stream.read("uint4")
        header_raster_color: int = stream.read("uint4")
        prefecture_identifier: int = stream.read("uint6")
        undefined_0: int = stream.read("uint2")
        map_zoom: int = stream.read("uint4")
        map_type: int = stream.read("uint4")
        map_position_x_high: int = stream.read("uint8")
        map_position_y_high: int = stream.read("uint8")
        map_position_y_low: int = stream.read("uint4")
        map_position_x_low: int = stream.read("uint4")
        map_position_x = map_position_x_high << 4 | map_position_x_low
        map_position_y = map_position_y_high << 4 | map_position_y_low
        information_deliver_time_hour_high: int = stream.read("uint3")
        information_deliver_time_flag: int = stream.read("uint1")
        content_type: int = stream.read("uint4")
        information_deliver_time_minute: int = stream.read("uint6")
        information_deliver_time_hour_low: int = stream.read("uint2")
        information_deliver_time_hour = (
            information_deliver_time_hour_high << 2 | information_deliver_time_hour_low
        )
        reference_link_number_high: int = stream.read("uint4")
        link_type: int = stream.read("uint2")
        link_layer: int = stream.read("uint2")
        reference_link_number_low: int = stream.read("uint8")
        reference_link_number = (
            reference_link_number_high << 8 | reference_link_number_low
        )

        return cls(
            program_number=program_number,
            total_pages=total_pages,
            content_update=content_update,
            display_instruction=display_instruction,
            display_format=display_format,
            information_type=information_type,
            header_raster_color=header_raster_color,
            raster_color=raster_color,
            prefecture_identifier=prefecture_identifier,
            undefined_0=undefined_0,
            map_zoom=map_zoom,
            map_type=map_type,
            map_position_x=map_position_x,
            map_position_y=map_position_y,
            information_deliver_time_hour=information_deliver_time_hour,
            information_deliver_time_flag=information_deliver_time_flag,
            content_type=content_type,
            information_deliver_time_minute=information_deliver_time_minute,
            reference_link_number=reference_link_number,
            link_type=link_type,
            link_layer=link_layer,
        )


@dataclass
class ContinueDataHeader(DataHeaderBase):

    def to_buffer(self) -> Buffer:
        buffer = pack(
            f"uint8, uint8",
            INFORMATION_SEPARATOR,
            self.data_header_parameter(),
        )
        return Buffer(buffer)

    @classmethod
    def data_header_parameter(cls):
        return 0x36

    @classmethod
    def read(cls, stream: BitStream) -> Self:
        information_separator: int = stream.read("uint8")
        if information_separator != INFORMATION_SEPARATOR:
            cls._logger.warning(
                "Invalid information separator: %s", hex(information_separator)
            )
        data_header_parameter: int = stream.read("uint8")
        if data_header_parameter != cls.data_header_parameter():
            cls._logger.warning(
                "Invalid data header parameter: %s", hex(data_header_parameter)
            )

        return cls()


@dataclass
class ProgramIndexDataHeader(DataHeaderBase):
    undefined_0: int
    index_control: int

    def to_buffer(self) -> Buffer:
        buffer = pack(
            f"""uint8, uint8,
                uint2, uint6,
            """,
            INFORMATION_SEPARATOR,
            self.data_header_parameter(),
            self.index_control,
            self.undefined_0,
        )
        return Buffer(buffer)

    @classmethod
    def data_header_parameter(cls):
        return 0x37

    @classmethod
    def read(cls, stream: BitStream) -> Self:
        information_separator: int = stream.read("uint8")
        if information_separator != INFORMATION_SEPARATOR:
            cls._logger.warning(
                "Invalid information separator: %s", hex(information_separator)
            )
        data_header_parameter: int = stream.read("uint8")
        if data_header_parameter != cls.data_header_parameter():
            cls._logger.warning(
                "Invalid data header parameter: %s", hex(data_header_parameter)
            )

        index_control: int = stream.read("uint2")
        undefined_0: int = stream.read("uint6")

        return cls(index_control=index_control, undefined_0=undefined_0)


@dataclass
class GenericDataUnit:
    data_unit_parameter: int
    data_unit_link_flag: int
    data: bytes

    _logger: ClassVar = getLogger(__name__)

    def to_buffer(self) -> Buffer:
        buffer = pack(
            f"uint8, uint8, uint7, uint1, uint8, bytes",
            DATA_UNIT_SEPARATOR,
            self.data_unit_parameter,
            len(self.data) >> 8,
            self.data_unit_link_flag,
            len(self.data) & 0xFF,
            self.data,
        )
        return Buffer(buffer)

    @classmethod
    def read(cls, stream: BitStream) -> Self:
        data_unit_separator: int = stream.read("uint8")
        if data_unit_separator != DATA_UNIT_SEPARATOR:
            cls._logger.warning(
                "Invalid data unit separator: %s", hex(data_unit_separator)
            )

        data_unit_parameter: int = stream.read("uint8")
        data_unit_size_high: int = stream.read("uint7")
        data_unik_link_flag: int = stream.read("uint1")
        data_unit_size_low: int = stream.read("uint8")
        data_unit_size = data_unit_size_high << 8 | data_unit_size_low
        data = stream.read(8 * data_unit_size).bytes

        return cls(
            data_unit_parameter=data_unit_parameter,
            data_unik_link_flag=data_unik_link_flag,
            data=data,
        )
