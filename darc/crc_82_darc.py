import bitstring
from logging import getLogger

__logger = getLogger(__name__)


def __generate_crc_82_darc_table() -> list[int]:
    """Generate CRC-82/DARC table

    Returns:
        list[int]: CRC-82/DARC table
    """
    table = [0] * 256
    for i in range(256):
        value = i << 74
        for _ in range(8):
            value = (
                (value << 1) ^ 0x0308C0111011401440411
                if (value & 0x200000000000000000000) != 0
                else (value << 1)
            )
        table[i] = value & 0x3FFFFFFFFFFFFFFFFFFFF
    return table


__crc_82_darc_table = __generate_crc_82_darc_table()


def __crc_82_darc_table_driven(message: bytes | bitstring.Bits) -> int:
    """Calculate CRC-82/DARC with table driven algorithm

    Args:
        message (bytes | bitstring.Bits): Message

    Returns:
        int: CRC value
    """
    crc = 0x000000000000000000000
    for value in message:
        crc = __crc_82_darc_table[((crc >> 74) ^ value) & 0xFF] ^ (crc << 8)
    return crc & 0x3FFFFFFFFFFFFFFFFFFFF


def __crc_82_darc_bit_by_bit(message: bytes | bitstring.Bits, bits: int) -> int:
    """Calculate CRC-82/DARC with bit by bit aigorithm

    Args:
        message (bytes | bitstring.Bits): Message
        bits (int): Number of bit in message

    Returns:
        int: CRC value
    """
    crc = 0x000000000000000000000
    for value in message:
        for i in range(8):
            if bits <= 0:
                break

            bit = (crc & 0x200000000000000000000) ^ (
                0x200000000000000000000 if value & (0x80 >> i) != 0 else 0
            )
            crc <<= 1
            if bit != 0:
                crc ^= 0x0308C0111011401440411

            bits -= 1
        crc &= 0x3FFFFFFFFFFFFFFFFFFFF
    return crc & 0x3FFFFFFFFFFFFFFFFFFFF


def crc_82_darc(message: bytes | bitstring.Bits, bits: int | None = None) -> int:
    """Calculate CRC-82/DARC

    Args:
        message (bytes | bitstring.Bits): Message
        bits (int | None, optional): Number of bit in message. Defaults to None.

    Returns:
        int: CRC value
    """
    if bits is None:
        bits = 8 * len(message)

    if bits % 8 == 0:
        return __crc_82_darc_table_driven(message)
    else:
        return __crc_82_darc_bit_by_bit(message, bits)


def __generate_bitflip_syndrome_map(
    length: int, error_width: int
) -> dict[int, bitstring.Bits]:
    """Generate bitflip syndrome map

    Args:
        length (int): Length
        error_width (int): Error width

    Returns:
        dict[int, bitstring.Bits]: Bitflip syndrome map
    """
    bitflip_syndrome_map: dict[int, bitstring.Bits] = dict()
    for i in range(1, error_width + 1):
        error_base = 1 << (i - 1) | 1
        counter_max = 2 ** (i - 2) if 2 < i else 1
        for j in range(counter_max):
            error_with_counter = error_base | j << 1
            for k in range(length - i):
                error = error_with_counter << k
                error_vector = bitstring.Bits(uint=error, length=length)
                bitflip_syndrome_map[crc_82_darc(error_vector, length)] = error_vector
    return bitflip_syndrome_map


__parity_bitflip_syndrome_map_dscc_272_190 = __generate_bitflip_syndrome_map(272, 8)


def correct_error_dscc_272_190(buffer: bitstring.Bits) -> bitstring.Bits | None:
    """Correct error with Difference Set Cyclic Codes (272,190)

    Args:
        buffer (bitstring.Bits): Buffer

    Returns:
        bitstring.Bits | None: bitstring.Bits if data corrected, else None
    """
    if len(buffer) != 272:
        raise ValueError("buffer length must be 272.")

    syndrome = crc_82_darc(buffer)
    if syndrome == 0:
        return buffer

    __logger.debug(
        f"Syndrome is not zero. Try correct error with parity. syndrome={hex(syndrome)}"
    )
    try:
        error_vector = __parity_bitflip_syndrome_map_dscc_272_190[syndrome]
        __logger.debug(f"Error vector found. error_vector={error_vector.bytes.hex()}")
        return buffer ^ error_vector
    except KeyError:
        __logger.warning("Error vector not found. Cannot correct error.")
        return
