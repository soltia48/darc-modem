from dataclasses import dataclass
from logging import getLogger
from typing import Self, Final, TypeAlias, ClassVar

from bitstring import Bits, pack

from .bit_operations import reverse_bits
from .crc_16_darc import crc_16_darc
from .l3_data import L3DataPacketServiceIdentificationCode as ServiceID

Buffer: TypeAlias = Bits
ServiceIdentifier: TypeAlias = ServiceID
GroupNumber: TypeAlias = int

START_OF_HEADING: Final[int] = 0x01
MIN_BUFFER_SIZE: Final[int] = 48
COMP2_CRC_THRESHOLD: Final[int] = 160
BLOCK_SIZE: Final[int] = 18
COMP2_BLOCK_SIZE: Final[int] = 20
BYTE_SIZE: Final[int] = 8
CRC_SIZE: Final[int] = 16


@dataclass
class L4DataGroup1:
    """Layer 4 Data Group Composition 1.

    Contains data group with header and CRC validation.

    Attributes:
        service_id: Service identification
        data_group_number: Group number
        data_group_link: Link indicator
        data_group_data: Actual payload data
        end_of_data_group: End marker
        crc: CRC value for validation
    """

    _logger: ClassVar = getLogger(__name__)

    service_id: ServiceIdentifier
    data_group_number: GroupNumber
    data_group_link: int
    data_group_data: Buffer
    end_of_data_group: int
    crc: int

    def __post_init__(self) -> None:
        """Validate data group after initialization."""
        if not 0 <= self.data_group_link <= 1:
            raise ValueError("Data group link must be 0 or 1")
        if not 0 <= self.end_of_data_group <= 255:
            raise ValueError("End of data group must be 0-255")
        if not 0 <= self.crc <= 0xFFFF:
            raise ValueError("CRC must be 16-bit value")

    def to_buffer(self) -> Buffer:
        """Convert data group to binary buffer.

        Returns:
            Binary buffer containing packed data group
        """
        data = reverse_bits(self.data_group_data.bytes)
        data_size = len(data)
        total_size = 6 + data_size
        padding_bits = BYTE_SIZE * (BLOCK_SIZE - total_size % BLOCK_SIZE)

        # Create initial buffer
        buffer = pack(
            f"uint8, uint1, uint15, bytes, pad{padding_bits}, uint8, uint16",
            START_OF_HEADING,
            self.data_group_link,
            data_size,
            data,
            self.end_of_data_group,
            self.crc,
        )

        # Reverse required bit segments
        for start in range(0, 24, 8):
            buffer[start : start + 8] = buffer[start : start + 8][::-1]
        buffer[-24:-16] = buffer[-24:-16][::-1]

        return Buffer(buffer)

    def is_crc_valid(self) -> bool:
        """Check if CRC is valid for this data group.

        Returns:
            True if CRC matches calculated value
        """
        data_buffer = self.to_buffer()[:-CRC_SIZE]
        return crc_16_darc(data_buffer.bytes) == self.crc

    @classmethod
    def from_buffer(
        cls,
        service_id: ServiceIdentifier,
        data_group_number: GroupNumber,
        buffer: Buffer,
    ) -> Self:
        """Create data group from binary buffer.

        Args:
            service_id: Service identification
            data_group_number: Group number
            buffer: Binary data buffer

        Returns:
            New data group instance

        Raises:
            ValueError: If buffer is too small or format is invalid
        """
        if len(buffer) < MIN_BUFFER_SIZE:
            raise ValueError(f"Buffer length must be >= {MIN_BUFFER_SIZE}")

        # Extract header fields (with bit reversal)
        start_of_heading = buffer[0:8][::-1].uint
        if start_of_heading != START_OF_HEADING:
            cls._logger.warning("Invalid start of heading: %s", hex(start_of_heading))

        data_group_link = buffer[15:16].uint
        data_size = buffer[8:15][::-1].uint << 8 | buffer[16:24][::-1].uint

        # Extract data and validation fields
        data_start = 24
        data_end = data_start + 8 * data_size
        data = Buffer(reverse_bits(buffer[data_start:data_end].bytes))
        end_mark = buffer[-24:-16][::-1].uint
        crc = buffer[-16:].uint

        return cls(
            service_id=service_id,
            data_group_number=data_group_number,
            data_group_link=data_group_link,
            data_group_data=data,
            end_of_data_group=end_mark,
            crc=crc,
        )


@dataclass
class L4DataGroup2:
    """Layer 4 Data Group Composition 2.

    Contains segments data with optional CRC validation.

    Attributes:
        service_id: Service identification
        data_group_number: Group number
        segments_data: Segment payload data
        crc: Optional CRC value
    """

    service_id: ServiceIdentifier
    data_group_number: GroupNumber
    segments_data: Buffer
    crc: int | None = None

    def has_crc(self) -> bool:
        """Check if group has CRC value.

        Returns:
            True if CRC is present
        """
        return len(self.segments_data) > COMP2_CRC_THRESHOLD

    def to_buffer(self) -> Buffer:
        """Convert data group to binary buffer.

        Returns:
            Binary buffer containing packed data group
        """
        data = reverse_bits(self.segments_data.bytes)
        data_size = len(data)
        total_size = data_size + (2 if self.has_crc() else 0)
        padding_bits = BYTE_SIZE * (COMP2_BLOCK_SIZE - total_size % COMP2_BLOCK_SIZE)

        # Create buffer with or without CRC
        if self.has_crc() and self.crc is not None:
            return pack(f"bytes, pad{padding_bits}, uint16", data, self.crc)
        return pack(f"bytes, pad{padding_bits}", data)

    def is_crc_valid(self) -> bool:
        """Check if CRC is valid for this data group.

        Returns:
            True if CRC matches or no CRC present
        """
        if not self.has_crc() or self.crc is None:
            return True

        data_buffer = self.to_buffer()[:-CRC_SIZE]
        return crc_16_darc(data_buffer.bytes) == self.crc

    @classmethod
    def from_buffer(
        cls,
        service_id: ServiceIdentifier,
        data_group_number: GroupNumber,
        buffer: Buffer,
    ) -> Self:
        """Create data group from binary buffer.

        Args:
            service_id: Service identification
            data_group_number: Group number
            buffer: Binary data buffer

        Returns:
            New data group instance
        """
        if len(buffer) > COMP2_CRC_THRESHOLD:
            data = Buffer(reverse_bits(buffer[:-CRC_SIZE].bytes))
            crc = buffer[-CRC_SIZE:].uint
        else:
            data = Buffer(reverse_bits(buffer.bytes))
            crc = None

        return cls(
            service_id=service_id,
            data_group_number=data_group_number,
            segments_data=data,
            crc=crc,
        )
