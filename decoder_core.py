"""Pure DARC decoder utilities - no side effects."""

from __future__ import annotations
import logging
import sys
from dataclasses import dataclass
from enum import Enum, unique
from pathlib import Path
from typing import Final, Iterable, Iterator, Sequence, TypeAlias

# --- DARC lib imports
from darc.l2_block_decoder import L2BlockDecoder
from darc.l2_frame_decoder import L2FrameDecoder
from darc.l3_data_packet_decoder import L3DataPacketDecoder
from darc.l4_data_group_decoder import L4DataGroupDecoder
from darc.l5_data_decoder import L5DataDecoder

BitValue: TypeAlias = int  # 0 or 1
STDIN_MARKER: Final[str] = "-"


# ------------------------------------------------------------------
# Logging
# ------------------------------------------------------------------
@unique
class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"

    def to_int(self) -> int:
        return getattr(logging, self.value)


def setup_logging(level: LogLevel) -> None:
    logging.basicConfig(
        level=level.to_int(),
        format="%(asctime)s [%(levelname)s] %(name)s:%(lineno)d - %(message)s",
    )


# ------------------------------------------------------------------
# Decoder pipeline
# ------------------------------------------------------------------
@dataclass(slots=True)
class DecoderPipeline:
    l2_block: L2BlockDecoder = L2BlockDecoder()
    l2_frame: L2FrameDecoder = L2FrameDecoder()
    l3_packet: L3DataPacketDecoder = L3DataPacketDecoder()
    l4_group: L4DataGroupDecoder = L4DataGroupDecoder()
    l5_data: L5DataDecoder = L5DataDecoder()

    def push_bit(self, bit: BitValue):
        """Yield (grp, event) whenever L5 produces output."""
        if (blk := self.l2_block.push_bit(bit)) and (
            frm := self.l2_frame.push_block(blk)
        ):
            for grp in self.l4_group.push_data_packets(self.l3_packet.push_frame(frm)):
                try:
                    evt = self.l5_data.push_data_group(grp)
                except ValueError:
                    continue
                yield grp, evt


# ------------------------------------------------------------------
# IO helpers
# ------------------------------------------------------------------
def byte_stream(path: str | Path) -> Iterator[int]:
    """Yield bytes from *path* or stdin (use '-' for stdin)."""
    if path == STDIN_MARKER:
        read = sys.stdin.buffer.read
        while b := read(1):
            yield b[0]
    else:
        with Path(path).open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                yield from chunk


def bits(stream: Iterable[int]) -> Iterator[BitValue]:
    """Convert byte iterator to logical-bit iterator (LSB only)."""
    for byte in stream:
        yield byte & 1
