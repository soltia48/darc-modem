from typing import Final, TypeAlias

from bitstring import Bits

CrcValue: TypeAlias = int
BitCount: TypeAlias = int
Message: TypeAlias = bytes | Bits

CRC_POLYNOMIAL: Final[int] = 0x0805
CRC_MASK: Final[int] = 0x3FFF
CRC_MSB: Final[int] = 0x2000
INITIAL_CRC: Final[int] = 0x0000
BYTE_MASK: Final[int] = 0xFF
SHIFT_BITS: Final[int] = 6
BITS_PER_BYTE: Final[int] = 8


def _generate_crc_14_darc_table() -> list[int]:
    """Generate CRC-14/DARC lookup table.

    Returns:
        list[int]: Pre-computed CRC-14/DARC table
    """
    table = [0] * 256

    for i in range(256):
        value = i << SHIFT_BITS
        for _ in range(BITS_PER_BYTE):
            value = (
                ((value << 1) ^ CRC_POLYNOMIAL) if (value & CRC_MSB) else (value << 1)
            )
        table[i] = value & CRC_MASK

    return table


# Pre-computed lookup table
CRC_14_DARC_TABLE: Final[list[int]] = _generate_crc_14_darc_table()


def _crc_14_darc_table_driven(message: Message) -> CrcValue:
    """Calculate CRC-14/DARC using table-driven algorithm.

    Args:
        message: Input message

    Returns:
        Calculated CRC value
    """
    crc = INITIAL_CRC
    data = message.bytes if isinstance(message, Bits) else message

    for value in data:
        table_index = ((crc >> SHIFT_BITS) ^ value) & BYTE_MASK
        crc = CRC_14_DARC_TABLE[table_index] ^ (crc << BITS_PER_BYTE)
        crc &= CRC_MASK

    return crc


def _crc_14_darc_bit_by_bit(message: Message, bits: BitCount) -> CrcValue:
    """Calculate CRC-14/DARC using bit-by-bit algorithm.

    Args:
        message: Input message
        bits: Number of bits to process

    Returns:
        Calculated CRC value
    """
    crc = INITIAL_CRC
    data = message.bytes if isinstance(message, Bits) else message

    for value in data:
        for i in range(BITS_PER_BYTE):
            if bits <= 0:
                break

            # Calculate current bit value
            bit = (crc & CRC_MSB) ^ (CRC_MSB if value & (0x80 >> i) else 0)

            # Update CRC
            crc = ((crc << 1) ^ CRC_POLYNOMIAL if bit else (crc << 1)) & CRC_MASK
            bits -= 1

    return crc


def crc_14_darc(message: Message, *, bits: BitCount | None = None) -> CrcValue:
    """Calculate CRC-14/DARC checksum.

    This function implements the CRC-14/DARC algorithm, which is used
    in the DARC (Data Radio Channel) standard. It can process both
    byte-aligned and non-byte-aligned data.

    Args:
        message: Input message as bytes or Bits
        bits: Optional bit count (if None, assumes full bytes)

    Returns:
        Calculated CRC value

    Example:
        >>> crc_14_darc(b'123456789')
        0x082D
        >>> crc_14_darc(Bits(hex='123456789'), bits=36)
        0x2B93
    """
    actual_bits = bits if bits is not None else BITS_PER_BYTE * len(message)

    return (
        _crc_14_darc_table_driven(message)
        if actual_bits % BITS_PER_BYTE == 0
        else _crc_14_darc_bit_by_bit(message, actual_bits)
    )
