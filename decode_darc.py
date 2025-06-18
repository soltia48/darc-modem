import argparse
import logging
import sys
from dataclasses import dataclass, fields
from pprint import pprint
from typing import Final, Sequence, TypeAlias

# ---------------------------------------------------------------------------
# Shared decoder utilities (pure)
# ---------------------------------------------------------------------------
from decoder_core import (
    DecoderPipeline,
    LogLevel,
    STDIN_MARKER,
    bits,
    byte_stream,
    setup_logging,
)

# ---------------------------------------------------------------------------
# DARC library helpers (for pretty-printing only — heavy but optional)
# ---------------------------------------------------------------------------
from darc.arib_string import AribStringDecoder
from darc.dump_binary import dump_binary
from darc.l4_data import L4DataGroup1, L4DataGroup2
from darc.l5_data import DataHeaderBase, GenericDataUnit, Segment
from darc.l5_data_units import data_unit_from_generic

DataGroup: TypeAlias = L4DataGroup1 | L4DataGroup2

SEP: Final[str] = "-" * 80
DSEP: Final[str] = "=" * 80

# ---------------------------------------------------------------------------
# Formatting helpers (human-readable dump)
# ---------------------------------------------------------------------------
_arib = AribStringDecoder()


def _hex(v: int | None, width: int = 2) -> str:
    return "None" if v is None else f"0x{v:0{width}X}"


def _try_arib(data: bytes) -> str | None:
    """Attempt ARIB STD-B24 decoding; return *None* on failure."""
    try:
        return _arib.decode(data)
    except Exception:  # pragma: no cover - external lib may raise
        return None


def fmt_header(h: DataHeaderBase) -> str:
    lines = [DSEP, f"DATA HEADER: {h.__class__.__name__}", SEP]
    for fld in (f for f in fields(h) if not f.name.startswith("_")):
        val = getattr(h, fld.name)
        rep = f"{_hex(val)} ({val})" if isinstance(val, int) else str(val)
        lines.append(f"{fld.name.replace('_', ' ').title():<25}: {rep}")
    lines.append(DSEP)
    return "\n".join(lines)


def fmt_unit(u: GenericDataUnit) -> str:
    lines: list[str] = [SEP]
    a = _try_arib(u.data_unit_data)
    lines += [
        "GENERIC DATA UNIT",
        f"Parameter     : {_hex(u.data_unit_parameter)}",
        f"Link Flag     : {_hex(u.data_unit_link_flag)}",
        "Data          :",
        dump_binary(u.data_unit_data),
        f"Data (ARIBStr): {a}",
    ]
    lines.append(SEP)
    return "\n".join(lines)


def fmt_segment(s: Segment) -> str:
    lines = [
        DSEP,
        "SEGMENT INFORMATION",
        SEP,
        f"Identifier    : {_hex(s.segment_identifier)}",
    ]
    if s.segment_identifier == 0xE:  # external station info
        lines += [
            f"Other Station Number      : {_hex(s.other_station_number)}",
            f"Other Station Segment ID  : {_hex(s.other_station_segment_identifier)}",
        ]
    a = _try_arib(s.segment_data)
    lines += [
        "Segment Data  :",
        dump_binary(s.segment_data),
        f"Data (ARIBStr): {a}",
        DSEP,
    ]
    return "\n".join(lines)


def fmt_group(g: DataGroup) -> str:
    lines = [
        DSEP,
        "DATA GROUP INFORMATION",
        SEP,
        f"Type          : {'Type 1' if isinstance(g, L4DataGroup1) else 'Type 2'}",
        f"CRC Status    : {'Valid' if g.is_crc_valid() else 'Invalid'}",
        f"Service ID    : {g.service_id.name}",
        f"Group Number  : {_hex(g.data_group_number)}",
    ]
    if isinstance(g, L4DataGroup1):
        lines += [
            f"Group Link    : {_hex(g.data_group_link)}",
            f"End Marker    : {_hex(g.end_of_data_group)}",
            f"CRC Value     : {_hex(g.crc)}"
        ]
    else:
        lines.append(f"CRC Value     : {_hex(g.crc)}")
    lines.append(DSEP)
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class CliArgs:
    input_path: str
    log_level: LogLevel


def parse_args(argv: Sequence[str] | None = None) -> CliArgs:
    p = argparse.ArgumentParser("DARC bit-stream Decoder (CLI)")
    p.add_argument(
        "input_path",
        help=f"Input DARC bit-stream ({STDIN_MARKER}=stdin)",
    )
    p.add_argument(
        "-l",
        "--log-level",
        default=LogLevel.INFO.value,
        choices=[lvl.value for lvl in LogLevel],
        help="Logging level",
    )
    ns = p.parse_args(argv)
    return CliArgs(ns.input_path, LogLevel(ns.log_level))


# ---------------------------------------------------------------------------
# Decoder runner
# ---------------------------------------------------------------------------


def run_decoder(args: CliArgs) -> int:
    """Main decoding loop - prints human-readable dump to stdout."""
    setup_logging(args.log_level)
    pipe = DecoderPipeline()

    try:
        for bit in bits(byte_stream(args.input_path)):
            for grp, event in pipe.push_bit(bit):
                # --- L4 group summary ---
                print(fmt_group(grp))

                # --- L5 event details ---
                match event:
                    case Segment() as seg:
                        print(fmt_segment(seg), "\n")
                    case (hdr, units):
                        if hdr:
                            print(fmt_header(hdr))
                        for u in units:
                            print(fmt_unit(u))
                            if grp.is_crc_valid():
                                pprint(data_unit_from_generic(u))
                        print()
        return 0

    except (KeyboardInterrupt, EOFError):
        return 0  # graceful termination

    except Exception as exc:  # noqa: BLE001 - propagate as fatal
        logging.exception("Fatal error: %s", exc)
        return 1


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main(argv: Sequence[str] | None = None) -> None:  # pragma: no cover
    sys.exit(run_decoder(parse_args(argv)))


if __name__ == "__main__":
    main()
