#!/usr/bin/env python3.13

import argparse
import logging
import sys
from typing import Final, TypeAlias, Sequence, NoReturn
from pathlib import Path
from dataclasses import dataclass


from darc.dump_binary import dump_binary
from darc.l2_block_decoder import L2BlockDecoder
from darc.l2_frame_decoder import L2FrameDecoder
from darc.l3_data_packet_decoder import L3DataPacketDecoder
from darc.l4_data import L4DataGroup1, L4DataGroup2
from darc.l4_data_group_decoder import L4DataGroupDecoder
from darc.l5_data import GenericDataUnit
from darc.l5_data_decoder import L5DataDecoder

# Type aliases
DataGroup: TypeAlias = L4DataGroup1 | L4DataGroup2
LogLevel: TypeAlias = str
BitValue: TypeAlias = int

# Constants
STDIN_MARKER: Final[str] = "-"
DEFAULT_LOG_LEVEL: Final[str] = "WARNING"
PROGRAM_DESCRIPTION: Final[str] = "DARC bitstream Decoder"


@dataclass
class DecoderPipeline:
    """DARC decoder pipeline configuration.

    Manages the complete decoding chain from L2 to L4.
    """

    l2_block_decoder: L2BlockDecoder
    l2_frame_decoder: L2FrameDecoder
    l3_packet_decoder: L3DataPacketDecoder
    l4_group_decoder: L4DataGroupDecoder
    l5_data_decoder: L5DataDecoder

    @classmethod
    def create(cls) -> "DecoderPipeline":
        """Create a new decoder pipeline instance."""
        return cls(
            L2BlockDecoder(),
            L2FrameDecoder(),
            L3DataPacketDecoder(),
            L4DataGroupDecoder(),
            L5DataDecoder(),
        )


def format_datagroup_output(data_group: DataGroup) -> str:
    """Format data group for output display with improved readability.

    Args:
        data_group: L4 data group to format

    Returns:
        Formatted string representation with clear structure and coloring
    """
    # ANSI color codes for better visual separation
    HEADER = "\033[95m"
    BLUE = "\033[94m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    ENDC = "\033[0m"

    # Common header information
    header = f"{HEADER}{'='*50}{ENDC}\n"
    crc_status = (
        f"{GREEN}Valid{ENDC}" if data_group.is_crc_valid() else f"{RED}Invalid{ENDC}"
    )

    common_fields = [
        f"CRC Status    : {crc_status}",
        f"Service ID    : {BLUE}{data_group.service_id.name}{ENDC}",
        f"Group Number  : {BLUE}{hex(data_group.data_group_number)}{ENDC}",
    ]

    if isinstance(data_group, L4DataGroup1):
        # Format Group 1 specific fields
        specific_fields = [
            f"Group Link    : {hex(data_group.data_group_link)}",
            f"Group Data    : {data_group.data_group_data.bytes.hex()}",
            f"End Marker    : {hex(data_group.end_of_data_group)}",
            f"CRC Value     : {hex(data_group.crc)}",
        ]
        group_type = "Data Group Type 1"
    else:
        # Format Group 2 specific fields
        crc_value = "None" if data_group.crc is None else hex(data_group.crc)
        specific_fields = [
            f"Segments Data : {data_group.segments_data.bytes.hex()}",
            f"CRC Value     : {crc_value}",
        ]
        group_type = "Data Group Type 2"

    # Combine all parts with proper formatting
    output_parts = [
        header,
        f"{HEADER}{group_type}{ENDC}",
        *common_fields,
        f"{HEADER}{'-'*50}{ENDC}",
        *specific_fields,
        f"{HEADER}{'='*50}{ENDC}\n",
    ]

    return "\n".join(output_parts)


def setup_logging(level: LogLevel) -> None:
    """Configure logging with specified level and improved format.

    Args:
        level: Logging level name
    """
    log_level = logging._nameToLevel[level]

    # Define custom log format with colors
    class ColoredFormatter(logging.Formatter):
        COLORS = {
            "DEBUG": "\033[94m",  # Blue
            "INFO": "\033[92m",  # Green
            "WARNING": "\033[93m",  # Yellow
            "ERROR": "\033[91m",  # Red
            "CRITICAL": "\033[95m",  # Purple
        }

        def format(self, record):
            # Add color to level name if available
            if record.levelname in self.COLORS:
                record.levelname = (
                    f"{self.COLORS[record.levelname]}{record.levelname}\033[0m"
                )
            return super().format(record)

    # Create and set formatted handler
    handler = logging.StreamHandler()
    formatter = ColoredFormatter(
        "%(asctime)s [%(levelname)s] %(name)s.%(funcName)s:%(lineno)d - %(message)s"
    )
    handler.setFormatter(formatter)

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)
    root_logger.addHandler(handler)


def process_stdin(pipeline: DecoderPipeline) -> NoReturn:
    """Process DARC bitstream from standard input.

    Args:
        pipeline: Configured decoder pipeline

    Note:
        This function runs indefinitely until interrupted.
    """
    while True:
        try:
            # Read and decode single bit
            bit = ord(sys.stdin.read(1))

            # Process through decoder pipeline
            if block := pipeline.l2_block_decoder.push_bit(bit):
                if frame := pipeline.l2_frame_decoder.push_block(block):
                    data_packets = pipeline.l3_packet_decoder.push_frame(frame)
                    data_groups = pipeline.l4_group_decoder.push_data_packets(
                        data_packets
                    )
                    for data_group in data_groups:
                        data_header, data_units = (
                            pipeline.l5_data_decoder.push_data_group(data_group)
                        )
                        if data_header is None:
                            continue
                        print(format_datagroup_output(data_group))
                        print("=" * 64)
                        print()
                        print("Data Header :       ", data_header)
                        print()
                        for data_unit in data_units:
                            print("-" * 32)
                            if isinstance(data_unit, GenericDataUnit):
                                print(
                                    "Data Unit Parameter:",
                                    format(data_unit.data_unit_parameter, "02X"),
                                )
                                print(
                                    "Data Unit Link Flag:",
                                    format(data_unit.data_unit_link_flag, "02X"),
                                )
                                print("Data Unit Data:")
                                print(dump_binary(data_unit.data))
                            elif isinstance(data_unit, bytes):
                                print("Data Unit (Maybe scrambled):")
                                print(dump_binary(data_unit))
                            print("-" * 32)
                            print()

                    # Output decoded data groups
                    # for group in data_groups:
                    # print(format_datagroup_output(group))

        except (KeyboardInterrupt, EOFError):
            sys.exit(0)
        except Exception as e:
            logging.error("Processing error: %s", str(e))
            continue


def process_file(path: Path) -> NoReturn:
    """Process DARC bitstream from file.

    Args:
        path: Path to input file

    Note:
        Currently not implemented.
    """
    print("File input is not yet supported.")
    sys.exit(1)


def parse_arguments(args: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command line arguments.

    Args:
        args: Command line arguments (None uses sys.argv)

    Returns:
        Parsed argument namespace
    """
    parser = argparse.ArgumentParser(description=PROGRAM_DESCRIPTION)
    parser.add_argument(
        "input_path", help=f"Input DARC bitstream path ({STDIN_MARKER} for stdin)"
    )
    parser.add_argument(
        "-log",
        "--loglevel",
        default=DEFAULT_LOG_LEVEL,
        help="Logging level",
        choices=list(logging._nameToLevel.keys()),
    )
    return parser.parse_args(args)


def main(argv: Sequence[str] | None = None) -> int:
    """Main program entry point.

    Args:
        argv: Command line arguments (None uses sys.argv)

    Returns:
        Exit code (0 for success)
    """
    try:
        args = parse_arguments(argv)
        setup_logging(args.loglevel)
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
