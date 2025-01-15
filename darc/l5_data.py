from abc import ABC, abstractmethod
from dataclasses import dataclass
from logging import getLogger
from typing import ClassVar, Final, Self, TypeAlias, Sequence

from bitstring import BitStream, Bits, pack

INFORMATION_SEPARATOR: Final[int] = 0x1E
DATA_UNIT_SEPARATOR: Final[int] = 0x1F

Buffer: TypeAlias = Bits


@dataclass
class DataHeaderBase(ABC):
    _logger: ClassVar = getLogger(__name__)

    @abstractmethod
    def to_buffer(self) -> Buffer:
        pass

    @classmethod
    def peek_data_header_parameter(cls, stream: BitStream) -> int:
        buffer = stream.peek("bytes2")
        return buffer[1]

    @classmethod
    @abstractmethod
    def data_header_parameter(cls) -> int:
        pass

    @classmethod
    @abstractmethod
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
                uint8, uint2, uint6, uint8, uint4, uint4
            """,
            INFORMATION_SEPARATOR,
            self.data_header_parameter(),
            self.program_number,
            self.content_change,
            self.total_pages,
            self.display_instruction,
            self.information_type,
            self.display_format,
        )
        return Buffer(buffer)

    @classmethod
    def data_header_parameter(cls):
        return 0x30

    @classmethod
    def read(cls, stream: BitStream) -> Self:
        information_separator: int = stream.read("uint8")
        if information_separator != INFORMATION_SEPARATOR:
            raise ValueError(
                "Invalid information separator: %s", hex(information_separator)
            )
        data_header_parameter: int = stream.read("uint8")
        if data_header_parameter != cls.data_header_parameter():
            raise ValueError(
                "Invalid data header parameter: %s", hex(data_header_parameter)
            )

        program_number: int = stream.read("uint8")
        content_change: int = stream.read("uint2")
        total_pages: int = stream.read("uint6")
        display_instruction: int = stream.read("uint8")
        information_type: int = stream.read("uint4")
        display_format: int = stream.read("uint4")

        return cls(
            program_number=program_number,
            content_change=content_change,
            total_pages=total_pages,
            display_instruction=display_instruction,
            information_type=information_type,
            display_format=display_format,
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
                uint8, uint2, uint6, uint8, uint4, uint4,
                uint2, uint6, uint4, uint4, uint8, uint8, uint4, uint4
            """,
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
        return Buffer(buffer)

    @classmethod
    def data_header_parameter(cls):
        return 0x31

    @classmethod
    def read(cls, stream: BitStream) -> Self:
        information_separator: int = stream.read("uint8")
        if information_separator != INFORMATION_SEPARATOR:
            raise ValueError(
                "Invalid information separator: %s", hex(information_separator)
            )
        data_header_parameter: int = stream.read("uint8")
        if data_header_parameter != cls.data_header_parameter():
            raise ValueError(
                "Invalid data header parameter: %s", hex(data_header_parameter)
            )

        program_number: int = stream.read("uint8")
        content_update: int = stream.read("uint2")
        total_pages: int = stream.read("uint6")
        display_instruction: int = stream.read("uint8")
        information_type: int = stream.read("uint4")
        display_format: int = stream.read("uint4")
        undefined_0: int = stream.read("uint2")
        prefecture_identifier: int = stream.read("uint6")
        map_type: int = stream.read("uint4")
        map_zoom: int = stream.read("uint4")
        map_position_x_high: int = stream.read("uint8")
        map_position_y_high: int = stream.read("uint8")
        map_position_x_low: int = stream.read("uint4")
        map_position_y_low: int = stream.read("uint4")
        map_position_x = map_position_x_high << 4 | map_position_x_low
        map_position_y = map_position_y_high << 4 | map_position_y_low

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
                uint8, uint2, uint6, uint8, uint4, uint4,
                uint4, uint4
            """,
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
        return Buffer(buffer)

    @classmethod
    def data_header_parameter(cls):
        return 0x32

    @classmethod
    def read(cls, stream: BitStream) -> Self:
        information_separator: int = stream.read("uint8")
        if information_separator != INFORMATION_SEPARATOR:
            raise ValueError(
                "Invalid information separator: %s", hex(information_separator)
            )
        data_header_parameter: int = stream.read("uint8")
        if data_header_parameter != cls.data_header_parameter():
            raise ValueError(
                "Invalid data header parameter: %s", hex(data_header_parameter)
            )

        program_number: int = stream.read("uint8")
        content_update: int = stream.read("uint2")
        total_pages: int = stream.read("uint6")
        display_instruction: int = stream.read("uint8")
        information_type: int = stream.read("uint4")
        display_format: int = stream.read("uint4")
        header_raster_color: int = stream.read("uint4")
        raster_color: int = stream.read("uint4")

        return cls(
            program_number=program_number,
            content_update=content_update,
            total_pages=total_pages,
            display_instruction=display_instruction,
            information_type=information_type,
            display_format=display_format,
            raster_color=raster_color,
            header_raster_color=header_raster_color,
        )


@dataclass
class PageDataHeaderB(DataHeaderBase):
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

    def to_buffer(self) -> Buffer:
        """Convert data group to binary buffer.

        Returns:
            Binary buffer containing packed data group
        """
        buffer = pack(
            f"""uint8, uint8,
                uint8, uint2, uint6, uint8, uint4, uint4,
                uint4, uint4, uint2, uint6, uint4, uint4, uint8, uint8, uint4, uint4,
                uint2, uint6, uint4, uint4, uint8, uint8, uint4, uint4,
                uint4, uint1, uint3, uint2, uint6, uint2, uint2, uint4, uint8
            """,
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
        return Buffer(buffer)

    @classmethod
    def data_header_parameter(cls):
        return 0x33

    @classmethod
    def read(cls, stream: BitStream) -> Self:
        information_separator: int = stream.read("uint8")
        if information_separator != INFORMATION_SEPARATOR:
            raise ValueError(
                "Invalid information separator: %s", hex(information_separator)
            )
        data_header_parameter: int = stream.read("uint8")
        if data_header_parameter != cls.data_header_parameter():
            raise ValueError(
                "Invalid data header parameter: %s", hex(data_header_parameter)
            )

        program_number: int = stream.read("uint8")
        content_update: int = stream.read("uint2")
        page_number: int = stream.read("uint6")
        display_instruction: int = stream.read("uint8")
        information_type: int = stream.read("uint4")
        display_format: int = stream.read("uint4")
        header_raster_color: int = stream.read("uint4")
        raster_color: int = stream.read("uint4")
        undefined_0: int = stream.read("uint2")
        prefecture_identifier: int = stream.read("uint6")
        map_type: int = stream.read("uint4")
        map_zoom: int = stream.read("uint4")
        map_position_x_high: int = stream.read("uint8")
        map_position_y_high: int = stream.read("uint8")
        map_position_x_low: int = stream.read("uint4")
        map_position_y_low: int = stream.read("uint4")
        map_position_x = map_position_x_high << 4 | map_position_x_low
        map_position_y = map_position_y_high << 4 | map_position_y_low
        content_type: int = stream.read("uint4")
        information_deliver_time_flag: int = stream.read("uint1")
        information_deliver_time_hour_high: int = stream.read("uint3")
        information_deliver_time_hour_low: int = stream.read("uint2")
        information_deliver_time_hour = (
            information_deliver_time_hour_high << 2 | information_deliver_time_hour_low
        )
        information_deliver_time_minute: int = stream.read("uint6")
        link_layer: int = stream.read("uint2")
        link_type: int = stream.read("uint2")
        reference_link_number_high: int = stream.read("uint4")
        reference_link_number_low: int = stream.read("uint8")
        reference_link_number = (
            reference_link_number_high << 8 | reference_link_number_low
        )

        return cls(
            program_number=program_number,
            content_update=content_update,
            page_number=page_number,
            display_instruction=display_instruction,
            information_type=information_type,
            display_format=display_format,
            raster_color=raster_color,
            header_raster_color=header_raster_color,
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
    display_instruction: int
    update: int
    undefined_0: int
    display_format: int
    program_common_macro_set: int
    program_common_macro_set_code: int

    def to_buffer(self) -> Buffer:
        """Convert data group to binary buffer.

        Returns:
            Binary buffer containing packed data group
        """
        buffer = pack(
            f"""uint8, uint8,
                uint8, uint1, uint3, uint4, uint8, uint8, uint8
            """,
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
        return Buffer(buffer)

    @classmethod
    def data_header_parameter(cls):
        return 0x34

    @classmethod
    def read(cls, stream: BitStream) -> Self:
        information_separator: int = stream.read("uint8")
        if information_separator != INFORMATION_SEPARATOR:
            raise ValueError(
                "Invalid information separator: %s", hex(information_separator)
            )
        data_header_parameter: int = stream.read("uint8")
        if data_header_parameter != cls.data_header_parameter():
            raise ValueError(
                "Invalid data header parameter: %s", hex(data_header_parameter)
            )

        display_instruction: int = stream.read("uint8")
        update: int = stream.read("uint1")
        undefined_0: int = stream.read("uint3")
        display_format: int = stream.read("uint4")
        program_common_macro_set: int = stream.read("uint8")
        program_common_macro_set_code_high: int = stream.read("uint8")
        program_common_macro_set_code_low: int = stream.read("uint8")
        program_common_macro_set_code = (
            program_common_macro_set_code_high << 8 | program_common_macro_set_code_low
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

    def to_buffer(self) -> Buffer:
        """Convert data group to binary buffer.

        Returns:
            Binary buffer containing packed data group
        """
        buffer = pack(
            f"""uint8, uint8,
                uint8, uint1, uint3, uint4, uint8, uint8, uint8,
                uint2, uint6, uint4, uint4, uint8, uint8, uint4, uint4, uint2, uint2, uint4, uint8
            """,
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
        return Buffer(buffer)

    @classmethod
    def data_header_parameter(cls):
        return 0x35

    @classmethod
    def read(cls, stream: BitStream) -> Self:
        information_separator: int = stream.read("uint8")
        if information_separator != INFORMATION_SEPARATOR:
            raise ValueError(
                "Invalid information separator: %s", hex(information_separator)
            )
        data_header_parameter: int = stream.read("uint8")
        if data_header_parameter != cls.data_header_parameter():
            raise ValueError(
                "Invalid data header parameter: %s", hex(data_header_parameter)
            )

        display_instruction: int = stream.read("uint8")
        update: int = stream.read("uint1")
        undefined_0: int = stream.read("uint3")
        display_format: int = stream.read("uint4")
        program_common_macro_set: int = stream.read("uint8")
        program_common_macro_set_code_high: int = stream.read("uint8")
        program_common_macro_set_code_low: int = stream.read("uint8")
        program_common_macro_set_code = (
            program_common_macro_set_code_high << 8 | program_common_macro_set_code_low
        )
        undefined_1: int = stream.read("uint2")
        prefecture_identifier: int = stream.read("uint6")
        map_type: int = stream.read("uint4")
        map_zoom: int = stream.read("uint4")
        map_position_x_high: int = stream.read("uint8")
        map_position_y_high: int = stream.read("uint8")
        map_position_x_low: int = stream.read("uint4")
        map_position_y_low: int = stream.read("uint4")
        map_position_x = map_position_x_high << 4 | map_position_x_low
        map_position_y = map_position_y_high << 4 | map_position_y_low
        link_layer: int = stream.read("uint2")
        link_type: int = stream.read("uint2")
        reference_link_number_high: int = stream.read("uint4")
        reference_link_number_low: int = stream.read("uint8")
        reference_link_number = (
            reference_link_number_high << 8 | reference_link_number_low
        )

        return cls(
            display_instruction=display_instruction,
            display_format=display_format,
            undefined_0=undefined_0,
            update=update,
            program_common_macro_set=program_common_macro_set,
            program_common_macro_set_code=program_common_macro_set_code,
            prefecture_identifier=prefecture_identifier,
            undefined_1=undefined_1,
            map_zoom=map_zoom,
            map_type=map_type,
            map_position_x=map_position_x,
            map_position_y=map_position_y,
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
            raise ValueError(
                "Invalid information separator: %s", hex(information_separator)
            )
        data_header_parameter: int = stream.read("uint8")
        if data_header_parameter != cls.data_header_parameter():
            raise ValueError(
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
                uint6, uint2,
            """,
            INFORMATION_SEPARATOR,
            self.data_header_parameter(),
            self.undefined_0,
            self.index_control,
        )
        return Buffer(buffer)

    @classmethod
    def data_header_parameter(cls):
        return 0x37

    @classmethod
    def read(cls, stream: BitStream) -> Self:
        information_separator: int = stream.read("uint8")
        if information_separator != INFORMATION_SEPARATOR:
            raise ValueError(
                "Invalid information separator: %s", hex(information_separator)
            )
        data_header_parameter: int = stream.read("uint8")
        if data_header_parameter != cls.data_header_parameter():
            raise ValueError(
                "Invalid data header parameter: %s", hex(data_header_parameter)
            )

        undefined_0: int = stream.read("uint6")
        index_control: int = stream.read("uint2")

        return cls(undefined_0=undefined_0, index_control=index_control)


def read_data_header(stream: BitStream):
    data_header_parameter = DataHeaderBase.peek_data_header_parameter(stream)
    for data_header_cls in (
        ProgramDataHeaderA,
        ProgramDataHeaderB,
        PageDataHeaderA,
        PageDataHeaderB,
        ProgramCommonMacroDataHeaderA,
        ProgramCommonMacroDataHeaderB,
        ContinueDataHeader,
        ProgramIndexDataHeader,
    ):
        if data_header_cls.data_header_parameter() == data_header_parameter:
            return data_header_cls.read(stream)

    return None


@dataclass
class GenericDataUnit:
    data_unit_parameter: int
    data_unit_link_flag: int
    data: bytes

    _logger: ClassVar = getLogger(__name__)

    def to_buffer(self) -> Buffer:
        buffer = pack(
            f"uint8, uint8, uint1, uint7, uint8, bytes",
            DATA_UNIT_SEPARATOR,
            self.data_unit_parameter,
            self.data_unit_link_flag,
            len(self.data) >> 8,
            len(self.data) & 0xFF,
            self.data,
        )
        return Buffer(buffer)

    @classmethod
    def read(cls, stream: BitStream) -> Self | bytes:
        data_unit_separator: int = stream.read("uint8")
        if data_unit_separator != DATA_UNIT_SEPARATOR:
            cls._logger.warning(
                "Invalid data unit separator: %s", hex(data_unit_separator)
            )
            stream.bytepos -= 1
            return stream.read("bytes")

        data_unit_parameter: int = stream.read("uint8")
        data_unit_link_flag: int = stream.read("uint1")
        data_unit_size_high: int = stream.read("uint7")
        data_unit_size_low: int = stream.read("uint8")
        data_unit_size = data_unit_size_high << 8 | data_unit_size_low
        data = stream.read(8 * data_unit_size).bytes

        return cls(
            data_unit_parameter=data_unit_parameter,
            data_unit_link_flag=data_unit_link_flag,
            data=data,
        )
