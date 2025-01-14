from bitstring import BitStream, ReadError
from logging import getLogger

from .l4_data import L4DataGroup1, L4DataGroup2
from .l5_data import read_data_header, GenericDataUnit


class L5DataDecoder:
    """DARC L5 Data Decoder"""

    __logger = getLogger(__name__)

    def push_data_groups(
        self, data_groups: list[L4DataGroup1 | L4DataGroup2]
    ) -> list[tuple]:
        """Push Data Packets

        Args:
            data_groups (list[L4DataGroup1 | L4DataGroup2]): Data Groupss

        Returns:
            list[L5Data]: List of Data
        """

        data: list[tuple] = []

        for data_group in data_groups:
            if isinstance(data_group, L4DataGroup2):
                continue
            stream = BitStream(data_group.data_group_data)
            data_header = read_data_header(stream)
            data_units = []
            while True:
                try:
                    first_byte: int = stream.peek("uint8")
                    if first_byte == 0x00:
                        break
                    data_unit = GenericDataUnit.read(stream)
                    data_units.append(data_unit)
                except ReadError:
                    break

            data.append((data_header, data_units))

        return data
