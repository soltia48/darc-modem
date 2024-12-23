from bitstring import BitStream
from logging import getLogger

from .l2_data import L2BlockIdentificationCode, L2InformationBlock, L2ParityBlock
from .lfsr import lfsr


class L2BlockDecoder:
    """L2 Block Decoder"""

    __logger = getLogger(__name__)

    def __init__(self) -> None:
        """Constructor"""

        self.__current_bic = 0x0000
        self.__data_buffer = BitStream()
        self.__lfsr = lfsr(0x155, 0x110)

        self.allowable_bic_errors = 2

    def __detected_bic(self) -> L2BlockIdentificationCode | None:
        """Get detected Block Identification Code

        Returns:
            L2BlockIdentificationCode | None: L2BlockIdentificationCode if BIC is detected, else None
        """

        bics = [
            L2BlockIdentificationCode.BIC_1,
            L2BlockIdentificationCode.BIC_2,
            L2BlockIdentificationCode.BIC_3,
            L2BlockIdentificationCode.BIC_4,
        ]
        bic_hamming_distances = list(
            map(lambda x: (x ^ self.__current_bic).bit_count(), bics)
        )
        minimum_index = bic_hamming_distances.index(min(bic_hamming_distances))
        return (
            bics[minimum_index]
            if bic_hamming_distances[minimum_index] <= self.allowable_bic_errors
            else None
        )

    def __is_information_block_detected(self) -> bool:
        """Is Information Block detected

        Returns:
            bool: True if Information Block detected, else False
        """

        detected_bic = self.__detected_bic()
        return (
            detected_bic == L2BlockIdentificationCode.BIC_1
            or detected_bic == L2BlockIdentificationCode.BIC_2
            or detected_bic == L2BlockIdentificationCode.BIC_3
        )

    def __is_parity_block_detected(self) -> bool:
        """Is Parity Block detected

        Returns:
            bool: True if Parity Block detected, else False
        """

        detected_bic = self.__detected_bic()
        return detected_bic == L2BlockIdentificationCode.BIC_4

    def reset(self) -> None:
        """Reset the decoder"""

        self.__current_bic = 0x0000
        self.__data_buffer.clear()
        self.__lfsr = lfsr(0x155, 0x110)

    def push_bit(self, bit: int) -> L2InformationBlock | L2ParityBlock | None:
        """Push a bit

        Args:
            bit (int): 0 or 1

        Returns:
            L2InformationBlock | L2ParityBlock | None: L2BlockType if any Block detected, else None
        """

        if self.__detected_bic() is None:
            self.__current_bic = ((self.__current_bic << 1) | bit) & 0xFFFF
            return

        # Descramble
        bit ^= next(self.__lfsr)
        self.__data_buffer += "0b0" if bit == 0 else "0b1"

        # If bits have been collected
        if len(self.__data_buffer) == 272:
            block_id = self.__detected_bic()
            self.__logger.debug(
                f"272 bits collected. block_id={block_id.name} data_buffer={self.__data_buffer}"
            )
            if self.__is_information_block_detected():
                block = L2InformationBlock.from_buffer(block_id, self.__data_buffer)
            elif self.__is_parity_block_detected():
                block = L2ParityBlock.from_buffer(block_id, self.__data_buffer)
            else:
                raise ValueError("Unknown Block detected.")
            self.__logger.debug(f"A block decoded. block_id={block.block_id.name}")

            # Must call it when decode
            self.reset()

            return block
