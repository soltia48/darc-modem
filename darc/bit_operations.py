def reverse_bits(buffer: bytes) -> bytes:
    """Reverse bits in byte

    Args:
        buffer (bytes): Buffer

    Returns:
        bytes: Bit reversed buffer
    """
    result = b""
    for value in buffer:
        value = (value & 0xF0) >> 4 | (value & 0x0F) << 4
        value = (value & 0xCC) >> 2 | (value & 0x33) << 2
        value = (value & 0xAA) >> 1 | (value & 0x55) << 1
        result += value.to_bytes()
    return result
