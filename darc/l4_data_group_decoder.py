from collections.abc import Sequence, MutableMapping
from dataclasses import dataclass
from logging import getLogger
from typing import TypeAlias

from bitstring import Bits

from .l3_data import L3DataPacketServiceIdentificationCode as ServiceID
from .l3_data import L3DataPacket
from .l4_data import L4DataGroup1, L4DataGroup2

DataPacket: TypeAlias = L3DataPacket
DataGroup: TypeAlias = L4DataGroup1 | L4DataGroup2
GroupKey: TypeAlias = tuple[ServiceID, int]
GroupBuffer: TypeAlias = MutableMapping[GroupKey, Bits]
DataPackets: TypeAlias = Sequence[DataPacket]
DataGroups: TypeAlias = list[DataGroup]


@dataclass(frozen=True)
class DecodingContext:
    """Context for data group decoding."""

    service_id: ServiceID
    group_number: int
    packet_number: int

    def __str__(self) -> str:
        return (
            f"service_id={hex(self.service_id)}, "
            f"group_number={hex(self.group_number)}, "
            f"packet_number={hex(self.packet_number)}"
        )


class L4DataGroupDecoder:
    """DARC Layer 4 Data Group Decoder.

    Decodes L4 data groups by assembling fragments from L3 packets.
    Handles both composition 1 and 2 formats.
    """

    def __init__(self) -> None:
        """Initialize a new data group decoder."""
        self._logger = getLogger(__name__)
        self._group_buffers: GroupBuffer = {}

    def _get_group_key(self, packet: DataPacket) -> GroupKey:
        """Create a unique key for a data group.

        Args:
            packet: L3 data packet

        Returns:
            Tuple of service ID and group number
        """
        return (packet.service_id, packet.data_group_number)

    def _log_missing_first_packet(self, context: DecodingContext) -> None:
        """Log when first packet of a group is missing.

        Args:
            context: Current decoding context
        """
        self._logger.debug("First Data Packet not found. %s", context)

    def _create_data_group(self, packet: DataPacket, buffer: Bits) -> DataGroup:
        """Create appropriate data group from buffer.

        Args:
            packet: L3 data packet containing group metadata
            buffer: Accumulated data buffer

        Returns:
            Decoded L4 data group
        """
        if packet.service_id == ServiceID.ADDITIONAL_INFORMATION:
            return L4DataGroup2.from_buffer(
                packet.service_id, packet.data_group_number, buffer
            )
        return L4DataGroup1.from_buffer(
            packet.service_id, packet.data_group_number, buffer
        )

    def push_data_packets(self, data_packets: DataPackets) -> DataGroups:
        """Process L3 data packets and assemble L4 data groups.

        Args:
            data_packets: Sequence of L3 data packets

        Returns:
            List of assembled L4 data groups
        """
        data_groups: DataGroups = []

        for packet in data_packets:
            # Create group key and get existing buffer if any
            group_key = self._get_group_key(packet)
            group_buffer = self._group_buffers.get(group_key)

            # Handle new group
            if group_buffer is None:
                if packet.data_packet_number != 0:
                    context = DecodingContext(
                        packet.service_id,
                        packet.data_group_number,
                        packet.data_packet_number,
                    )
                    self._log_missing_first_packet(context)
                    continue

                self._group_buffers[group_key] = packet.data_block
            else:
                # Append to existing buffer
                self._group_buffers[group_key] += packet.data_block

            # Check if group is complete
            if packet.end_of_information_flag == 1:
                # Get and remove buffer
                final_buffer = self._group_buffers.pop(group_key)

                # Create appropriate data group
                try:
                    data_group = self._create_data_group(packet, final_buffer)
                    data_groups.append(data_group)
                except Exception as e:
                    self._logger.error(
                        "Failed to create data group: %s. Key: %s", str(e), group_key
                    )

        return data_groups

    def get_buffer_count(self) -> int:
        """Get number of incomplete group buffers.

        Returns:
            Count of incomplete groups
        """
        return len(self._group_buffers)
