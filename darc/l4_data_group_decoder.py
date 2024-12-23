from bitstring import Bits
from logging import getLogger

from .l3_data import L3DataPacketServiceIdentificationCode, L3DataPacket
from .l4_data import L4DataGroup1, L4DataGroup2


class L4DataGroupDecoder:
    """DARC L4 Data Group Decoder"""

    __logger = getLogger(__name__)

    def __init__(self) -> None:
        """Constructor"""
        self.__data_group_buffers: dict[tuple[int, int], Bits] = {}

    def push_data_packets(
        self, data_packets: list[L3DataPacket]
    ) -> list[L4DataGroup1 | L4DataGroup2]:
        """Push Data Packets

        Args:
            data_packets (list[DarcL3DataPacket]): Data Packets

        Returns:
            list[DarcL4DataGroup1 | DarcL4DataGroup2]: Data Groups
        """
        data_groups: list[L4DataGroup1 | L4DataGroup2] = []

        for data_packet in data_packets:
            data_group_key = (data_packet.service_id, data_packet.data_group_number)
            data_group_buffer = self.__data_group_buffers.get(data_group_key)
            if data_group_buffer is None:
                if data_packet.data_packet_number != 0:
                    self.__logger.debug(
                        f"First Data Packet not found. service_id={hex(data_packet.service_id)} data_group_number={hex(data_packet.data_group_number)} data_packet_number={hex(data_packet.data_packet_number)}"
                    )
                    continue

                self.__data_group_buffers[data_group_key] = data_packet.data_block
            else:
                self.__data_group_buffers[data_group_key] += data_packet.data_block

            if data_packet.end_of_information_flag == 1:
                data_group_buffer = self.__data_group_buffers.pop(data_group_key)
                if (
                    data_packet.service_id
                    == L3DataPacketServiceIdentificationCode.ADDITIONAL_INFORMATION
                ):
                    data_group = L4DataGroup2.from_buffer(
                        data_packet.service_id,
                        data_packet.data_group_number,
                        data_group_buffer,
                    )
                else:
                    data_group = L4DataGroup1.from_buffer(
                        data_packet.service_id,
                        data_packet.data_group_number,
                        data_group_buffer,
                    )

                data_groups.append(data_group)

        return data_groups
