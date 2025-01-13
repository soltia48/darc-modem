from typing import Final, TypeAlias

from bitstring import Bits

CrcValue: TypeAlias = int
BitCount: TypeAlias = int
Message: TypeAlias = bytes | Bits

CRC_POLYNOMIAL: Final[int] = 0x1021
CRC_MASK: Final[int] = 0xFFFF
CRC_MSB: Final[int] = 0x8000
INITIAL_CRC: Final[int] = 0x0000
BYTE_MASK: Final[int] = 0xFF


def _generate_crc_16_darc_table() -> list[int]:
    """Generate CRC-16/DARC lookup table.

    Returns:
        list[int]: Pre-computed CRC-16/DARC table
    """
    table = [0] * 256

    for i in range(256):
        value = i << 8
        for _ in range(8):
            value = (
                ((value << 1) ^ CRC_POLYNOMIAL) if (value & CRC_MSB) else (value << 1)
            )
        table[i] = value & CRC_MASK

    return table


# Pre-computed lookup table
CRC_16_DARC_TABLE: Final[list[int]] = _generate_crc_16_darc_table()


def _crc_16_darc_table_driven(message: Message) -> CrcValue:
    """Calculate CRC-16/DARC using table-driven algorithm.

    Args:
        message: Input message

    Returns:
        Calculated CRC value
    """
    crc = INITIAL_CRC
    data = message.bytes if isinstance(message, Bits) else message

    for value in data:
        table_index = ((crc >> 8) ^ value) & BYTE_MASK
        crc = CRC_16_DARC_TABLE[table_index] ^ (crc << 8)
        crc &= CRC_MASK

    return crc


def _crc_16_darc_bit_by_bit(message: Message, bits: BitCount) -> CrcValue:
    """Calculate CRC-16/DARC using bit-by-bit algorithm.

    Args:
        message: Input message
        bits: Number of bits to process

    Returns:
        Calculated CRC value
    """
    crc = INITIAL_CRC
    data = message.bytes if isinstance(message, Bits) else message

    for value in data:
        for i in range(8):
            if bits <= 0:
                break

            bit = (crc & CRC_MSB) ^ (CRC_MSB if value & (0x80 >> i) else 0)
            crc = ((crc << 1) ^ CRC_POLYNOMIAL if bit else (crc << 1)) & CRC_MASK
            bits -= 1

    return crc


def crc_16_darc(message: Message, *, bits: BitCount | None = None) -> CrcValue:
    """Calculate CRC-16/DARC checksum.

    Args:
        message: Input message
        bits: Optional bit count (if None, assumes full bytes)

    Returns:
        Calculated CRC value

    Example:
        >>> crc_16_darc(b'123456789')
        0xD64E
        >>> crc_16_darc(Bits(hex='123456789'), bits=36)
        0x1A38
    """
    actual_bits = bits if bits is not None else 8 * len(message)

    return (
        _crc_16_darc_table_driven(message)
        if actual_bits % 8 == 0
        else _crc_16_darc_bit_by_bit(message, actual_bits)
    )
