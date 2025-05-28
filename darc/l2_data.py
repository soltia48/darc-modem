from collections.abc import Sequence
from dataclasses import dataclass, field
from enum import IntEnum
from typing import Self, Final, TypeAlias

from bitstring import Bits, pack

from .crc_14_darc import crc_14_darc
from .crc_82_darc import correct_error_dscc_272_190

Block: TypeAlias = "L2InformationBlock | L2ParityBlock"

PACKET_SIZE: Final[int] = 176
CRC_SIZE: Final[int] = 14
BLOCK_SIZE: Final[int] = 190
FRAME_SIZE: Final[int] = 272
PARITY_SIZE: Final[int] = BLOCK_SIZE


class L2BlockIdentificationCode(IntEnum):
    """Layer 2 Block Identification Codes.

    These codes are used to identify different types of blocks in the L2 frame.
    """

    UNDEFINED = 0x0000
    BIC_1 = 0x135E
    BIC_2 = 0x74A6
    BIC_3 = 0xA791
    BIC_4 = 0xC875


@dataclass(frozen=True)
class L2InformationBlock:
    """Layer 2 Information Block.

    Contains data packet and error detection information.

    Attributes:
        block_id: Block identification code
        data_packet: Actual data payload
        crc: Cyclic redundancy check value
    """
    block_id: L2BlockIdentificationCode
    data_packet: Bits
    crc: int

    def __post_init__(self) -> None:
        """Validate block after initialization."""
        if len(self.data_packet) != PACKET_SIZE:
            raise ValueError(f"Data packet must be {PACKET_SIZE} bits")
        if not 0 <= self.crc < (1 << CRC_SIZE):
            raise ValueError(f"CRC must be a {CRC_SIZE}-bit value")

    def is_crc_valid(self) -> bool:
        """Check if the CRC is valid for this block.

        Returns:
            True if CRC matches calculated value
        """
        return crc_14_darc(self.data_packet.bytes) == self.crc

    def to_buffer(self) -> Bits:
        """Convert block to buffer format.

        Returns:
            Binary buffer containing packed block data
        """
        return pack("bits176, uint14", self.data_packet, self.crc)

    @classmethod
    def from_buffer(cls, block_id: L2BlockIdentificationCode, buffer: Bits) -> Self:
        """Create block from binary buffer.

        Args:
            block_id: Block identification code
            buffer: Binary data buffer

        Returns:
            New information block instance

        Raises:
            ValueError: If buffer length is invalid
        """
        if len(buffer) not in (BLOCK_SIZE, FRAME_SIZE):
            raise ValueError(f"Bits length must be {BLOCK_SIZE} or {FRAME_SIZE}")

        # Attempt error correction if needed
        if len(buffer) == FRAME_SIZE:
            corrected = correct_error_dscc_272_190(buffer, raise_error=False)
            if corrected is not None:
                buffer = corrected

        return cls(
            block_id=block_id,
            data_packet=buffer[0:PACKET_SIZE],
            crc=buffer[PACKET_SIZE:BLOCK_SIZE].uint,
        )


@dataclass(frozen=True)
class L2ParityBlock:
    """Layer 2 Parity Block.

    Contains vertical parity information for error correction.

    Attributes:
        block_id: Block identification code
        vertical_parity: Vertical parity bits
    """

    block_id: L2BlockIdentificationCode
    vertical_parity: Bits

    def __post_init__(self) -> None:
        """Validate block after initialization."""
        if len(self.vertical_parity) != PARITY_SIZE:
            raise ValueError(f"Vertical parity must be {PARITY_SIZE} bits")

    def to_buffer(self) -> Bits:
        """Convert block to buffer format.

        Returns:
            Binary buffer containing parity data
        """
        return self.vertical_parity

    @classmethod
    def from_buffer(cls, block_id: L2BlockIdentificationCode, buffer: Bits) -> Self:
        """Create block from binary buffer.

        Args:
            block_id: Block identification code
            buffer: Binary data buffer

        Returns:
            New parity block instance

        Raises:
            ValueError: If buffer length is invalid
        """
        if len(buffer) not in (BLOCK_SIZE, FRAME_SIZE):
            raise ValueError(f"Bits length must be {BLOCK_SIZE} or {FRAME_SIZE}")

        # Attempt error correction if needed
        if len(buffer) == FRAME_SIZE:
            corrected = correct_error_dscc_272_190(buffer, raise_error=False)
            if corrected is not None:
                buffer = corrected

        return cls(block_id, buffer[0:PARITY_SIZE])


@dataclass
class L2Frame:
    """Layer 2 Frame.

    Contains multiple information blocks with error correction capability.

    Attributes:
        blocks: List of information blocks in the frame
    """

    blocks: list[L2InformationBlock] = field(default_factory=list)

    @classmethod
    def from_block_buffer(cls, block_buffer: Sequence[Block]) -> Self:
        """Create frame from sequence of blocks.

        Args:
            block_buffer: Sequence of information and parity blocks

        Returns:
            New frame instance

        Raises:
            ValueError: If buffer length is invalid
        """
        if len(block_buffer) != FRAME_SIZE:
            raise ValueError(f"Block buffer length must be {FRAME_SIZE}")

        # Extract blocks by type
        info_blocks = [b for b in block_buffer if isinstance(b, L2InformationBlock)]
        parity_blocks = [b for b in block_buffer if isinstance(b, L2ParityBlock)]
        blocks = [*info_blocks, *parity_blocks]

        # Convert to 2D buffer and apply error correction
        buffers = [Bits(block.to_buffer()) for block in blocks]
        rotated = list(zip(*buffers))[::-1]
        corrected = map(correct_error_dscc_272_190, map(Bits, rotated))
        restored = list(zip(*list(corrected)[::-1]))

        # Create corrected information blocks
        return cls(
            [
                L2InformationBlock.from_buffer(blocks[i].block_id, Bits(restored[i]))
                for i in range(BLOCK_SIZE)
            ]
        )
