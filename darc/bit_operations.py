from typing import Final

NIBBLE_HIGH: Final[int] = 0xF0
NIBBLE_LOW: Final[int] = 0x0F
PAIR_HIGH: Final[int] = 0xCC
PAIR_LOW: Final[int] = 0x33
ODD_BITS: Final[int] = 0xAA
EVEN_BITS: Final[int] = 0x55


def reverse_bits(buffer: bytes | bytearray) -> bytes:
    """Reverse the bits in each byte of the input buffer.

    This function reverses the bits in each byte using an optimized algorithm
    that performs the reversal in three steps using masks and shifts.

    Args:
        buffer: Input bytes, bytearray, or iterable of integers

    Returns:
        A new bytes object with all bits reversed

    Example:
        >>> reverse_bits(b'\\x0F')  # 0000 1111 -> 1111 0000
        b'\\xF0'
        >>> reverse_bits(b'\\xAA')  # 1010 1010 -> 0101 0101
        b'\\x55'

    Note:
        The algorithm uses the following steps for each byte:
        1. Swap nibbles (4 bits)
        2. Swap pairs of bits
        3. Swap adjacent bits
    """
    # Pre-allocate bytearray for better performance
    result = bytearray(len(buffer))

    for i, value in enumerate(buffer):
        # Step 1: Swap nibbles (4 bits)
        value = ((value & NIBBLE_HIGH) >> 4) | ((value & NIBBLE_LOW) << 4)

        # Step 2: Swap pairs of bits
        value = ((value & PAIR_HIGH) >> 2) | ((value & PAIR_LOW) << 2)

        # Step 3: Swap adjacent bits
        value = ((value & ODD_BITS) >> 1) | ((value & EVEN_BITS) << 1)

        result[i] = value

    return bytes(result)
