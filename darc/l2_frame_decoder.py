from logging import getLogger
from typing import Final, TypeAlias

from .l2_data import (
    L2BlockIdentificationCode as BIC,
    L2InformationBlock,
    L2ParityBlock,
    L2Frame,
)

Block: TypeAlias = L2InformationBlock | L2ParityBlock

FRAME_SIZE: Final[int] = 272
BIC1_START: Final[int] = 1
BIC1_END: Final[int] = 13
BIC2_START: Final[int] = 137
BIC2_END: Final[int] = 149


class L2FrameDecoder:
    """Layer 2 Frame Decoder.

    Decodes DARC Layer 2 frames by assembling blocks and validating their sequence.
    Implements complex block identification code (BIC) validation rules.
    """

    def __init__(self) -> None:
        """Initialize a new frame decoder instance."""
        self._logger = getLogger(__name__)
        self._block_buffer: list[Block] = []

    def reset(self) -> None:
        """Reset the decoder state."""
        self._block_buffer.clear()

    def _get_expected_bic(self, position: int) -> BIC:
        """Get expected BIC for a given position.

        Args:
            position: Current position in sequence (1-based)

        Returns:
            Expected BIC for the position
        """
        # BIC1 range
        if BIC1_START <= position <= BIC1_END:
            return BIC.BIC_1

        # BIC2 range
        if BIC2_START <= position <= BIC2_END:
            return BIC.BIC_2

        # Middle section (14-136)
        if 14 <= position <= 136:
            if position % 3 == 1:
                return BIC.BIC_4
            return BIC.BIC_3

        # End section (150-272)
        if 150 <= position <= FRAME_SIZE:
            if position % 3 == 2:
                return BIC.BIC_4
            return BIC.BIC_3

        self._logger.warning("Invalid position: %d", position)
        return BIC.UNDEFINED

    def _validate_sequence(self, position: int, block: Block) -> bool:
        """Validate block sequence based on position and block type.

        Args:
            position: Current position in sequence (1-based)
            block: Block to validate

        Returns:
            True if sequence is valid, False otherwise
        """
        expected_bic = self._get_expected_bic(position)

        if expected_bic == BIC.UNDEFINED:
            self._logger.error(
                "Invalid position %d for block with BIC %s",
                position,
                block.block_id.name,
            )
            return False

        if block.block_id != expected_bic:
            self._logger.debug(
                "BIC mismatch at position %d: expected %s, got %s",
                position,
                expected_bic.name,
                block.block_id.name,
            )
            return False

        return True

    def push_block(self, block: Block) -> L2Frame | None:
        """Process a new block and attempt to construct a frame.

        Args:
            block: New block to process

        Returns:
            Completed frame if available, None otherwise
        """
        current_position = len(self._block_buffer) + 1

        # Validate sequence
        if not self._validate_sequence(current_position, block):
            self._logger.debug(
                "Invalid sequence detected at position %d with BIC %s",
                current_position,
                block.block_id.name,
            )
            self.reset()
            return None

        # Add block to buffer
        self._block_buffer.append(block)

        # Check if frame is complete
        if current_position == FRAME_SIZE:
            self._logger.debug(
                "Frame assembly complete: %d blocks collected", FRAME_SIZE
            )
            try:
                frame = L2Frame.from_block_buffer(self._block_buffer)
                return frame
            finally:
                self.reset()

        return None

    def get_buffer_size(self) -> int:
        """Get current buffer size.

        Returns:
            Number of blocks in buffer
        """
        return len(self._block_buffer)
