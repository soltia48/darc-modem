from bitstring import Bits, pack
from logging import getLogger
from typing import Self

from .bit_operations import reverse_bits
from .crc_16_darc import crc_16_darc
from .l3_data import L3DataPacketServiceIdentificationCode


class L4DataGroup1:
    """L4 Data Group Composition 1"""

    __logger = getLogger(__name__)

    service_id: L3DataPacketServiceIdentificationCode
    data_group_number: int
    data_group_link: int
    data_group_data: Bits
    end_of_data_group: int
    crc: int

    def to_buffer(self) -> Bits:
        """To buffer

        Returns:
            Bits: Buffer
        """
        start_of_headding = 0x01
        data_group_data = reverse_bits(self.data_group_data.bytes)
        data_group_size = len(data_group_data)
        total_size = 6 + data_group_size
        padding_length = 8 * (18 - total_size % 18)

        buffer = pack(
            f"uint8, uint1, uint15, bytes, pad{padding_length}, uint8, uint16",
            start_of_headding,
            self.data_group_link,
            data_group_size,
            data_group_data,
            self.end_of_data_group,
            self.crc,
        )
        buffer[0:8] = buffer[0:8][::-1]
        buffer[8:16] = buffer[8:16][::-1]
        buffer[16:24] = buffer[16:24][::-1]
        buffer[-24:-16] = buffer[-24:-16][::-1]
        return Bits(buffer)

    def is_crc_valid(self) -> bool:
        """Is CRC valid

        Returns:
            bool: True if CRC is valid, else False
        """
        data_buffer = self.to_buffer()[:-16]
        return crc_16_darc(data_buffer.bytes) == self.crc

    @classmethod
    def from_buffer(
        cls,
        service_id: L3DataPacketServiceIdentificationCode,
        data_group_number: int,
        buffer: Bits,
    ) -> Self:
        """Construct from buffer

        Args:
            service_id (DarcL3DataPacketServiceIdentificationCode): Service ID
            data_group_number (int): Data Group number
            buffer (Bits): Buffer

        Raises:
            ValueError: Invalid start_of_headding

        Returns:
            Self: DarcL4DataGroup1 instance
        """
        if len(buffer) < 48:
            raise ValueError("buffer length must be greater than or equal to 48.")

        start_of_headding = buffer[0:8][::-1].uint
        if start_of_headding != 0x01:
            L4DataGroup1.__logger.warning(
                f"start_of_headding is not 0x01. start_of_headding={hex(start_of_headding)}"
            )

        data_group_link = buffer[15:16].uint
        data_group_size = buffer[8:15][::-1].uint << 8 | buffer[16:24][::-1].uint
        data_group_data = Bits(
            reverse_bits(buffer[24 : 24 + 8 * data_group_size].bytes)
        )
        end_of_data_group = buffer[-24:-16][::-1].uint
        crc = buffer[-16:].uint

        return cls(
            service_id,
            data_group_number,
            data_group_link,
            data_group_data,
            end_of_data_group,
            crc,
        )


class L4DataGroup2:
    """L4 Data Group Composition 2"""

    def __init__(
        self,
        service_id: L3DataPacketServiceIdentificationCode,
        data_group_number: int,
        segments_data: Bits,
        crc: int | None,
    ) -> None:
        """Constructor

        Args:
            service_id (DarcL3DataPacketServiceIdentificationCode): Service ID
            data_group_number (int): Data Group number
            segments_data (Bits): Segments data
            crc (int | None): Recorded CRC value
        """
        # Metadata
        self.service_id = service_id
        self.data_group_number = data_group_number

        self.segments_data = segments_data
        self.crc = crc

    def has_crc(self) -> bool:
        """Has CRC value

        Returns:
            bool: True if has CRC value, else None
        """
        return 160 < len(self.segments_data)

    def to_buffer(self) -> Bits:
        """To buffer

        Returns:
            Bits: Buffer
        """
        segments_data = reverse_bits(self.segments_data.bytes)
        segments_data_size = len(segments_data)
        total_size = 2 + segments_data_size if self.has_crc() else segments_data_size
        padding_length = 8 * (20 - total_size % 20)

        if self.has_crc():
            buffer = pack(
                f"bytes, pad{padding_length}, uint16", segments_data, self.crc
            )
        else:
            buffer = pack(f"bytes, pad{padding_length}", segments_data)
        return Bits(buffer)

    def is_crc_valid(self) -> bool:
        """Is CRC valid

        Returns:
            bool: True if CRC is valid, else False
        """
        if not self.has_crc():
            return True

        data_buffer = self.to_buffer()[:-16]
        return crc_16_darc(data_buffer.bytes) == self.crc

    @classmethod
    def from_buffer(
        cls,
        service_id: L3DataPacketServiceIdentificationCode,
        data_group_number: int,
        buffer: Bits,
    ) -> Self:
        """Construct from buffer

        Args:
            service_id (DarcL3DataPacketServiceIdentificationCode): Service ID
            data_group_number (int): Data Group number
            buffer (Bits): Buffer

        Returns:
            Self: DarcL4DataGroup2 instance
        """

        crc: int | None = None

        if 160 < len(buffer):
            segments_data = Bits(reverse_bits(buffer[:-16].bytes))
            crc = buffer[-16:].uint
        else:
            segments_data = Bits(reverse_bits(buffer.bytes))

        return cls(service_id, data_group_number, segments_data, crc)
