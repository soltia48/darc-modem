import argparse
import logging
import sys

from darc.l2_block_decoder import DarcL2BlockDecoder
from darc.l2_frame_decoder import DarcL2FrameDecoder
from darc.l3_data_packet_decoder import DarcL3DataPacketDecoder
from darc.l4_data import DarcL4DataGroup1, DarcL4DataGroup2
from darc.l4_data_group_decoder import DarcL4DataGroupDecoder


def configLogger(level: str):
    """Config logger

    Args:
        level (str): Log level
    """
    level = logging._nameToLevel[level]
    logging.basicConfig(
        level=level,
        format="[%(asctime)s] %(levelname)s [%(name)s.%(funcName)s:%(lineno)d] %(message)s",
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description="DARC bitstream Decoder")
    parser.add_argument("input_path", help="Input DARC bitstream path (- to stdin)")
    parser.add_argument(
        "-log",
        "--loglevel",
        default="WARNING",
        help="Logging level",
        choices=["NOTSET", "DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
    )
    args = parser.parse_args()

    configLogger(args.loglevel)

    l2_block_decoder = DarcL2BlockDecoder()
    l2_frame_decoder = DarcL2FrameDecoder()
    l3_data_packet_decoder = DarcL3DataPacketDecoder()
    l4_data_group_decoder = DarcL4DataGroupDecoder()

    if args.input_path == "-":
        while True:
            bit = ord(sys.stdin.read(1))
            block = l2_block_decoder.push_bit(bit)
            if block is None:
                continue
            frame = l2_frame_decoder.push_block(block)
            if frame is None:
                continue
            data_packets = l3_data_packet_decoder.push_frame(frame)
            data_groups = l4_data_group_decoder.push_data_packets(data_packets)
            for data_group in data_groups:
                if isinstance(data_group, DarcL4DataGroup1):
                    print(
                        f"is_crc_valid={data_group.is_crc_valid()} service_id={data_group.service_id.name} data_group_number={hex(data_group.data_group_number)} data_group_link={hex(data_group.data_group_link)} data_group_data={data_group.data_group_data.bytes.hex()} end_of_data_group={hex(data_group.end_of_data_group)} crc={hex(data_group.crc)}"
                    )
                elif isinstance(data_group, DarcL4DataGroup2):
                    crc_string = (
                        "None" if data_group.crc is None else hex(data_group.crc)
                    )
                    print(
                        f"is_crc_valid={data_group.is_crc_valid()} service_id={data_group.service_id.name} data_group_number={hex(data_group.data_group_number)} segments_data={data_group.segments_data.bytes.hex()} crc={crc_string}"
                    )
    else:
        print("File input is not yet supported.")


if __name__ == "__main__":
    main()
