from typing import TypeAlias
from collections.abc import Sequence

from .l2_data import L2Frame
from .l3_data import L3DataPacket

DataPackets: TypeAlias = Sequence[L3DataPacket]


class L3DataPacketDecoder:
    """Layer 3 Data Packet Decoder.

    Decodes Layer 3 data packets from Layer 2 frames in the DARC protocol.
    """

    def push_frame(self, frame: L2Frame) -> DataPackets:
        """Process a Layer 2 frame and extract Layer 3 data packets.

        Converts each information block in the frame to a Layer 3 data packet.

        Args:
            frame: Layer 2 frame containing data packets

        Returns:
            Sequence of decoded Layer 3 data packets
        """
        return [L3DataPacket.from_buffer(block.data_packet) for block in frame.blocks]
