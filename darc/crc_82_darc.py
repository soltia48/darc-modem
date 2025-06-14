from logging import getLogger
from typing import Final, Literal

from bitstring import Bits

CRC_POLYNOMIAL: Final[int] = 0x0308C0111011401440411
CRC_MASK: Final[int] = 0x3FFFFFFFFFFFFFFFFFFFF
CRC_MSB: Final[int] = 0x200000000000000000000
INITIAL_CRC: Final[int] = 0x000000000000000000000

logger = getLogger(__name__)


def _generate_crc_82_darc_table() -> list[int]:
    """Generate CRC-82/DARC lookup table.

    Returns:
        list[int]: Pre-computed CRC-82/DARC table
    """
    table = [0] * 256

    for i in range(256):
        value = i << 74
        for _ in range(8):
            value = (
                ((value << 1) ^ CRC_POLYNOMIAL) if (value & CRC_MSB) else (value << 1)
            )
        table[i] = value & CRC_MASK

    return table


# Pre-computed table as a module constant
CRC_82_DARC_TABLE: Final[list[int]] = _generate_crc_82_darc_table()


def _crc_82_darc_table_driven(message: bytes) -> int:
    """Calculate CRC-82/DARC using table-driven algorithm.

    Args:
        message: Input message as bytes or Bits

    Returns:
        Calculated CRC value
    """
    crc = INITIAL_CRC

    for value in message:
        table_index = ((crc >> 74) ^ value) & 0xFF
        crc = CRC_82_DARC_TABLE[table_index] ^ (crc << 8)
        crc &= CRC_MASK

    return crc


def _crc_82_darc_bit_by_bit(message: bytes, bits: int) -> int:
    """Calculate CRC-82/DARC using bit-by-bit algorithm.

    Args:
        message: Input message
        bits: Number of bits to process

    Returns:
        Calculated CRC value
    """
    crc = INITIAL_CRC

    for value in message:
        for i in range(8):
            if bits <= 0:
                break

            bit = (crc & CRC_MSB) ^ (CRC_MSB if value & (0x80 >> i) else 0)
            crc = ((crc << 1) ^ CRC_POLYNOMIAL if bit else (crc << 1)) & CRC_MASK
            bits -= 1

    return crc


def crc_82_darc(message: bytes, *, bits: int | None = None) -> int:
    """Calculate CRC-82/DARC.

    Args:
        message: Input message
        bits: Optional bit count (if None, assumes full bytes)

    Returns:
        Calculated CRC value
    """
    actual_bits = bits if bits is not None else 8 * len(message)
    return (
        _crc_82_darc_table_driven(message)
        if actual_bits % 8 == 0
        else _crc_82_darc_bit_by_bit(message, actual_bits)
    )


def _generate_bitflip_syndrome_map(length: int, error_width: int) -> dict[int, Bits]:
    """Generate bitflip syndrome map.

    Args:
        length: Length of the code
        error_width: Maximum error width to handle

    Returns:
        Dictionary mapping syndromes to error vectors
    """
    syndromes: dict[int, Bits] = {}

    for w in range(1, error_width + 1):
        base = (1 << (w - 1)) | 1  # 端点 2 bit は必ず 1
        middle_patterns = 1 << max(w - 2, 0)  # 中間部の組み合わせ
        for mid in range(middle_patterns):
            pattern = base | (mid << 1)
            for offset in range(length - w + 1):  # ★ +1 で最後まで
                err = pattern << offset
                vec = Bits(uint=err, length=length)
                syn = crc_82_darc(vec.bytes, bits=length)
                syndromes[syn] = vec
    return syndromes


# Pre-computed syndrome map for DSCC (272,190)
PARITY_BITFLIP_SYNDROME_MAP_DSCC_272_190: Final[dict[int, Bits]] = (
    _generate_bitflip_syndrome_map(272, 8)
)

ErrorCorrectionMode = Literal["raise", "warning", "ignore"]


def correct_error_dscc_272_190(
    buffer: Bits, mode: ErrorCorrectionMode = "ignore"
) -> Bits:
    """Correct error with Difference Set Cyclic Codes (272,190).

    Args:
        buffer: Input buffer to correct

    Returns:
        Corrected buffer if successful, None if correction failed

    Raises:
        ValueError: If buffer length is not 272 bits
    """
    if len(buffer) != 272:
        raise ValueError("Buffer length must be 272 bits")

    syndrome = crc_82_darc(buffer.bytes, bits=272)
    if syndrome == 0:
        return buffer

    logger.debug(
        "Non-zero syndrome detected: %s. Attempting error correction.", hex(syndrome)
    )

    try:
        error_vector = PARITY_BITFLIP_SYNDROME_MAP_DSCC_272_190[syndrome]
        logger.debug("Error vector found: %s", error_vector.bytes.hex())
        return buffer ^ error_vector
    except KeyError:
        message = "Error vector not found. Cannot correct error."
        if mode == "raise":
            raise ValueError(message)
        elif mode == "warning":
            logger.warning(message)
        return buffer
