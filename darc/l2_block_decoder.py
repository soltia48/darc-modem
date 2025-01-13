from logging import getLogger
from typing import Final, TypeAlias

from bitstring import BitStream

from .l2_data import L2BlockIdentificationCode, L2InformationBlock, L2ParityBlock
from .lfsr import lfsr

Bit: TypeAlias = int
BlockResult: TypeAlias = L2InformationBlock | L2ParityBlock | None

LFSR_POLYNOMIAL: Final[int] = 0x155
LFSR_INITIAL: Final[int] = 0x110
BIC_MASK: Final[int] = 0xFFFF
BLOCK_SIZE: Final[int] = 272
DEFAULT_BIC_ERROR_TOLERANCE: Final[int] = 2


class L2BlockDecoder:
    """Layer 2 Block Decoder for DARC protocol.

    This decoder processes incoming bits, detects Block Identification Codes (BIC),
    and reconstructs Layer 2 Information and Parity blocks. It includes descrambling
    functionality using an LFSR.

    Attributes:
        allowable_bic_errors (int): Maximum allowed Hamming distance for BIC detection
    """

    __logger = getLogger(__name__)

    def __init__(self) -> None:
        """Initialize the L2 Block Decoder with default settings."""
        self.__current_bic: int = 0x0000
        self.__data_buffer = BitStream()
        self.__lfsr = lfsr(LFSR_POLYNOMIAL, LFSR_INITIAL)
        self.allowable_bic_errors = DEFAULT_BIC_ERROR_TOLERANCE

    def __detected_bic(self) -> L2BlockIdentificationCode | None:
        """Detect Block Identification Code from current BIC buffer.

        Uses Hamming distance to find the closest matching BIC within
        the allowable error threshold.

        Returns:
            Detected BIC if within error tolerance, None otherwise
        """
        bics = [
            L2BlockIdentificationCode.BIC_1,
            L2BlockIdentificationCode.BIC_2,
            L2BlockIdentificationCode.BIC_3,
            L2BlockIdentificationCode.BIC_4,
        ]

        # Calculate Hamming distances
        hamming_distances = [(bic ^ self.__current_bic).bit_count() for bic in bics]
        min_distance = min(hamming_distances)
        min_index = hamming_distances.index(min_distance)

        return bics[min_index] if min_distance <= self.allowable_bic_errors else None

    def __is_information_block_detected(self) -> bool:
        """Check if current BIC indicates an Information Block.

        Returns:
            True if an Information Block is detected
        """
        detected_bic = self.__detected_bic()
        return detected_bic in (
            L2BlockIdentificationCode.BIC_1,
            L2BlockIdentificationCode.BIC_2,
            L2BlockIdentificationCode.BIC_3,
        )

    def __is_parity_block_detected(self) -> bool:
        """Check if current BIC indicates a Parity Block.

        Returns:
            True if a Parity Block is detected
        """
        return self.__detected_bic() == L2BlockIdentificationCode.BIC_4

    def reset(self) -> None:
        """Reset the decoder to its initial state.

        Clears the BIC buffer, data buffer, and reinitializes the LFSR.
        """
        self.__current_bic = 0x0000
        self.__data_buffer.clear()
        self.__lfsr = lfsr(LFSR_POLYNOMIAL, LFSR_INITIAL)

    def push_bit(self, bit: Bit) -> BlockResult:
        """Process a single input bit.

        This method handles:
        1. BIC detection
        2. Bit descrambling
        3. Block reconstruction

        Args:
            bit: Input bit (0 or 1)

        Returns:
            Decoded block if complete, None otherwise

        Raises:
            ValueError: If an unknown block type is detected
        """
        if not isinstance(bit, int) or bit not in (0, 1):
            # raise ValueError("Bit must be 0 or 1")
            self.__logger.warning("Bit must be 0 or 1")
            return None

        # BIC detection phase
        if self.__detected_bic() is None:
            self.__current_bic = ((self.__current_bic << 1) | bit) & BIC_MASK
            return None

        # Descrambling phase
        descrambled_bit = bit ^ next(self.__lfsr)
        self.__data_buffer += f"0b{descrambled_bit}"

        # Block completion check
        if len(self.__data_buffer) == BLOCK_SIZE:
            block_id = self.__detected_bic()
            self.__logger.debug(
                "Block data collected. block_id=%s data_buffer=%s",
                block_id.name if block_id else "UNKNOWN",
                self.__data_buffer,
            )

            # Block reconstruction
            try:
                if self.__is_information_block_detected():
                    block = L2InformationBlock.from_buffer(block_id, self.__data_buffer)
                elif self.__is_parity_block_detected():
                    block = L2ParityBlock.from_buffer(block_id, self.__data_buffer)
                else:
                    raise ValueError(f"Unknown Block type detected: {block_id}")

                self.__logger.debug("Block decoded. block_id=%s", block.block_id.name)
                self.reset()
                return block

            except Exception as e:
                self.__logger.error("Block decoding failed: %s", str(e))
                self.reset()
                raise

        return None
