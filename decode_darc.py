import argparse
import logging
import sys
from dataclasses import dataclass, fields
from pathlib import Path
from pprint import pprint
from typing import (
    Final,
    Literal,
    NoReturn,
    Self,
    Sequence,
    TypeAlias,
    Any,
    get_type_hints,
)

from darc.arib_string import AribStringDecoder
from darc.dump_binary import dump_binary
from darc.l2_block_decoder import L2BlockDecoder
from darc.l2_frame_decoder import L2FrameDecoder
from darc.l3_data_packet_decoder import L3DataPacketDecoder
from darc.l4_data import L4DataGroup1, L4DataGroup2
from darc.l4_data_group_decoder import L4DataGroupDecoder
from darc.l5_data import GenericDataUnit, Segment
from darc.l5_data_decoder import L5DataDecoder
from darc.l5_data import (
    DataHeaderBase,
    ProgramDataHeaderA,
    ProgramDataHeaderB,
    PageDataHeaderA,
    PageDataHeaderB,
    ProgramCommonMacroDataHeaderA,
    ProgramCommonMacroDataHeaderB,
    ContinueDataHeader,
    ProgramIndexDataHeader,
)
from darc.l5_data_units import decode_unit

# Type aliases with more specific typing
DataGroup: TypeAlias = L4DataGroup1 | L4DataGroup2
LogLevel: TypeAlias = Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]
BitValue: TypeAlias = Literal[0, 1]

# Constants
STDIN_MARKER: Final[str] = "-"
DEFAULT_LOG_LEVEL: Final[LogLevel] = "WARNING"
PROGRAM_DESCRIPTION: Final[str] = "DARC bitstream Decoder"
SEPARATOR_LINE: Final[str] = "-" * 80
DOUBLE_SEPARATOR: Final[str] = "=" * 80


def format_hex(value: int | None, width: int = 2) -> str:
    """Format hex value with consistent width."""
    if value is None:
        return "None"
    return f"0x{value:0{width}X}"


def format_data_header(header: DataHeaderBase) -> str:
    """Format data header for output display.

    Args:
        header: Data header to format

    Returns:
        Formatted string representation of the data header
    """
    header_type = header.__class__.__name__
    lines = [DOUBLE_SEPARATOR, f"DATA HEADER: {header_type}", SEPARATOR_LINE]

    # Get all fields except internal ones (starting with _)
    field_list = [f for f in fields(header) if not f.name.startswith("_")]

    # Format each field
    field_types = get_type_hints(header.__class__)
    for field in field_list:
        value = getattr(header, field.name)
        field_type = field_types.get(field.name, Any)

        if isinstance(value, int):
            # Format numeric values as hex and decimal
            formatted_value = f"{format_hex(value)} ({value})"
        elif value is None:
            formatted_value = "None"
        else:
            formatted_value = str(value)

        # Convert field name from snake_case to Title Case
        field_name = field.name.replace("_", " ").title()
        lines.append(f"{field_name:<25}: {formatted_value}")

    lines.append(DOUBLE_SEPARATOR)
    return "\n".join(lines)


@dataclass(frozen=True, slots=True)
class DecoderPipeline:
    """DARC decoder pipeline configuration."""

    l2_block_decoder: L2BlockDecoder
    l2_frame_decoder: L2FrameDecoder
    l3_packet_decoder: L3DataPacketDecoder
    l4_group_decoder: L4DataGroupDecoder
    l5_data_decoder: L5DataDecoder

    @classmethod
    def create(cls) -> Self:
        """Create a new decoder pipeline instance."""
        return cls(
            L2BlockDecoder(),
            L2FrameDecoder(),
            L3DataPacketDecoder(),
            L4DataGroupDecoder(),
            L5DataDecoder(),
        )


def format_data_unit(data_unit: GenericDataUnit | bytes) -> str:
    """Format data unit for output display."""
    lines = [SEPARATOR_LINE]
    string_decoder = AribStringDecoder()

    match data_unit:
        case GenericDataUnit():
            try:
                data_arib_str = string_decoder.decode(data_unit.data_unit_data)
            except:
                data_arib_str = None
            lines.extend(
                [
                    "GENERIC DATA UNIT",
                    f"Parameter     : {format_hex(data_unit.data_unit_parameter)}",
                    f"Link Flag     : {format_hex(data_unit.data_unit_link_flag)}",
                    "Data          :",
                    dump_binary(data_unit.data_unit_data),
                    f"Data (ARIBStr): {data_arib_str}",
                ]
            )
        case bytes():
            try:
                data_arib_str = string_decoder.decode(data_unit)
            except:
                data_arib_str = None
            lines.extend(
                [
                    "RAW DATA UNIT (Potentially Scrambled)",
                    dump_binary(data_unit),
                    f"Data (ARIBStr): {data_arib_str}",
                ]
            )

    lines.append(SEPARATOR_LINE)
    return "\n".join(lines)


def format_segment(segment: Segment) -> str:
    """Format segment for output display."""
    lines = [
        DOUBLE_SEPARATOR,
        "SEGMENT INFORMATION",
        SEPARATOR_LINE,
        f"Identifier    : {format_hex(segment.segment_identifier)}",
    ]
    string_decoder = AribStringDecoder()

    if segment.segment_identifier == 0xE:
        lines.extend(
            [
                f"Other Station Number      : {format_hex(segment.other_station_number)}",
                f"Other Station Segment ID  : {format_hex(segment.other_station_segment_identifier)}",
            ]
        )

    try:
        data_arib_str = string_decoder.decode(segment.segment_data)
    except:
        data_arib_str = None

    lines.extend(
        [
            "Segment Data  :",
            dump_binary(segment.segment_data),
            f"Data (ARIBStr): {data_arib_str}",
            DOUBLE_SEPARATOR,
        ]
    )

    return "\n".join(lines)


def format_datagroup_output(data_group: DataGroup) -> str:
    """Format data group for output display."""
    lines = [
        DOUBLE_SEPARATOR,
        "DATA GROUP INFORMATION",
        SEPARATOR_LINE,
        f"Type          : {'Type 1' if isinstance(data_group, L4DataGroup1) else 'Type 2'}",
        f"CRC Status    : {'Valid' if data_group.is_crc_valid() else 'Invalid'}",
        f"Service ID    : {data_group.service_id.name}",
        f"Group Number  : {format_hex(data_group.data_group_number)}",
    ]

    match data_group:
        case L4DataGroup1():
            lines.extend(
                [
                    f"Group Link    : {format_hex(data_group.data_group_link)}",
                    f"End Marker    : {format_hex(data_group.end_of_data_group)}",
                    f"CRC Value     : {format_hex(data_group.crc)}",
                    "RAW           :",
                    dump_binary(data_group.to_buffer().bytes),
                ]
            )
        case L4DataGroup2():
            lines.extend(
                [
                    f"CRC Value     : {format_hex(data_group.crc)}",
                    # "Segments Data :",
                    # dump_binary(data_group.segments_data.bytes),
                ]
            )

    lines.append(DOUBLE_SEPARATOR)
    return "\n".join(lines)


def setup_logging(level: LogLevel) -> None:
    """Configure logging with specified level."""
    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s.%(funcName)s:%(lineno)d - %(message)s"
    )
    handler = logging.StreamHandler()
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)


def process_stdin(pipeline: DecoderPipeline) -> NoReturn:
    """Process DARC bitstream from standard input."""
    while True:
        try:
            bit = ord(sys.stdin.read(1))

            if not (block := pipeline.l2_block_decoder.push_bit(bit)):
                continue

            if not (frame := pipeline.l2_frame_decoder.push_block(block)):
                continue

            data_packets = pipeline.l3_packet_decoder.push_frame(frame)
            data_groups = pipeline.l4_group_decoder.push_data_packets(data_packets)

            for data_group in data_groups:
                l5_data = pipeline.l5_data_decoder.push_data_group(data_group)

                match l5_data:
                    case (data_header, data_units):
                        if data_header is None:
                            continue

                        print(format_datagroup_output(data_group))
                        print(format_data_header(data_header))
                        for data_unit in data_units:
                            print(format_data_unit(data_unit))
                            # if data_group.is_crc_valid():
                            #     pprint(decode_unit(data_unit)) # type: ignore
                        print()

                    case Segment():
                        print(format_segment(l5_data))
                        print()

        except (KeyboardInterrupt, EOFError):
            sys.exit(0)
        except Exception as e:
            logging.error("Processing error: %s", str(e))
            continue


def process_file(path: Path) -> NoReturn:
    """Process DARC bitstream from file."""
    print("File input is not yet supported.")
    sys.exit(1)


def parse_arguments(args: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description=PROGRAM_DESCRIPTION)
    parser.add_argument(
        "input_path", help=f"Input DARC bitstream path ({STDIN_MARKER} for stdin)"
    )
    parser.add_argument(
        "-log",
        "--log-level",
        default=DEFAULT_LOG_LEVEL,
        help="Logging level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )
    return parser.parse_args(args)


def main(argv: Sequence[str] | None = None) -> int:
    """Main program entry point."""
    try:
        args = parse_arguments(argv)
        setup_logging(args.log_level)
        pipeline = DecoderPipeline.create()

        if args.input_path == STDIN_MARKER:
            process_stdin(pipeline)
        else:
            process_file(Path(args.input_path))

        return 0

    except Exception as e:
        logging.error("Fatal error: %s", str(e))
        return 1


if __name__ == "__main__":
    sys.exit(main())
