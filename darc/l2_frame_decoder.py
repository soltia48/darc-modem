from logging import getLogger

from .l2_data import (
    L2BlockIdentificationCode,
    L2InformationBlock,
    L2ParityBlock,
    L2Frame,
)


class L2FrameDecoder:
    """L2 Frame Decoder"""

    __logger = getLogger(__name__)

    def __init__(self) -> None:
        """Constructor"""

        self.__block_buffer: list[L2InformationBlock | L2ParityBlock] = []

    def reset(self) -> None:
        """Reset"""

        self.__block_buffer.clear()

    def push_block(self, block: L2InformationBlock | L2ParityBlock) -> L2Frame | None:
        """Push a Block

        Args:
            block (L2InformationBlock | L2ParityBlock): Block

        Returns:
            L2Frame | None: L2Frame if frame detected, else None
        """

        current_block_number = len(self.__block_buffer) + 1

        # BIC1
        if (
            1 <= current_block_number and current_block_number <= 13
        ) and block.block_id != L2BlockIdentificationCode.BIC_1:
            self.__logger.debug("Invalid sequence detected.")
            self.__block_buffer.clear()
            return
        # BIC2
        if (
            137 <= current_block_number and current_block_number <= 149
        ) and block.block_id != L2BlockIdentificationCode.BIC_2:
            self.__logger.debug("Invalid sequence detected.")
            self.__block_buffer.clear()
            return
        # BIC3
        if (
            (14 <= current_block_number and current_block_number <= 136)
            and (current_block_number % 3 == 0 or current_block_number % 3 == 2)
            and block.block_id != L2BlockIdentificationCode.BIC_3
        ):
            self.__logger.debug("Invalid sequence detected.")
            self.__block_buffer.clear()
            return
        if (
            (150 <= current_block_number and current_block_number <= 272)
            and (current_block_number % 3 == 0 or current_block_number % 3 == 1)
            and block.block_id != L2BlockIdentificationCode.BIC_3
        ):
            self.__logger.debug("Invalid sequence detected.")
            self.__block_buffer.clear()
            return
        # BIC4
        if (
            (14 <= current_block_number and current_block_number <= 136)
            and current_block_number % 3 == 1
            and block.block_id != L2BlockIdentificationCode.BIC_4
        ):
            self.__logger.debug("Invalid sequence detected.")
            self.__block_buffer.clear()
            return
        if (
            (150 <= current_block_number and current_block_number <= 272)
            and current_block_number % 3 == 2
            and block.block_id != L2BlockIdentificationCode.BIC_4
        ):
            self.__logger.debug("Invalid sequence detected.")
            self.__block_buffer.clear()
            return

        self.__block_buffer.append(block)

        if current_block_number == 272:
            self.__logger.debug(f"272 blocks collected.")
            frame = L2Frame.from_block_buffer(self.__block_buffer)

            # Must reset the decoder
            self.reset()

            return frame
