from dataclasses import dataclass
from enum import IntEnum
from functools import cached_property
from typing import Self, Final

from bitstring import Bits

PACKET_SIZE: Final[int] = 176
SERVICE_ID_SIZE: Final[int] = 4
DECODE_FLAG_SIZE: Final[int] = 1
EOI_FLAG_SIZE: Final[int] = 1
UPDATE_FLAG_SIZE: Final[int] = 2
HEADER_SIZE: Final[int] = (
    SERVICE_ID_SIZE + DECODE_FLAG_SIZE + EOI_FLAG_SIZE + UPDATE_FLAG_SIZE
)

COMP1_GROUP_SIZE: Final[int] = 14
COMP1_PACKET_SIZE: Final[int] = 10
COMP2_GROUP_SIZE: Final[int] = 4
COMP2_PACKET_SIZE: Final[int] = 4


class L3DataPacketServiceIdentificationCode(IntEnum):
    """Layer 3 Data Packet Service Identification Codes.

    Defines the various transmission modes and service types for L3 packets.
    Values must be between 0x0 and 0xF.
    """

    UNDEFINED_0 = 0x0
    TRANSMISSION_1_MODE = 0x1
    TRANSMISSION_2_MODE = 0x2
    TRANSMISSION_3_MODE = 0x3
    TRANSMISSION_4_MODE = 0x4
    TRANSMISSION_5_MODE = 0x5
    TRANSMISSION_6_MODE = 0x6
    TRANSMISSION_7_MODE = 0x7
    TRANSMISSION_8_MODE = 0x8
    TRANSMISSION_9_MODE = 0x9
    UNDEFINED_A = 0xA
    UNDEFINED_B = 0xB
    UNDEFINED_C = 0xC
    ADDITIONAL_INFORMATION = 0xD
    AUXILIARY_SIGNAL = 0xE
    OPERATIONAL_SIGNAL = 0xF

    @classmethod
    def is_valid(cls, value: int) -> bool:
        """Check if a value is a valid service identification code.

        Args:
            value: Value to check

        Returns:
            True if value is valid
        """
        return 0x0 <= value <= 0xF


@dataclass(frozen=True)
class L3DataPacket:
    """Layer 3 Data Packet.

    Contains service identification and data group information.
    Supports two different compositions based on service ID.

    Attributes:
        service_id: Service identification code
        decode_id_flag: Decode identification flag (0 or 1)
        end_of_information_flag: End of information flag (0 or 1)
        update_flag: Update flag (0-3)
        data_group_number: Data group number
        data_packet_number: Data packet number within group
        data_block: Actual data payload
    """

    service_id: L3DataPacketServiceIdentificationCode
    decode_id_flag: int
    end_of_information_flag: int
    update_flag: int
    data_group_number: int
    data_packet_number: int
    data_block: Bits

    def __post_init__(self) -> None:
        """Validate packet data after initialization."""
        if not isinstance(self.service_id, L3DataPacketServiceIdentificationCode):
            raise ValueError("Invalid service identification code")
        if not 0 <= self.decode_id_flag <= 1:
            raise ValueError("Decode ID flag must be 0 or 1")
        if not 0 <= self.end_of_information_flag <= 1:
            raise ValueError("End of information flag must be 0 or 1")
        if not 0 <= self.update_flag <= 3:
            raise ValueError("Update flag must be between 0 and 3")

        # Validate group and packet numbers based on composition
        if (
            self.service_id
            == L3DataPacketServiceIdentificationCode.ADDITIONAL_INFORMATION
        ):
            if not 0 <= self.data_group_number < (1 << COMP2_GROUP_SIZE):
                raise ValueError(f"Group number exceeds {COMP2_GROUP_SIZE} bits")
            if not 0 <= self.data_packet_number < (1 << COMP2_PACKET_SIZE):
                raise ValueError(f"Packet number exceeds {COMP2_PACKET_SIZE} bits")
        else:
            if not 0 <= self.data_group_number < (1 << COMP1_GROUP_SIZE):
                raise ValueError(f"Group number exceeds {COMP1_GROUP_SIZE} bits")
            if not 0 <= self.data_packet_number < (1 << COMP1_PACKET_SIZE):
                raise ValueError(f"Packet number exceeds {COMP1_PACKET_SIZE} bits")

    @cached_property
    def is_composition_2(self) -> bool:
        """Check if packet uses composition 2 format.

        Returns:
            True if packet uses composition 2
        """
        return (
            self.service_id
            == L3DataPacketServiceIdentificationCode.ADDITIONAL_INFORMATION
        )

    @classmethod
    def from_buffer(cls, buffer: Bits) -> Self:
        """Create packet from binary buffer.

        Args:
            buffer: Binary data buffer

        Returns:
            New packet instance

        Raises:
            ValueError: If buffer length or content is invalid
        """
        if isinstance(buffer, bytes):
            buffer = Bits(buffer)

        if len(buffer) != PACKET_SIZE:
            raise ValueError(f"Buffer length must be {PACKET_SIZE} bits")

        # Extract header fields (reverse bits as needed)
        service_id = L3DataPacketServiceIdentificationCode(buffer[0:4][::-1].uint)
        decode_id_flag: int = buffer[4:5].uint
        end_of_information_flag: int = buffer[5:6].uint
        update_flag: int = buffer[6:8][::-1].uint

        # Handle different compositions
        if service_id == L3DataPacketServiceIdentificationCode.ADDITIONAL_INFORMATION:
            # Composition 2
            data_group_number: int = buffer[8:12][::-1].uint
            data_packet_number: int = buffer[12:16][::-1].uint
            data_block = buffer[16:PACKET_SIZE]
        else:
            # Composition 1
            data_group_number: int = buffer[8:22][::-1].uint
            data_packet_number: int = buffer[22:32][::-1].uint
            data_block = buffer[32:PACKET_SIZE]

        return cls(
            service_id=service_id,
            decode_id_flag=decode_id_flag,
            end_of_information_flag=end_of_information_flag,
            update_flag=update_flag,
            data_group_number=data_group_number,
            data_packet_number=data_packet_number,
            data_block=data_block,
        )
