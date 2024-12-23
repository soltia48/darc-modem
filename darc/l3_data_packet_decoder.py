from .l2_data import L2Frame
from .l3_data import L3DataPacket


class L3DataPacketDecoder:
    """L3 Data Packet Decoder"""

    def push_frame(self, frame: L2Frame) -> list[L3DataPacket]:
        """Push a Frame

        Args:
            frame (L2Frame): Frame

        Returns:
            list[L3DataPacket]: Data Packets
        """

        return list(
            map(
                lambda x: L3DataPacket.from_buffer(x.data_packet),
                frame.blocks,
            )
        )
