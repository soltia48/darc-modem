from bitstring import Bits, pack
from dataclasses import dataclass
from enum import IntEnum
from typing import Self

from .crc_14_darc import crc_14_darc
from .crc_82_darc import correct_error_dscc_272_190


class L2BlockIdentificationCode(IntEnum):
    UNDEFINED = 0x0000
    BIC_1 = 0x135E
    BIC_2 = 0x74A6
    BIC_3 = 0xA791
    BIC_4 = 0xC875


@dataclass
class L2InformationBlock:
    """DARC L2 Information Block"""

    block_id: L2BlockIdentificationCode
    data_packet: Bits
    crc: int

    def is_crc_valid(self) -> bool:
        """Is CRC valid

        Returns:
            bool: True if CRC is valid, else False
        """
        return crc_14_darc(self.data_packet.bytes) == self.crc

    def to_buffer(self) -> Bits:
        """To buffer

        Returns:
            Bits: Buffer
        """
        return pack("bits176, uint14", self.data_packet, self.crc)

    @classmethod
    def from_buffer(cls, block_id: L2BlockIdentificationCode, buffer: Bits) -> Self:
        """Construct from buffer

        Args:
            block_id (DarcL2BlockIdentificationCode): Block ID
            buffer (Bits): Buffer

        Raises:
            ValueError: Invalid buffer length

        Returns:
            Self: DarcL2InformationBlock instance
        """
        if len(buffer) != 190 and len(buffer) != 272:
            raise ValueError("buffer length must be 190 or 272.")

        if len(buffer) == 272:
            # Correct error
            error_corrected_blocks = correct_error_dscc_272_190(buffer)
            if error_corrected_blocks is not None:
                buffer = error_corrected_blocks

        data_packet = buffer[0:176]
        crc = buffer[176:190].uint

        return cls(block_id, data_packet, crc)


@dataclass
class L2ParityBlock:
    """DARC L2 Parity Block"""

    block_id: L2BlockIdentificationCode
    vertical_parity: Bits

    def to_buffer(self) -> Bits:
        """To buffer

        Returns:
            Bits: Buffer
        """
        return self.vertical_parity

    @classmethod
    def from_buffer(cls, block_id: L2BlockIdentificationCode, buffer: Bits) -> Self:
        """Construct from buffer

        Args:
            block_id (DarcL2BlockIdentificationCode): Block ID
            buffer (Bits): Buffer

        Raises:
            ValueError: Invalid buffer length

        Returns:
            Self: DarcL2ParityBlock instance
        """
        if len(buffer) != 190 and len(buffer) != 272:
            raise ValueError("buffer length must be 190 or 272.")

        if len(buffer) == 272:
            # Correct error
            error_corrected_blocks = correct_error_dscc_272_190(buffer)
            if error_corrected_blocks is not None:
                buffer = error_corrected_blocks

        vertical_parity = buffer[0:190]

        return cls(block_id, vertical_parity)


@dataclass
class L2Frame:
    """DARC L2 Frame"""

    blocks: list[L2InformationBlock]

    @staticmethod
    def __correct_error_dscc_272_190(buffer: Bits) -> Bits:
        """Correct error with Difference Set Cyclic Codes (272,190)

        Args:
            buffer (Bits): Buffer

        Returns:
            Bits: Error corrected buffer. However, return original If cannot correct error
        """
        error_corrected_buffer = correct_error_dscc_272_190(buffer)
        if error_corrected_buffer is not None:
            buffer = error_corrected_buffer
        return buffer

    @classmethod
    def from_block_buffer(
        cls,
        block_buffer: list[L2InformationBlock | L2ParityBlock],
    ) -> Self:
        """Construct from Block buffer

        Args:
            block_buffer (list[DarcL2InformationBlock  |  DarcL2ParityBlock]): Block buffer

        Raises:
            ValueError: Invalid block_buffer length

        Returns:
            Self: DarcL2Frame instance
        """
        if len(block_buffer) != 272:
            raise ValueError("block_buffer length must be 272.")

        # Copy information blocks
        blocks = list(filter(lambda x: isinstance(x, L2InformationBlock), block_buffer))
        # Copy parity blocks
        blocks.extend(filter(lambda x: isinstance(x, L2ParityBlock), block_buffer))

        # Create blocks 2D buffer
        blocks_2d_buffer = list(map(lambda x: Bits(x.to_buffer()), blocks))
        # Rotate left
        left_rotated_blocks_2d_buffer: list[Bits] = map(
            lambda x: Bits(x), list(zip(*blocks_2d_buffer))[::-1]
        )
        # Correct error with vertical parity
        left_rotated_blocks_2d_buffer = map(
            L2Frame.__correct_error_dscc_272_190, left_rotated_blocks_2d_buffer
        )
        # Rotate right
        blocks_2d_buffer = list(
            map(
                lambda x: Bits(x),
                zip(*list(left_rotated_blocks_2d_buffer)[::-1]),
            )
        )

        # Create Information Blocks from error corrected buffers
        error_corrected_blocks: list[L2InformationBlock] = []
        for i in range(190):
            error_corrected_blocks.append(
                L2InformationBlock.from_buffer(blocks[i].block_id, blocks_2d_buffer[i])
            )

        return L2Frame(error_corrected_blocks)
