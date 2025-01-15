from collections.abc import Sequence
from logging import getLogger
from typing import ClassVar, Final, TypeAlias

from bitstring import BitStream, ReadError

from .l4_data import L4DataGroup1, L4DataGroup2
from .l5_data import DataHeaderBase, read_data_header, GenericDataUnit, Segment

DataUnit: TypeAlias = GenericDataUnit | bytes
DataGroup: TypeAlias = L4DataGroup1 | L4DataGroup2
L5Data: TypeAlias = tuple[DataHeaderBase, Sequence[DataUnit]] | Segment

PADDING_BYTE: Final[int] = 0x00


class L5DataDecoder:
    """DARC L5 (Layer 5) Data Decoder.

    This decoder handles the processing of L4 data groups and converts them into
    appropriate L5 data structures (either data header + units or segments).
    """

    _logger: ClassVar = getLogger(__name__)

    def push_data_group(self, data_group: DataGroup) -> L5Data:
        """Process a data group and extract L5 data.

        Args:
            data_group: L4 data group to process

        Returns:
            Either a tuple of (data header, data units) or a Segment object

        Raises:
            ValueError: Invalid data group type
            ReadError: Error reading from bitstream
        """
        try:
            match data_group:
                case L4DataGroup1():
                    return self._process_data_group1(data_group)
                case L4DataGroup2():
                    return self._process_data_group2(data_group)
                case _:
                    raise ValueError(
                        f"Unsupported data group type: {type(data_group).__name__}"
                    )
        except ReadError as e:
            self._logger.error("Error reading data group: %s", str(e))
            raise

    def _process_data_group1(
        self, data_group: L4DataGroup1
    ) -> tuple[DataHeaderBase, list[DataUnit]]:
        """Process L4DataGroup1 type data.

        Args:
            data_group: L4DataGroup1 to process

        Returns:
            Tuple of data header and list of data units
        """
        stream = BitStream(data_group.data_group_data)
        data_header = read_data_header(stream)

        if data_header is None:
            self._logger.warning("Failed to read data header")
            return None, []

        data_units = self._read_data_units(stream)
        return data_header, data_units

    def _process_data_group2(self, data_group: L4DataGroup2) -> Segment:
        """Process L4DataGroup2 type data.

        Args:
            data_group: L4DataGroup2 to process

        Returns:
            Segment object
        """
        stream = BitStream(data_group.segments_data)
        return Segment.read(stream)

    def _read_data_units(self, stream: BitStream) -> list[DataUnit]:
        """Read all data units from a bitstream.

        Args:
            stream: Input bitstream

        Returns:
            List of data units (either GenericDataUnit or raw bytes)
        """
        data_units: list[DataUnit] = []

        while stream.pos < stream.len:
            try:
                # Peek at next byte
                if stream.peek("uint8") == PADDING_BYTE:
                    stream.read("uint8")  # Skip padding
                    continue

                data_unit = GenericDataUnit.read(stream)
                data_units.append(data_unit)

            except ReadError as e:
                self._logger.warning("Error reading data unit: %s", str(e))
                break

        return data_units
