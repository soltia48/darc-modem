from bitstring import Bits
from logging import getLogger

from .l4_data import L4DataGroup1, L4DataGroup2


class L5DataDecoder:
    """DARC L5 Data Decoder"""

    __logger = getLogger(__name__)

    # def __init__(self) -> None:
    #     """Constructor"""

    def push_data_groups(
        self, data_groups: list[L4DataGroup1 | L4DataGroup2]
    ) -> list[L5Data]:
        """Push Data Packets

        Args:
            data_groups (list[L4DataGroup1 | L4DataGroup2]): Data Groupss

        Returns:
            list[L5Data]: List of Data
        """

        data: list[L5Data] = []

        return data
